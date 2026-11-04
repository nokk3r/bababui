import asyncio
import base64
import dataclasses
import importlib.util
import tempfile
import threading
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
        for i in range(len(bodies)):
            db.create_source("subscription", "", f"https://example.com/{i}", "", True)
        replies = [(body, {}) for body in bodies]
        with mock.patch.object(subscription, "fetch", side_effect=replies):
            subscription.refresh_all()
        return [node["name"] for node in db.list_nodes()]

    def test_padded_base64_keeps_second_subscription(self):
        first = b64(vless("1.1.1.1", "a"))
        self.assertTrue(first.endswith("="))
        self.assertEqual(self.refresh(first, b64(vless("2.2.2.2", "b"))), ["a", "b"])

    def test_plain_and_base64_are_merged(self):
        self.assertEqual(self.refresh(vless("1.1.1.1", "a"), b64(vless("2.2.2.2", "b"))), ["a", "b"])

    def test_group_is_parsed_without_fetching(self):
        group = db.create_source("group", "", "", f"{vless('1.1.1.1', 'a')}\n{vless('2.2.2.2', 'b')}", True)
        with mock.patch.object(subscription, "fetch") as fetch:
            self.assertEqual(subscription.refresh_source(group), 2)
        fetch.assert_not_called()
        self.assertEqual({node["name"]: node["sources"] for node in db.list_nodes()}, {"a": [group], "b": [group]})

    def test_broken_subscription_keeps_others(self):
        good = db.create_source("subscription", "", "https://example.com/good", "", True)
        bad = db.create_source("subscription", "", "https://example.com/bad", "", True)
        replies = [(vless("1.1.1.1", "a"), {}), subscription.SubscriptionError("[[subscription_http|{\"code\": 404}]]")]
        with mock.patch.object(subscription, "fetch", side_effect=replies):
            count, errors = subscription.refresh_all()
        self.assertEqual(count, 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(db.get_source(good)["error"], "")
        self.assertIn("subscription_http", db.get_source(bad)["error"])

    def test_node_stays_while_any_source_has_it(self):
        shared = vless("1.1.1.1", "shared")
        first = db.create_source("group", "", "", shared, True)
        second = db.create_source("group", "", "", f"{shared}\n{vless('2.2.2.2', 'own')}", True)
        subscription.refresh_all()
        db.update_source(second, "", "", "", True)
        subscription.refresh_source(second)
        self.assertEqual({node["name"]: node["active"] for node in db.list_nodes()}, {"shared": True, "own": False})
        db.delete_source(first)
        self.assertFalse(db.list_nodes()[0]["active"])

    def test_group_toggle_touches_only_its_nodes(self):
        first = db.create_source("group", "", "", vless("1.1.1.1", "a"), True)
        db.create_source("group", "", "", vless("2.2.2.2", "b"), True)
        subscription.refresh_all()
        db.set_source_enabled(first, False)
        self.assertEqual({node["name"]: node["enabled"] for node in db.list_nodes()}, {"a": False, "b": True})

    def test_profile_title_header(self):
        self.assertEqual(subscription.profile_title("base64:" + base64.b64encode("Мой VPN".encode()).decode()), "Мой VPN")
        self.assertEqual(subscription.profile_title("Мой VPN".encode().decode("latin-1")), "Мой VPN")

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "нужен fastapi")
    def test_source_form_validation(self):
        from pydantic import ValidationError

        from app.main import SourceIn

        self.assertEqual(SourceIn(kind="subscription", url=" https://example.com/sub ").url, "https://example.com/sub")
        group = SourceIn(kind="group", links=f"\n {vless('1.1.1.1', 'a')}\n\nhy2://pass@2.2.2.2:443#b\n")
        self.assertEqual(group.links, f"{vless('1.1.1.1', 'a')}\nhy2://pass@2.2.2.2:443#b")
        for bad in (
            {"kind": "subscription", "url": "ftp://example.com/sub"},
            {"kind": "subscription", "url": "https://a.com/1\nhttps://a.com/2"},
            {"kind": "group", "links": "https://example.com/sub"},
            {"kind": "group", "links": "socks://1.1.1.1:1080"},
        ):
            with self.assertRaises(ValidationError):
                SourceIn(**bad)


