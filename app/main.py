"""Веб-интерфейс и API xray-checker."""

from __future__ import annotations

import asyncio
import csv
import hmac
import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import db, subscription
from app.config import APP_VERSION, LOG_LEVEL, STATIC_DIR, WEB_PASSWORD
from app.engines import binary_status
from app.runner import Runner
from app.scheduler import Scheduler
from app.subscription import SubscriptionError

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("checker")
logger.setLevel(LOG_LEVEL)


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not WEB_PASSWORD:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if len(token) != len(WEB_PASSWORD) or not hmac.compare_digest(token, WEB_PASSWORD):
        raise HTTPException(status_code=401, detail="Нужен пароль")


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscription_url: str = ""
    subscription_insecure: bool
    scheduler_enabled: bool
    interval_minutes: int = Field(ge=1, le=1440)
    concurrency: int = Field(ge=1, le=4)
    download_seconds: int = Field(ge=3, le=60)
    upload_seconds: int = Field(ge=3, le=60)
    download_bytes: int = Field(ge=1_000_000, le=2_000_000_000)
    upload_bytes: int = Field(ge=1_000_000, le=2_000_000_000)
    download_url: str
    upload_url: str
    latency_url: str
    tls_insecure_if_no_sni: bool
    refresh_before_run: bool
    measure_download: bool
    measure_upload: bool
    retention_days: int = Field(ge=1, le=3650)

    @field_validator("subscription_url")
    @classmethod
    def subscription_lines(cls, value: str) -> str:
        for line in value.splitlines():
            item = line.strip()
            if item and not item.lower().startswith(("http://", "https://")):
                raise ValueError("ссылка должна начинаться с http:// или https://")
        return value.strip()

    @field_validator("download_url", "upload_url", "latency_url")
    @classmethod
    def http_url(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("адрес должен начинаться с http:// или https://")
        return value


class RunIn(BaseModel):
    node_ids: list[str] | None = None
    include_disabled: bool = False


class EnabledIn(BaseModel):
    enabled: bool


class NoCacheStatic(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _safe_refresh() -> None:
    try:
        subscription.refresh()
    except SubscriptionError as exc:
        logger.warning("startup refresh: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    app.state.runner = Runner()
    app.state.scheduler = Scheduler(app.state.runner)
    app.state.versions = {"app": APP_VERSION, **binary_status()}
    refresh_task = asyncio.create_task(asyncio.to_thread(_safe_refresh))
    sched_task = asyncio.create_task(app.state.scheduler.loop())
    try:
        yield
    finally:
        app.state.scheduler.stop()
        app.state.runner.cancel()
        sched_task.cancel()
        refresh_task.cancel()
        for task in (sched_task, refresh_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="xray-checker", lifespan=lifespan)


@app.middleware("http")
async def api_not_cached(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    parts = []
    for item in exc.errors():
        loc = ".".join(str(part) for part in item["loc"] if part != "body")
        parts.append(f"{loc}: {item['msg']}" if loc else item["msg"])
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "проверьте поля"})


@app.get("/api/health")
def health(request: Request):
    versions = getattr(request.app.state, "versions", {})
    return {"ok": True, "auth": bool(WEB_PASSWORD), "versions": versions}


@app.get("/api/state", dependencies=[Depends(require_auth)])
def state(request: Request):
    raw = db.get_raw_settings()
    public = db.public_settings(raw)
    nodes = db.list_nodes()
    enabled = [node for node in nodes if node["active"] and node["supported"] and node["enabled"]]
    per_node = 0
    if public["measure_download"]:
        per_node += public["download_bytes"]
    if public["measure_upload"]:
        per_node += public["upload_bytes"]
    next_at = request.app.state.scheduler.next_at
    runs = db.list_runs(1)
    return {
        "running": request.app.state.runner.progress,
        "next_run_at": _iso(next_at),
        "scheduler_enabled": public["scheduler_enabled"],
        "last_refresh_at": raw.get("last_refresh_at") or None,
        "last_refresh_error": raw.get("last_refresh_error") or "",
        "userinfo": subscription.userinfo_view(raw.get("subscription_userinfo") or ""),
        "versions": request.app.state.versions,
        "enabled_count": len(enabled),
        "node_count": sum(1 for node in nodes if node["active"]),
        "estimate_bytes": per_node * len(enabled),
        "interval_minutes": public["interval_minutes"],
        "last_run": runs[0] if runs else None,
    }


@app.get("/api/settings", dependencies=[Depends(require_auth)])
def get_settings():
    return db.public_settings()


@app.put("/api/settings", dependencies=[Depends(require_auth)])
def put_settings(body: SettingsIn):
    return db.save_settings(body.model_dump())


@app.post("/api/scheduler", dependencies=[Depends(require_auth)])
def set_scheduler(body: EnabledIn):
    current = db.public_settings()
    current["scheduler_enabled"] = body.enabled
    return db.save_settings(current)


@app.post("/api/subscription/refresh", dependencies=[Depends(require_auth)])
def refresh_subscription():
    try:
        count = subscription.refresh()
    except SubscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": count}


@app.get("/api/nodes", dependencies=[Depends(require_auth)])
def get_nodes():
    return db.list_nodes()


@app.post("/api/nodes/{node_id}/enabled", dependencies=[Depends(require_auth)])
def set_node_enabled(node_id: str, body: EnabledIn):
    if not db.set_enabled(node_id, body.enabled):
        raise HTTPException(status_code=404, detail="Узел не найден или протокол не поддерживается")
    return {"ok": True}


@app.post("/api/nodes/enabled", dependencies=[Depends(require_auth)])
def set_nodes_enabled(body: EnabledIn):
    count = db.set_enabled_all(body.enabled)
    return {"count": count}


@app.get("/api/nodes/{node_id}/history", dependencies=[Depends(require_auth)])
def history(node_id: str, limit: int = 500):
    limit = min(max(limit, 1), 2000)
    if db.get_node_link(node_id) is None:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return db.node_history(node_id, limit)


@app.get("/api/series", dependencies=[Depends(require_auth)])
def series(hours: int = 48):
    hours = min(max(hours, 1), 24 * 90)
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return db.series(since)


@app.post("/api/runs", dependencies=[Depends(require_auth)])
async def start_run(body: RunIn, request: Request):
    rows = db.nodes_for_run(body.node_ids, body.include_disabled)
    if not rows:
        raise HTTPException(status_code=400, detail="Нет узлов для проверки. Включите узлы или обновите подписку.")
    started = await request.app.state.runner.begin("manual", body.node_ids, body.include_disabled)
    if not started:
        raise HTTPException(status_code=409, detail="Проверка уже выполняется")
    return {"ok": True}


@app.post("/api/runs/cancel", dependencies=[Depends(require_auth)])
def cancel_run(request: Request):
    request.app.state.runner.cancel()
    return {"ok": True}


@app.get("/api/runs", dependencies=[Depends(require_auth)])
def runs(limit: int = 40):
    return db.list_runs(min(max(limit, 1), 200))


@app.get("/api/runs/{run_id}", dependencies=[Depends(require_auth)])
def run_detail(run_id: int):
    item = db.get_run(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Прогон не найден")
    return item


@app.delete("/api/history", dependencies=[Depends(require_auth)])
def delete_history(request: Request):
    if request.app.state.runner.busy():
        raise HTTPException(status_code=409, detail="Нельзя очистить историю во время проверки")
    db.clear_history()
    return {"ok": True}


@app.get("/api/export.csv", dependencies=[Depends(require_auth)])
def export_csv():
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "tested_at",
            "name",
            "protocol",
            "address",
            "port",
            "latency_ms",
            "download_mbps",
            "upload_mbps",
            "download_bps",
            "upload_bps",
            "ok",
            "error",
        ]
    )
    for row in db.export_rows():
        down = row["download_bps"]
        up = row["upload_bps"]
        writer.writerow(
            [
                row["tested_at"],
                row["name"],
                row["protocol"],
                row["address"],
                row["port"],
                "" if row["latency_ms"] is None else round(row["latency_ms"], 1),
                "" if down is None else round(down * 8 / 1_000_000, 3),
                "" if up is None else round(up * 8 / 1_000_000, 3),
                "" if down is None else round(down, 1),
                "" if up is None else round(up, 1),
                row["ok"],
                row["error"],
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=xray-checker.csv"},
    )


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", NoCacheStatic(directory=str(STATIC_DIR)), name="static")


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
