import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from app import db
from app.cron import CronError, next_after, parse_cron, zone
from app.scheduler import next_run_at

UTC = timezone.utc


def at(text: str, tz=UTC) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=tz).timestamp()


def following(expression: str, after: str, tz=UTC) -> str:
    stamp = next_after(parse_cron(expression), at(after, tz), tz)
    return datetime.fromtimestamp(stamp, tz).strftime("%Y-%m-%d %H:%M")


class ParseTests(unittest.TestCase):
    def test_lists_ranges_steps_and_names(self):
        cron = parse_cron("*/15 9-17/4 1,15 jan-mar MON-fri")
        self.assertEqual(cron.minutes, (0, 15, 30, 45))
        self.assertEqual(cron.hours, (9, 13, 17))
        self.assertEqual(cron.days, {1, 15})
        self.assertEqual(cron.months, {1, 2, 3})
        self.assertEqual(cron.weekdays, {1, 2, 3, 4, 5})

    def test_start_with_step_runs_to_the_end(self):
        self.assertEqual(parse_cron("50/5 * * * *").minutes, (50, 55))

    def test_sunday_is_zero_and_seven(self):
        self.assertEqual(parse_cron("0 0 * * 7").weekdays, {0})

    def test_bad_expressions_are_rejected(self):
        for expression in ("* * * *", "60 * * * *", "* * 0 * *", "*/0 * * * *", "5-1 * * * *", "a * * * *", "* * * 13 *"):
            with self.subTest(expression), self.assertRaises(CronError):
                parse_cron(expression)


class NextTests(unittest.TestCase):
    def test_next_is_strictly_after(self):
        self.assertEqual(following("0 */2 * * *", "2026-11-03 10:00:00"), "2026-11-03 12:00")
        self.assertEqual(following("0 */2 * * *", "2026-11-03 10:59:59"), "2026-11-03 12:00")
        self.assertEqual(following("* * * * *", "2026-11-03 10:00:30"), "2026-11-03 10:01")

    def test_weekdays_skip_weekend(self):
        # 2026-11-06 — пятница.
        self.assertEqual(following("30 9 * * 1-5", "2026-11-06 10:00:00"), "2026-11-09 09:30")

    def test_day_and_weekday_match_either(self):
        # 1-е число или воскресенье: 2026-11-08 — воскресенье, оно раньше 1 декабря.
        self.assertEqual(following("0 0 1 * 0", "2026-11-02 00:00:00"), "2026-11-08 00:00")

    def test_leap_day(self):
        self.assertEqual(following("0 0 29 2 *", "2026-03-01 00:00:00"), "2028-02-29 00:00")

    def test_impossible_date_never_runs(self):
        with self.assertRaises(CronError):
            next_after(parse_cron("0 0 31 2 *"), at("2026-01-01 00:00:00"), UTC)

    def test_time_is_read_in_zone(self):
        moscow = ZoneInfo("Europe/Moscow")
        # 05:00 UTC — это 08:00 в Москве, ближайшие 9:30 по Москве — 06:30 UTC того же дня.
        stamp = next_after(parse_cron("30 9 * * *"), at("2026-11-03 05:00:00"), moscow)
        self.assertEqual(stamp, at("2026-11-03 06:30:00"))

    def test_unknown_zone(self):
        with self.assertRaises(CronError):
            zone("Mars/Olympus")
        self.assertIs(zone(""), UTC)


class SchedulerCronTests(unittest.TestCase):
    def source(self, **values) -> dict:
        base = {"id": 1, "schedule_mode": "cron", "cron_expression": "0 3 * * *", "schedule_timezone": "",
                "interval_minutes": 120, "last_scheduled_at": ""}
        return {**base, **values}

    def next_at(self, now: str, last: str = "") -> str:
        stamp = next_run_at(self.source(last_scheduled_at=last), at(now))
        return datetime.fromtimestamp(stamp, UTC).strftime("%Y-%m-%d %H:%M")

    def test_missed_run_is_not_caught_up(self):
        self.assertEqual(self.next_at("2026-11-03 10:00:00", "2026-11-01T03:00:00Z"), "2026-11-04 03:00")

    def test_current_minute_still_runs(self):
        self.assertEqual(self.next_at("2026-11-03 03:00:20", "2026-11-02T03:00:00Z"), "2026-11-03 03:00")

    def test_finished_run_waits_for_next_time(self):
        self.assertEqual(self.next_at("2026-11-03 03:00:20", "2026-11-03T03:00:00Z"), "2026-11-04 03:00")

    def test_bad_expression_stops_schedule(self):
        self.assertIsNone(next_run_at(self.source(cron_expression="nope")))

    def test_interval_mode_is_unchanged(self):
        source = self.source(schedule_mode="interval", interval_minutes=60, last_scheduled_at="2026-11-03T03:00:00Z")
        self.assertEqual(next_run_at(source), at("2026-11-03 04:00:00"))


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "нужен fastapi")
class SettingsValidationTests(unittest.TestCase):
    def settings(self, **values):
        from app.main import SourceIn

        return SourceIn(kind="group", **values)

    def test_cron_mode_checks_expression(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            self.settings(schedule_mode="cron", cron_expression="0 0 31 2 *")
        saved = self.settings(schedule_mode="cron", cron_expression=" 0   3 * * * ", schedule_timezone="Europe/Moscow")
        self.assertEqual(saved.cron_expression, "0 3 * * *")

    def test_interval_mode_keeps_unfinished_expression(self):
        self.assertEqual(self.settings(cron_expression="0 3").cron_expression, "0 3")


if __name__ == "__main__":
    unittest.main()