class MigrationTests(DatabaseCase):
    def test_old_link_field_becomes_sources(self):
        node = parse_link(vless("1.1.1.1", "fed"))
        manual = vless("2.2.2.2", "manual")
        with db.connect() as conn:
            conn.execute("DELETE FROM sources")
            conn.execute("DELETE FROM settings WHERE key='sources_migrated'")
            conn.execute("UPDATE settings SET value=? WHERE key='subscription_url'", (f"https://example.com/sub\n{manual}",))
            conn.execute("UPDATE settings SET value='0' WHERE key='subscription_insecure'")
        db.sync_nodes(99, [node, parse_link(manual)])
        with db.connect() as conn:
            conn.execute("DELETE FROM source_nodes")
        db.init_db()
        feed, group = db.list_sources()
        self.assertEqual((feed["kind"], feed["url"], feed["insecure"]), ("subscription", "https://example.com/sub", False))
        self.assertEqual((group["kind"], group["links"]), ("group", manual))
        self.assertEqual({row["name"]: row["sources"] for row in db.list_nodes()}, {"fed": [feed["id"]], "manual": [group["id"]]})
        db.init_db()
        self.assertEqual(len(db.list_sources()), 2)


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
        db.sync_nodes(1, [old])
        db.set_enabled(old.id, False)
        db.insert_result(db.create_run("manual", 1), old.id, ProbeResult(ok=True, download_bps=5.0))

        db.sync_nodes(1, [node])

        rows = db.list_nodes()
        self.assertEqual([row["id"] for row in rows], [node.id])
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["download_bps"], 5.0)

    def test_sync_does_not_take_row_of_listed_node(self):
        node = parse_link(vless("1.1.1.1", "x"))
        plain = dataclasses.replace(node, id=node.legacy_id, legacy_id="", name="plain")
        db.sync_nodes(1, [plain])
        db.sync_nodes(1, [plain, node])
        self.assertEqual({row["id"] for row in db.list_nodes()}, {plain.id, node.id})


class RunOrderTests(DatabaseCase):
    def test_least_recently_checked_go_first(self):
        nodes = [parse_link(vless(f"1.1.1.{i}", name)) for i, name in enumerate(("a", "b", "c"))]
        db.sync_nodes(1, nodes)
        run_id = db.create_run("manual", 2)
        db.insert_result(run_id, nodes[0].id, ProbeResult(error="таймаут"))
        self.assertEqual([row["name"] for row in db.nodes_for_run(None, False)], ["b", "c", "a"])


class DeleteRunTests(DatabaseCase):
    def test_only_that_run_and_its_results_go(self):
        node = parse_link(vless("1.1.1.1", "x"))
        db.sync_nodes(1, [node])
        keep, drop = db.create_run("manual", 1), db.create_run("manual", 1)
        for run_id in (keep, drop):
            db.insert_result(run_id, node.id, ProbeResult(ok=True, download_bps=float(run_id)))
            db.finish_run(run_id, "done", 1, 0)

        self.assertTrue(db.delete_run(drop))

        self.assertEqual([run["id"] for run in db.list_runs(10)], [keep])
        self.assertEqual([row["download_bps"] for row in db.node_history(node.id, 10)], [float(keep)])
        self.assertFalse(db.delete_run(drop))

    def test_running_run_is_kept(self):
        run_id = db.create_run("manual", 1)
        self.assertFalse(db.delete_run(run_id))
        self.assertEqual(db.list_runs(1)[0]["id"], run_id)


