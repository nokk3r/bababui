import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from app import db, engines
from app.engines import CancelToken, ProbeResult, measure, relax_unverified_tls
from app.i18n import msg
from app.parser import parse_link

UUID = "11111111-1111-1111-1111-111111111111"
SETTINGS = {"measure_download": True, "measure_upload": True}


def payload(download=None, upload=None) -> str:
    server = {"id": "42", "latency": 20_000_000}
    if download:
        server["dl_speed"] = download
    if upload:
        server["ul_speed"] = upload
    return json.dumps({"servers": [server]})


def run_measure(replies, alive=True, settings=SETTINGS):
    runs = mock.Mock(side_effect=replies)
    with mock.patch.object(engines, "run_speedtest", runs), mock.patch.object(
        engines, "traffic_passes", return_value=alive
    ) as traffic:
        result = measure(1080, settings, CancelToken(), [])
    return result, runs, traffic


class MeasureTests(unittest.TestCase):
    def test_directions_run_separately_on_one_server(self):
        result, runs, traffic = run_measure([(0, payload(download=100), ""), (0, payload(upload=50), "")])
        self.assertTrue(result.ok)
        self.assertTrue(result.alive)
        self.assertEqual((result.download_bps, result.upload_bps), (100, 50))
        first, second = [call.args[0] for call in runs.call_args_list]
        self.assertIn("--no-upload", first)
        self.assertNotIn("--no-download", first)
        self.assertIn("--no-download", second)
        self.assertIn("--server=42", second)
        traffic.assert_called_once()

    def test_upload_timeout_keeps_download(self):
        result, _, _ = run_measure([(0, payload(download=100), ""), (1, "", msg("speedtest_timeout"))])
        self.assertFalse(result.ok)
        self.assertTrue(result.alive)
        self.assertEqual(result.download_bps, 100)
        self.assertEqual(result.error, f"speedtest: {msg('speedtest_timeout')}")

    def test_stages_follow_measurement(self):
        stage = mock.Mock()
        runs = mock.Mock(side_effect=[(0, payload(download=100), ""), (0, payload(upload=50), "")])
        with mock.patch.object(engines, "run_speedtest", runs), mock.patch.object(
            engines, "traffic_passes", return_value=True
        ):
            measure(1080, SETTINGS, CancelToken(), [], stage)
        self.assertEqual([call.args[0] for call in stage.call_args_list], ["traffic", "download", "upload"])

    def test_download_timeout_skips_upload(self):
        result, runs, traffic = run_measure([(1, "", msg("speedtest_timeout"))])
        self.assertFalse(result.ok)
        self.assertTrue(result.alive)
        self.assertEqual(result.error, f"speedtest: {msg('speedtest_timeout')}")
        self.assertEqual(runs.call_count, 1)
        traffic.assert_called_once()

    def test_dead_node_skips_speedtest(self):
        result, runs, _ = run_measure([], alive=False)
        self.assertFalse(result.ok)
        self.assertIs(result.alive, False)
        self.assertEqual(result.error, msg("node_no_traffic"))
        runs.assert_not_called()

    def test_node_dying_mid_test_stops(self):
        runs = mock.Mock(side_effect=[(1, "", "connection refused")])
        with mock.patch.object(engines, "run_speedtest", runs), mock.patch.object(
            engines, "traffic_passes", side_effect=[True, False]
        ):
            result = measure(1080, SETTINGS, CancelToken(), [])
        self.assertIs(result.alive, False)
        self.assertEqual(result.error, f"{msg('node_no_traffic')}: connection refused")
        self.assertEqual(runs.call_count, 1)

    def test_single_direction_is_one_run(self):
        settings = {"measure_download": False, "measure_upload": True}
        result, runs, _ = run_measure([(0, payload(upload=50), "")], settings=settings)
        self.assertTrue(result.ok)
        self.assertEqual(runs.call_count, 1)


