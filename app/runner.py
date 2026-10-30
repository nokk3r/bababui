"""Очередь проверок: одна проверка за раз, несколько узлов параллельно по настройке."""

from __future__ import annotations

import asyncio
import logging

from app import db, subscription
from app.engines import CancelToken, ProbeResult, test_node
from app.parser import parse_link
from app.subscription import SubscriptionError

logger = logging.getLogger("checker.runner")


class Runner:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.progress: dict | None = None
        self.cancel_token: CancelToken | None = None

    def busy(self) -> bool:
        return self._lock.locked()

    async def begin(
        self,
        trigger: str,
        node_ids: list[str] | None,
        include_disabled: bool,
    ) -> bool:
        try:
            await asyncio.wait_for(self._lock.acquire(), 0.05)
        except asyncio.TimeoutError:
            return False
        self.progress = {
            "running": True,
            "run_id": None,
            "trigger": trigger,
            "total": 0,
            "done": 0,
            "ok": 0,
            "fail": 0,
            "current": [],
            "phase": "подготовка",
            "started_at": db.utcnow(),
        }
        self._task = asyncio.create_task(
            self._execute_and_release(trigger, node_ids, include_disabled)
        )
        return True

    async def begin_and_wait(self, trigger: str) -> bool:
        started = await self.begin(trigger, None, False)
        if not started or self._task is None:
            return False
        await self._task
        return True

    def cancel(self) -> None:
        token = self.cancel_token
        if token is not None:
            token.cancel()
        if self.progress is not None:
            self.progress["phase"] = "остановка"

    async def _execute_and_release(
        self,
        trigger: str,
        node_ids: list[str] | None,
        include_disabled: bool,
    ) -> None:
        try:
            await self._execute(trigger, node_ids, include_disabled)
        except Exception:
            logger.exception("run failed")
        finally:
            self.progress = None
            self.cancel_token = None
            self._lock.release()

    async def _execute(
        self,
        trigger: str,
        node_ids: list[str] | None,
        include_disabled: bool,
    ) -> None:
        token = CancelToken()
        self.cancel_token = token
        settings = db.public_settings()
        refresh_error = ""
        if settings["refresh_before_run"]:
            self._phase("обновление подписки")
            try:
                await asyncio.to_thread(subscription.refresh)
            except SubscriptionError as exc:
                refresh_error = str(exc)
                logger.warning("subscription refresh failed: %s", exc)
            settings = db.public_settings()
        if token.cancelled:
            return
        rows = await asyncio.to_thread(db.nodes_for_run, node_ids, include_disabled)
        run_id = db.create_run(trigger, len(rows))
        self.progress = {
            "running": True,
            "run_id": run_id,
            "trigger": trigger,
            "total": len(rows),
            "done": 0,
            "ok": 0,
            "fail": 0,
            "current": [],
            "phase": "проверка",
            "started_at": db.utcnow(),
        }
        ok_count = 0
        fail_count = 0
        status = "done"
        error = ""
        try:
            if not rows:
                status = "failed"
                error = refresh_error or "Нет узлов для проверки"
                return
            if refresh_error:
                error = f"Подписка не обновилась: {refresh_error}"
            semaphore = asyncio.Semaphore(max(1, int(settings["concurrency"])))
            current: set[str] = set()

            async def one(row) -> None:
                nonlocal ok_count, fail_count
                async with semaphore:
                    if token.cancelled:
                        return
                    current.add(row["name"])
                    self._publish(current, ok_count, fail_count)
                    try:
                        probe = await self._probe(row, settings, token)
                        if token.cancelled and not probe.ok:
                            # Прерванный замер ничего не говорит об узле.
                            current.discard(row["name"])
                            self._publish(current, ok_count, fail_count)
                            return
                        db.insert_result(run_id, row["id"], probe)
                    except Exception as exc:
                        logger.exception("node failed %s", row["name"])
                        probe = ProbeResult(error=str(exc)[:300])
                        try:
                            db.insert_result(run_id, row["id"], probe)
                        except Exception:
                            logger.exception("result insert failed")
                    if probe.ok:
                        ok_count += 1
                    else:
                        fail_count += 1
                    current.discard(row["name"])
                    self._publish(current, ok_count, fail_count)

            await asyncio.gather(*(one(row) for row in rows))
            if token.cancelled:
                status = "cancelled"
        except Exception as exc:
            logger.exception("run %s failed", run_id)
            status = "failed"
            error = str(exc)[:500]
        finally:
            db.finish_run(run_id, status, ok_count, fail_count, error)
            try:
                db.purge_old(int(settings["retention_days"]))
            except Exception:
                logger.exception("purge failed")

    async def _probe(self, row, settings: dict, token: CancelToken) -> ProbeResult:
        try:
            node = parse_link(row["link"], insecure_if_no_sni=settings["tls_insecure_if_no_sni"])
        except Exception as exc:
            return ProbeResult(error=f"Не удалось разобрать ссылку: {exc}")
        logger.info("probe %s via %s", row["name"], node.engine or node.protocol)
        try:
            return await asyncio.to_thread(test_node, node, settings, token)
        except Exception as exc:
            logger.exception("probe crashed for %s", row["name"])
            return ProbeResult(error=str(exc)[:300])

    def _phase(self, phase: str) -> None:
        if self.progress is not None:
            self.progress["phase"] = phase

    def _publish(self, current: set[str], ok_count: int, fail_count: int) -> None:
        if self.progress is None:
            return
        self.progress["current"] = sorted(current)
        self.progress["done"] = ok_count + fail_count
        self.progress["ok"] = ok_count
        self.progress["fail"] = fail_count
        self.progress["phase"] = "остановка" if self.cancel_token and self.cancel_token.cancelled else "проверка"
