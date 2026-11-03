"""Cron из пяти полей: минута, час, день месяца, месяц, день недели."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.i18n import msg

MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAY_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
# Поиск идёт по дням. 29 февраля в понедельник бывает раз в 28 лет, дальше выражение считаем невыполнимым.
SEARCH_DAYS = 366 * 28


class CronError(ValueError):
    pass


@dataclass(frozen=True)
class Cron:
    minutes: tuple[int, ...]
    hours: tuple[int, ...]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    any_day: bool
    any_weekday: bool

    def day_matches(self, day) -> bool:
        if day.month not in self.months:
            return False
        in_days = day.day in self.days
        # Python: понедельник 0. Cron: воскресенье 0.
        in_weekdays = (day.weekday() + 1) % 7 in self.weekdays
        # Как в Vixie cron: если заданы оба поля дня, хватает совпадения любого.
        if self.any_day or self.any_weekday:
            return in_days and in_weekdays
        return in_days or in_weekdays


def parse_cron(text: str) -> Cron:
    parts = text.split()
    if len(parts) != 5:
        raise CronError(msg("cron_field_count"))
    minutes = _field(parts[0], 0, 59)
    hours = _field(parts[1], 0, 23)
    days = _field(parts[2], 1, 31)
    months = _field(parts[3], 1, 12, MONTH_NAMES, 1)
    weekdays = {value % 7 for value in _field(parts[4], 0, 7, WEEKDAY_NAMES, 0)}
    return Cron(
        minutes=tuple(sorted(minutes)),
        hours=tuple(sorted(hours)),
        days=frozenset(days),
        months=frozenset(months),
        weekdays=frozenset(weekdays),
        any_day=parts[2].startswith("*"),
        any_weekday=parts[4].startswith("*"),
    )


def _field(text: str, low: int, high: int, names: list[str] | None = None, first: int = 0) -> set[int]:
    values: set[int] = set()
    for item in text.split(","):
        body, slash, step_text = item.partition("/")
        step = _number(step_text, item) if slash else 1
        if step < 1:
            raise CronError(msg("cron_invalid", part=item))
        if body == "*":
            start, end = low, high
        elif "-" in body:
            left, _, right = body.partition("-")
            start, end = _value(left, names, first, item), _value(right, names, first, item)
        else:
            start = _value(body, names, first, item)
            # «5/15» значит «с 5 до конца с шагом 15».
            end = high if slash else start
        if not low <= start <= end <= high:
            raise CronError(msg("cron_invalid", part=item))
        values.update(range(start, end + 1, step))
    return values


def _value(text: str, names: list[str] | None, first: int, item: str) -> int:
    if names and text.lower() in names:
        return names.index(text.lower()) + first
    return _number(text, item)


def _number(text: str, item: str) -> int:
    if not text.isdigit():
        raise CronError(msg("cron_invalid", part=item))
    return int(text)


def zone(name: str) -> tzinfo:
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise CronError(msg("invalid_timezone", name=name)) from exc


def next_after(cron: Cron, after: float, tz: tzinfo) -> float:
    """Первый запуск строго позже after. Время сравнивается по часам пояса, чтобы переход на летнее не сдвигал расписание."""
    start = datetime.fromtimestamp(after, tz).replace(tzinfo=None, second=0, microsecond=0) + timedelta(minutes=1)
    day = start.date()
    for _ in range(SEARCH_DAYS):
        if cron.day_matches(day):
            for hour in cron.hours:
                for minute in cron.minutes:
                    candidate = datetime(day.year, day.month, day.day, hour, minute)
                    if candidate >= start:
                        return candidate.replace(tzinfo=tz).timestamp()
        day += timedelta(days=1)
    raise CronError(msg("cron_never"))