class SchedulerTests(DatabaseCase):
    def source(self, kind="group", links="", **schedule) -> int:
        return db.create_source(kind, "", "https://example.com/sub" if kind == "subscription" else "", links, True, **schedule)

    def test_manual_run_does_not_shift_schedule(self):
        db.get_source(self.source())
        db.mark_scheduled([1], "2026-01-01T00:00:00Z")
        before = next_run_at(db.get_source(1))
        db.create_run("manual", 1)
        self.assertEqual(next_run_at(db.get_source(1)), before)

    def test_clear_history_does_not_start_check(self):
        source_id = self.source()
        db.mark_scheduled([source_id], db.utcnow())
        db.clear_history()
        self.assertGreater(next_run_at(db.get_source(source_id)), time.time() + 3600)

    def test_no_sources_means_no_run(self):
        scheduler = Scheduler(Runner())
        asyncio.run(scheduler.tick())
        self.assertIsNone(scheduler.next_at)
        self.assertEqual(db.list_runs(1), [])

    def test_old_global_pause_turns_off_every_schedule(self):
        first, second = self.source(), self.source()
        with db.connect() as conn:
            conn.execute("DELETE FROM settings WHERE key='global_pause_migrated'")
            conn.execute("UPDATE settings SET value='0' WHERE key='scheduler_enabled'")
        db.init_db()
        self.assertEqual([db.get_source(i)["schedule_enabled"] for i in (first, second)], [False, False])
        scheduler = Scheduler(Runner())
        asyncio.run(scheduler.tick())
        self.assertIsNone(scheduler.next_at)

    def test_history_stats(self):
        empty = db.history_stats()
        self.assertEqual((empty["results"], empty["runs"], empty["oldest"]), (0, 0, None))
        node = parse_link(vless("1.1.1.1", "x"))
        db.sync_nodes(1, [node])
        db.insert_result(db.create_run("manual", 1), node.id, ProbeResult(ok=True))
        stats = db.history_stats()
        self.assertEqual((stats["results"], stats["runs"]), (1, 1))
        self.assertIsNotNone(stats["oldest"])
        self.assertGreater(stats["bytes"], 0)

    def test_first_deadline_stays_put_until_the_run(self):
        self.source(links=vless("1.1.1.1", "x"), interval_minutes=1200)
        subscription.refresh_all()
        scheduler = Scheduler(Runner())
        clock = {"now": 1_700_000_000.0}

        def frozen() -> float:
            return clock["now"]

        with mock.patch("app.scheduler.time.time", side_effect=frozen):
            asyncio.run(scheduler.tick())
            first = scheduler.next_at
            self.assertEqual(first, clock["now"] + 8)
            clock["now"] += 3
            asyncio.run(scheduler.tick())
            self.assertEqual(scheduler.next_at, first)
            self.assertEqual(db.list_runs(1), [])
            clock["now"] = first
            asyncio.run(scheduler.tick())

        self.assertEqual(db.list_runs(1)[0]["trigger"], "schedule")
        self.assertGreater(scheduler.next_at, time.time() + 1190 * 60)

    def test_only_due_sources_run_and_are_remembered(self):
        due = self.source(links=vless("1.1.1.1", "due"), interval_minutes=60)
        later = self.source(links=vless("2.2.2.2", "later"), interval_minutes=60)
        subscription.refresh_all()
        db.mark_scheduled([due], "2026-01-01T00:00:00Z")
        db.mark_scheduled([later], db.utcnow())
        checked = []

        def probe(node, *_args):
            checked.append(node.name)
            return ProbeResult(ok=True)

        with mock.patch("app.runner.test_node", probe):
            asyncio.run(Scheduler(Runner()).tick())
        self.assertEqual(checked, ["due"])
        run = db.list_runs(1)[0]
        self.assertEqual((run["trigger"], run["total"]), ("schedule", 1))
        self.assertEqual(len(run["sources"]), 1)
        self.assertGreater(next_run_at(db.get_source(due)), time.time() + 3000)
        self.assertEqual(db.get_source(later)["last_scheduled_at"][:4], db.utcnow()[:4])

    def test_source_with_nothing_to_check_is_not_run(self):
        empty = self.source()
        off = self.source(links=vless("1.1.1.1", "off"))
        subscription.refresh_all()
        db.set_source_enabled(off, False)
        db.mark_scheduled([empty, off], "2026-01-01T00:00:00Z")
        scheduler = Scheduler(Runner())
        asyncio.run(scheduler.tick())
        self.assertEqual(db.list_runs(1), [])
        self.assertEqual(scheduler.idle, {empty, off})
        self.assertIsNone(scheduler.next_at)

    def test_empty_subscription_that_refreshes_still_runs(self):
        source_id = self.source(kind="subscription")
        scheduler = Scheduler(Runner())
        scheduler.update_plan()
        self.assertIn(source_id, scheduler.plan)

    def test_busy_runner_makes_due_sources_wait(self):
        source_id = self.source(links=vless("1.1.1.1", "x"))
        subscription.refresh_all()
        runner = Runner()
        with mock.patch.object(runner, "busy", return_value=True):
            scheduler = Scheduler(runner)
            with mock.patch("app.scheduler.time.time", return_value=time.time() + 60):
                asyncio.run(scheduler.tick())
        self.assertEqual(db.list_runs(1), [])
        self.assertIsNone(db.get_source(source_id)["last_scheduled_at"])
        self.assertIsNotNone(scheduler.next_at)

    def test_manual_source_run_checks_only_its_nodes(self):
        mine = self.source(links=f"{vless('1.1.1.1', 'a')}\n{vless('2.2.2.2', 'b')}")
        self.source(links=vless("3.3.3.3", "other"))
        subscription.refresh_all()
        checked = []

        def probe(node, *_args):
            checked.append(node.name)
            return ProbeResult(ok=True)

        with mock.patch("app.runner.test_node", probe):
            runner = Runner()

            async def run_and_wait():
                await runner.begin("manual", None, False, [mine])
                await runner._task

            asyncio.run(run_and_wait())
        self.assertEqual(sorted(checked), ["a", "b"])
        run = db.list_runs(1)[0]
        self.assertEqual((run["trigger"], run["total"], len(run["sources"])), ("manual", 2, 1))

    def test_scheduled_run_refreshes_only_its_subscriptions(self):
        mine = self.source(kind="subscription")
        self.source(kind="subscription")
        with mock.patch.object(subscription, "refresh_many", return_value=[]) as refresh:
            asyncio.run(Runner().begin_and_wait("schedule", source_ids=[mine]))
        refresh.assert_called_once_with([mine])

    def test_old_schedule_is_copied_to_sources(self):
        source_id = self.source()
        with db.connect() as conn:
            conn.execute("DELETE FROM settings WHERE key='source_schedules_migrated'")
            for key, value in (("schedule_mode", "interval"), ("interval_minutes", "45"), ("refresh_before_run", "0"),
                               ("last_schedule_at", "2026-11-03T03:00:00Z")):
                conn.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
        db.init_db()
        source = db.get_source(source_id)
        self.assertEqual((source["interval_minutes"], source["refresh_before_run"]), (45, False))
        self.assertEqual(source["last_scheduled_at"], "2026-11-03T03:00:00Z")