class AliveColumnTests(unittest.TestCase):
    def test_old_database_gets_column(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(db, "DATA_DIR", Path(folder)):
            conn = sqlite3.connect(Path(folder) / "checker.db")
            conn.execute(
                """
                CREATE TABLE results (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    tested_at TEXT NOT NULL,
                    ok INTEGER NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()
            db.init_db()
            db.init_db()
            with db.connect() as check:
                names = {row["name"] for row in check.execute("PRAGMA table_info(results)")}
        self.assertIn("alive", names)

    def test_node_exposes_last_alive(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(db, "DATA_DIR", Path(folder)):
            db.init_db()
            node = parse_link(f"vless://{UUID}@1.1.1.1:443?security=tls&sni=a.com#x")
            db.sync_nodes([node])
            db.insert_result(db.create_run("manual", 1), node.id, ProbeResult(error="сбой", alive=True))
            self.assertIs(db.list_nodes()[0]["last_alive"], True)


class PortTests(unittest.TestCase):
    def test_same_free_port_is_not_given_twice(self):
        with mock.patch.object(engines, "free_port", side_effect=[1111, 1111, 2222]):
            first = engines.reserve_port()
            second = engines.reserve_port()
        self.addCleanup(engines.release_port, first)
        self.addCleanup(engines.release_port, second)
        self.assertEqual((first, second), (1111, 2222))

    def test_released_port_can_be_reused(self):
        with mock.patch.object(engines, "free_port", return_value=3333):
            engines.release_port(engines.reserve_port())
            port = engines.reserve_port()
        engines.release_port(port)
        self.assertEqual(port, 3333)

    def test_parallel_reservations_are_unique(self):
        barrier = threading.Barrier(4)

        def take(_):
            barrier.wait()
            return engines.reserve_port()

        with ThreadPoolExecutor(4) as pool:
            ports = list(pool.map(take, range(4)))
        for port in ports:
            engines.release_port(port)
        self.assertEqual(len(set(ports)), 4)


class UdpTlsTests(unittest.TestCase):
    def outbound(self, network: str, alpn: list[str]) -> dict:
        return {
            "settings": {"vnext": [{"address": "1.1.1.1", "port": 443}]},
            "streamSettings": {
                "network": network,
                "tlsSettings": {"allowInsecure": True, "alpn": alpn},
            },
        }

    def fail_fetch(self):
        return mock.patch.object(engines, "fetch_cert_sha256", side_effect=OSError("refused"))

    def test_h3_without_tcp_is_left_to_xray(self):
        outbound = self.outbound("xhttp", ["h3"])
        with self.fail_fetch():
            relax_unverified_tls(outbound)
        tls = outbound["streamSettings"]["tlsSettings"]
        self.assertNotIn("allowInsecure", tls)
        self.assertNotIn("pinnedPeerCertSha256", tls)

    def test_kcp_without_tcp_is_left_to_xray(self):
        outbound = self.outbound("kcp", [])
        with self.fail_fetch():
            relax_unverified_tls(outbound)
        self.assertNotIn("allowInsecure", outbound["streamSettings"]["tlsSettings"])

    def test_tcp_node_still_reports_failure(self):
        with self.fail_fetch(), self.assertRaises(RuntimeError):
            relax_unverified_tls(self.outbound("tcp", ["h2"]))

    def test_h3_is_not_offered_over_tcp(self):
        outbound = self.outbound("xhttp", ["h3", "h2"])
        with mock.patch.object(engines, "fetch_cert_sha256", return_value="ab") as fetch:
            relax_unverified_tls(outbound)
        self.assertEqual(fetch.call_args.args[3], ["h2"])
        self.assertEqual(outbound["streamSettings"]["tlsSettings"]["pinnedPeerCertSha256"], "ab")


class BinaryVersionTests(unittest.TestCase):
    def test_speedtest_version_drops_build_time(self):
        output = "speedtest-go v1.8.3 git-df849ca built at 2026-09-01T06:42:03Z\n"
        with mock.patch("app.engines.subprocess.check_output", return_value=output):
            status = engines.describe_binary("speedtest-go", ["--version"])
        self.assertEqual(status, {"ok": True, "text": "speedtest-go v1.8.3"})


class RemovedTransportTests(unittest.TestCase):
    def test_http_and_quic_are_unsupported_and_keep_id(self):
        for network in ("h2", "http", "quic"):
            node = parse_link(f"vless://{UUID}@1.1.1.1:443?security=tls&type={network}&sni=a.com#x")
            self.assertFalse(node.supported)
            self.assertEqual(node.engine, "")
            self.assertIn("transport_removed", node.reason)


if __name__ == "__main__":
    unittest.main()
