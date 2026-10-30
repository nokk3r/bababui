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
            await self.tick()
            await asyncio.sleep(1)

    async def tick(self) -> None:
        settings = db.public_settings()
        if not settings["scheduler_enabled"] or not settings["subscription_url"] or self.runner.busy():
            self.next_at = None
            return
        self.next_at = next_run_at()
        if time.time() >= self.next_at:
            db.set_meta("last_schedule_at", db.utcnow())
            try:
                await self.runner.begin_and_wait("schedule")
            except Exception:
                logger.exception("scheduled run failed")
            self.next_at = next_run_at()


def next_run_at() -> float:
    interval = max(1, int(db.public_settings()["interval_minutes"])) * 60
    last = db.last_scheduled_at()
    now = time.time()
    if not last:
        return now + 8
    try:
        started = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return now + 8
    return started.timestamp() + interval