class CancelTests(DatabaseCase):
    def test_cancelled_probe_keeps_last_result(self):
        db.save_settings({"refresh_before_run": False})
        node = parse_link(vless("1.1.1.1", "x"))
        db.sync_nodes(1, [node])
        db.insert_result(db.create_run("manual", 1), node.id, ProbeResult(ok=True, download_bps=5.0))

        def stopped(_node, _settings, token, _stage):
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


class ProgressTests(DatabaseCase):
    def test_nodes_with_same_name_differ_by_id(self):
        db.save_settings({"refresh_before_run": False})
        nodes = [parse_link(vless("1.1.1.1", "same")), parse_link(vless("2.2.2.2", "same"))]
        db.sync_nodes(1, nodes)
        runner = Runner()
        seen = []

        def probe(_node, _settings, _token, _stage):
            seen.append((list(runner.progress["current"]), list(runner.progress["current_ids"])))
            return ProbeResult(ok=True, download_bps=1.0)

        async def run():
            await runner.begin("manual", None, False)
            await runner._task

        with mock.patch("app.runner.test_node", probe):
            asyncio.run(run())

        self.assertEqual(sorted(ids[0] for _, ids in seen), sorted(node.id for node in nodes))
        self.assertTrue(all(names == ["same"] for names, _ in seen))
        self.assertIn("alive", db.node_history(nodes[0].id, 5)[0])
        self.assertIn("alive", db.series("2000-01-01T00:00:00Z")[0])


class RecentResultsTests(DatabaseCase):
    def test_keeps_last_checks_of_each_node_in_time_order(self):
        nodes = [parse_link(vless("1.1.1.1", "a")), parse_link(vless("2.2.2.2", "b"))]
        db.sync_nodes(1, nodes)
        run = db.create_run("manual", 2)
        for speed in (1.0, 2.0, 3.0):
            db.insert_result(run, nodes[0].id, ProbeResult(ok=True, download_bps=speed))
        db.insert_result(run, nodes[1].id, ProbeResult(ok=False, alive=True))

        rows = db.recent_results(2)

        first = [row["download_bps"] for row in rows if row["node_id"] == nodes[0].id]
        self.assertEqual(first, [2.0, 3.0])
        second = [row for row in rows if row["node_id"] == nodes[1].id]
        self.assertEqual(len(second), 1)
        self.assertTrue(second[0]["alive"])


class StageTests(DatabaseCase):
    def test_node_stage_is_published_next_to_name(self):
        db.save_settings({"refresh_before_run": False})
        db.sync_nodes(1, [parse_link(vless("1.1.1.1", "x"))])
        release = threading.Event()

        def probe(_node, _settings, _token, stage):
            stage("download")
            release.wait(5)
            return ProbeResult(ok=True)

        async def run():
            runner = Runner()
            await runner.begin("manual", None, False)
            seen = None
            for _ in range(100):
                await asyncio.sleep(0.02)
                progress = runner.progress or {}
                # Сразу после старта узла этап пустой: ждём, пока дойдёт сообщённый из потока.
                if progress.get("current_stages") == ["download"]:
                    seen = (progress["current"], progress["current_stages"], progress["current_stage_started"])
                    break
            release.set()
            await runner._task
            return seen

        with mock.patch("app.runner.test_node", probe):
            before = time.time()
            names, stages, started = asyncio.run(run())
        self.assertEqual((names, stages), (["x"], ["download"]))
        self.assertEqual(len(started), 1)
        self.assertGreaterEqual(started[0], before)


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
