"""Очередь проверок: одна проверка за раз, несколько узлов параллельно по настройке."""

from __future__ import annotations

import asyncio
import logging
import time

from app import db, subscription
from app.engines import CancelToken, ProbeResult, Stage, test_node
from app.i18n import msg, render
from app.parser import parse_link

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
        source_ids: list[int] | None = None,
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
            "current_ids": [],
            "current_stages": [],
            "current_stage_started": [],
            "phase": "preparing",
            "started_at": db.utcnow(),
        }
        self._task = asyncio.create_task(
            self._execute_and_release(trigger, node_ids, include_disabled, source_ids)
        )
        return True

    async def begin_and_wait(self, trigger: str, source_ids: list[int] | None = None) -> bool:
        started = await self.begin(trigger, None, False, source_ids)
        if not started or self._task is None:
            return False
        await self._task
        return True

    def cancel(self) -> None:
        token = self.cancel_token
        if token is not None:
            token.cancel()
        if self.progress is not None:
            self.progress["phase"] = "stopping"

    async def _execute_and_release(
        self,
        trigger: str,
        node_ids: list[str] | None,
        include_disabled: bool,
        source_ids: list[int] | None = None,
    ) -> None:
        try:
            await self._execute(trigger, node_ids, include_disabled, source_ids)
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
        source_ids: list[int] | None = None,
    ) -> None:
        token = CancelToken()
        self.cancel_token = token
        settings = db.public_settings()
        # Проверка по расписанию касается только своих источников; ручная — всех.
        scope = [source for source in db.list_sources() if source_ids is None or source["id"] in source_ids]
        stale = [source["id"] for source in scope if source["kind"] == "subscription" and source["refresh_before_run"]]
        refresh_error = ""
        if stale:
            self._phase("refreshing")
            errors = await asyncio.to_thread(subscription.refresh_many, stale)
            # Часть подписок не обновилась: проверка идёт по прежним узлам, а причина видна в прогоне.
            refresh_error = "; ".join(errors)
            if refresh_error:
                logger.warning("subscription refresh failed: %s", render(refresh_error))
        if token.cancelled:
            return
        rows = await asyncio.to_thread(db.nodes_for_run, node_ids, include_disabled, source_ids)
        labels = [subscription.source_label(source) for source in scope] if source_ids is not None else None
        run_id = db.create_run(trigger, len(rows), labels)
        self.progress = {
            "running": True,
            "run_id": run_id,
            "trigger": trigger,
            "total": len(rows),
            "done": 0,
            "ok": 0,
            "fail": 0,
            "current": [],
            "current_ids": [],
            "current_stages": [],
            "current_stage_started": [],
            "phase": "checking",
            "started_at": db.utcnow(),
        }
        ok_count = 0
        fail_count = 0
        status = "done"
        error = ""
        try:
            if not rows:
                status = "failed"
                error = refresh_error or msg("no_nodes_to_check")
                return
            if refresh_error:
                error = f"{msg('subscription_not_refreshed')}: {refresh_error}"
            semaphore = asyncio.Semaphore(max(1, int(settings["concurrency"])))
            # Имена идут в подпись прогресса, id нужны интерфейсу: имена в подписке могут повторяться.
            current: dict[str, str] = {}
            stages: dict[str, str] = {}
            # Начало текущего этапа узла: по нему интерфейс досчитывает полосу между опросами.
            started: dict[str, float] = {}
            loop = asyncio.get_running_loop()

            def set_stage(node_id: str, stage: str) -> None:
                # Этап мог прийти из потока уже после того, как узел закончен.
                if node_id in current:
                    stages[node_id] = stage
                    started[node_id] = time.time()
                    self._publish(current, stages, started, ok_count, fail_count)

            async def one(row) -> None:
                nonlocal ok_count, fail_count
                async with semaphore:
                    if token.cancelled:
                        return
                    current[row["id"]] = row["name"]
                    started[row["id"]] = time.time()
                    self._publish(current, stages, started, ok_count, fail_count)

                    def stage(name: str) -> None:
                        loop.call_soon_threadsafe(set_stage, row["id"], name)

                    try:
                        probe = await self._probe(row, settings, token, stage)
                        if token.cancelled and not probe.ok:
                            # Прерванный замер ничего не говорит об узле.
                            current.pop(row["id"], None)
                            stages.pop(row["id"], None)
                            started.pop(row["id"], None)
                            self._publish(current, stages, started, ok_count, fail_count)
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
                    current.pop(row["id"], None)
                    stages.pop(row["id"], None)
                    started.pop(row["id"], None)
                    self._publish(current, stages, started, ok_count, fail_count)

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

    async def _probe(self, row, settings: dict, token: CancelToken, stage: Stage) -> ProbeResult:
        try:
            node = parse_link(row["link"], insecure_if_no_sni=settings["tls_insecure_if_no_sni"])
        except Exception as exc:
            return ProbeResult(error=f"{msg('link_parse_failed')}: {exc}")
        logger.info("probe %s via %s", row["name"], node.engine or node.protocol)
        try:
            return await asyncio.to_thread(test_node, node, settings, token, stage)
        except Exception as exc:
            logger.exception("probe crashed for %s", row["name"])
            return ProbeResult(error=str(exc)[:300])

    def _phase(self, phase: str) -> None:
        if self.progress is not None:
            self.progress["phase"] = phase

    def _publish(
        self,
        current: dict[str, str],
        stages: dict[str, str],
        started: dict[str, float],
        ok_count: int,
        fail_count: int,
    ) -> None:
        if self.progress is None:
            return
        order = sorted(current, key=lambda node_id: (current[node_id], node_id))
        self.progress["current"] = [current[node_id] for node_id in order]
        # id, этап и время начала этапа стоят на той же позиции, что и имя в current.
        self.progress["current_ids"] = order
        self.progress["current_stages"] = [stages.get(node_id, "") for node_id in order]
        self.progress["current_stage_started"] = [started.get(node_id) for node_id in order]
        self.progress["done"] = ok_count + fail_count
        self.progress["ok"] = ok_count
        self.progress["fail"] = fail_count
        self.progress["phase"] = "stopping" if self.cancel_token and self.cancel_token.cancelled else "checking"
