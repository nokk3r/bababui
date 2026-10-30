"""Периодический запуск проверки."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from app import db
from app.runner import Runner

logger = logging.getLogger("checker.scheduler")


class Scheduler:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.next_at: float | None = None
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def loop(self) -> None:
        while not self._stop:
            settings = db.public_settings()
            if not settings["scheduler_enabled"] or self.runner.busy():
                self.next_at = None
            else:
                self.next_at = next_run_at()
                if time.time() >= self.next_at:
                    try:
                        await self.runner.begin_and_wait("schedule")
                    except Exception:
                        logger.exception("scheduled run failed")
                    self.next_at = next_run_at()
            await asyncio.sleep(1)


def next_run_at() -> float:
    interval = max(1, int(db.public_settings()["interval_minutes"])) * 60
    runs = db.list_runs(1)
    now = time.time()
    if not runs or not runs[0].get("started_at"):
        return now + 8
    try:
        started = datetime.strptime(runs[0]["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return now + 8
    return started.timestamp() + interval
