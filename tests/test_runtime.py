import asyncio
import base64
import dataclasses
import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app import db, subscription
from app.engines import ProbeResult
from app.parser import parse_link, parse_subscription
from app.runner import Runner
from app.scheduler import Scheduler, next_run_at

UUID = "11111111-1111-1111-1111-111111111111"


def vless(host: str, name: str, sni: str = "a.com") -> str:
    return f"vless://{UUID}@{host}:443?security=tls&type=tcp&sni={sni}#{name}"


def b64(*links: str) -> str:
    return base64.b64encode(("\n".join(links) + "\n").encode()).decode()


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(db, "DATA_DIR", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()


class SubscriptionTests(DatabaseCase):
    def refresh(self, *bodies: str) -> list[str]:
        db.set_meta("subscription_url", "\n".join(f"https://example.com/{i}" for i in range(len(bodies))))
        replies = [(body, "") for body in bodies]
        with mock.patch.object(subscription, "fetch", side_effect=replies):
            subscription.refresh()
        return [node["name"] for node in db.list_nodes()]

    def test_padded_base64_keeps_second_subscription(self):
        first = b64(vless("1.1.1.1", "a"))
        self.assertTrue(first.endswith("="))
        self.assertEqual(self.refresh(first, b64(vless("2.2.2.2", "b"))), ["a", "b"])

    def test_plain_and_base64_are_merged(self):
        self.assertEqual(self.refresh(vless("1.1.1.1", "a"), b64(vless("2.2.2.2", "b"))), ["a", "b"])


class NodeIdentityTests(DatabaseCase):
    def test_different_sni_are_separate_nodes(self):
        links = vless("1.1.1.1", "x", "a.com") + "\n" + vless("1.1.1.1", "y", "b.com")
        self.assertEqual([node.name for node in parse_subscription(links)], ["x", "y"])

    def test_id_without_new_fields_is_unchanged(self):
        node = parse_link(f"vless://{UUID}@1.1.1.1:443?security=none&type=tcp#plain")
        self.assertEqual(node.id, node.legacy_id)

    def test_sync_moves_history_and_flag_to_new_id(self):
        node = parse_link(vless("1.1.1.1", "x"))
        old = dataclasses.replace(node, id=node.legacy_id, legacy_id="")
        db.sync_nodes([old])
        db.set_enabled(old.id, False)
        db.insert_result(db.create_run("manual", 1), old.id, ProbeResult(ok=True, download_bps=5.0))

        db.sync_nodes([node])

        rows = db.list_nodes()
        self.assertEqual([row["id"] for row in rows], [node.id])
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["download_bps"], 5.0)

    def test_sync_does_not_take_row_of_listed_node(self):
        node = parse_link(vless("1.1.1.1", "x"))
        plain = dataclasses.replace(node, id=node.legacy_id, legacy_id="", name="plain")
        db.sync_nodes([plain])
        db.sync_nodes([plain, node])
        self.assertEqual({row["id"] for row in db.list_nodes()}, {plain.id, node.id})


class SchedulerTests(DatabaseCase):
    def test_manual_run_does_not_shift_schedule(self):
        db.set_meta("last_schedule_at", "2026-01-01T00:00:00Z")
        before = next_run_at()
        db.create_run("manual", 1)
        self.assertEqual(next_run_at(), before)

    def test_clear_history_does_not_start_check(self):
        db.set_meta("last_schedule_at", db.utcnow())
        db.clear_history()
        self.assertGreater(next_run_at(), time.time() + 3600)

    def test_old_database_uses_scheduled_run(self):
        db.create_run("schedule", 1)
        self.assertGreater(next_run_at(), time.time() + 3600)

    def test_no_link_means_no_run(self):
        scheduler = Scheduler(Runner())
        asyncio.run(scheduler.tick())
        self.assertIsNone(scheduler.next_at)
        self.assertEqual(db.list_runs(1), [])

    def test_due_run_is_started_and_remembered(self):
        db.save_settings({"subscription_url": "https://example.com/sub", "refresh_before_run": False})
        db.set_meta("last_schedule_at", "2026-01-01T00:00:00Z")
        asyncio.run(Scheduler(Runner()).tick())
        self.assertEqual(db.list_runs(1)[0]["trigger"], "schedule")
        self.assertGreater(next_run_at(), time.time() + 3600)


class CancelTests(DatabaseCase):
    def test_cancelled_probe_keeps_last_result(self):
        db.save_settings({"refresh_before_run": False})
        node = parse_link(vless("1.1.1.1", "x"))
        db.sync_nodes([node])
        db.insert_result(db.create_run("manual", 1), node.id, ProbeResult(ok=True, download_bps=5.0))

        def stopped(_node, _settings, token):
            token.cancel()
            return ProbeResult(error="остановлено")

        async def run():
            runner = Runner()
            await runner.begin("manual", None, False)
            await runner._task

        with mock.patch("app.runner.test_node", stopped):
            asyncio.run(run())

        row = db.list_nodes()[0]
        self.assertTrue(row["last_ok"])
        self.assertEqual(row["download_bps"], 5.0)
        self.assertEqual(db.list_runs(1)[0]["status"], "cancelled")


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "нужен fastapi")
class AuthTests(unittest.TestCase):
    def check(self, password: str, header: str | None) -> None:
        from app import main

        with mock.patch.object(main, "WEB_PASSWORD", password):
            main.require_auth(header)

    def test_non_ascii_password(self):
        self.check("пароль", "Bearer %D0%BF%D0%B0%D1%80%D0%BE%D0%BB%D1%8C")

    def test_percent_in_password_survives_encoding(self):
        self.check("100%41", "Bearer 100%2541")

    def test_wrong_password_is_rejected(self):
        from fastapi import HTTPException

        for header in ("Bearer %D0%BF", "Bearer пароль-но-длиннее", None):
            with self.assertRaises(HTTPException):
                self.check("пароль", header)


if __name__ == "__main__":
    unittest.main()
