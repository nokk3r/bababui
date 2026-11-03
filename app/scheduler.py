"""Периодический запуск проверки."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from app import db
from app.cron import CronError, next_after, parse_cron, zone
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
        if self.next_at is not None and time.time() >= self.next_at:
            db.set_meta("last_schedule_at", db.utcnow())
            try:
                await self.runner.begin_and_wait("schedule")
            except Exception:
                logger.exception("scheduled run failed")
            self.next_at = next_run_at()


def next_run_at() -> float | None:
    settings = db.public_settings()
    last = last_started()
    now = time.time()
    if settings["schedule_mode"] == "cron":
        try:
            cron = parse_cron(settings["cron_expression"])
            # Пропущенные запуски не догоняются: после простоя проверка не стартует сразу,
            # а ждёт ближайшего времени по расписанию. Минута запаса — чтобы не проскочить текущую.
            return next_after(cron, max(last or 0, now - 60), zone(settings["schedule_timezone"]))
        except CronError:
            logger.warning("bad cron expression: %s", settings["cron_expression"])
            return None
    if last is None:
        return now + 8
    return last + max(1, int(settings["interval_minutes"])) * 60


def last_started() -> float | None:
    last = db.last_scheduled_at()
    if not last:
        return None
    try:
        return datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None
