"""Запуск проверок по расписанию: у каждого источника своё."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from app import db
from app.cron import CronError, next_after, parse_cron, zone
from app.runner import Runner
from app.subscription import source_label

logger = logging.getLogger("checker.scheduler")

# Первая проверка нового источника — через несколько секунд после появления, а не сразу посреди сохранения.
FIRST_DELAY = 8


class Scheduler:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        # Ближайший срок среди всех источников и сроки каждого: их показывает интерфейс.
        self.next_at: float | None = None
        self.next_sources: list[str] = []
        self.plan: dict[int, float] = {}
        # Источники по расписанию, которым нечего проверять: срока у них нет, интерфейс пишет «проверять нечего».
        self.idle: set[int] = set()
        # Первый запуск источника назначается один раз. Иначе «через 8 секунд» пересчитывается каждый такт,
        # срок всё время впереди и проверка не начинается.
        self._first: dict[int, float] = {}
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def loop(self) -> None:
        while not self._stop:
            await self.tick()
            await asyncio.sleep(1)

    async def tick(self) -> None:
        sources = self.update_plan()
        if not self.plan or self.runner.busy():
            # Пока идёт другая проверка, источники со сроком ждут: замеры делят один канал, параллельно нечестно.
            return
        now = time.time()
        due = [source for source in sources if self.plan.get(source["id"], now + 1) <= now]
        if not due:
            return
        ids = [source["id"] for source in due]
        db.mark_scheduled(ids, db.utcnow())
        for source_id in ids:
            self._first.pop(source_id, None)
        try:
            await self.runner.begin_and_wait("schedule", source_ids=ids)
        except Exception:
            logger.exception("scheduled run failed")
        self.update_plan()

    def update_plan(self) -> list[dict]:
        """Сроки всех источников. Зовётся каждый такт и при запросе списка источников, чтобы срок после правки был виден сразу."""
        sources = [source for source in db.list_sources() if source["schedule_enabled"]]
        now = time.time()
        plan: dict[int, float] = {}
        checkable = db.checkable_counts()
        idle: set[int] = set()
        for source in sources:
            # Без включённых узлов проверка вышла бы пустым прогоном с ошибкой в истории. Исключение —
            # подписка, которая обновляется перед проверкой: обновление может как раз вернуть узлы.
            refreshes = source["kind"] == "subscription" and source["refresh_before_run"]
            if not checkable.get(source["id"]) and not refreshes:
                idle.add(source["id"])
                continue
            first = self._first.get(source["id"])
            at = next_run_at(source, now, first)
            if at is None:
                continue
            if not source["last_scheduled_at"] and source["schedule_mode"] != "cron":
                self._first[source["id"]] = at
            plan[source["id"]] = at
        self.plan = plan
        self.idle = idle
        self.next_at = min(plan.values()) if plan else None
        self.next_sources = [source_label(source) for source in sources if plan.get(source["id"]) == self.next_at]
        return sources


def next_run_at(source: dict, now: float | None = None, first: float | None = None) -> float | None:
    """Срок следующей проверки источника. Пропущенные запуски не догоняются."""
    now = time.time() if now is None else now
    last = parse_stamp(source.get("last_scheduled_at"))
    if source["schedule_mode"] == "cron":
        try:
            cron = parse_cron(source["cron_expression"])
            # После простоя проверка не стартует сразу, а ждёт ближайшего времени по расписанию.
            # Минута запаса — чтобы не проскочить текущую.
            return next_after(cron, max(last or 0, now - 60), zone(source["schedule_timezone"]))
        except CronError:
            logger.warning("bad cron expression for source %s: %s", source["id"], source["cron_expression"])
            return None
    if last is None:
        return first if first is not None else now + FIRST_DELAY
    return last + max(1, int(source["interval_minutes"])) * 60


def parse_stamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None
