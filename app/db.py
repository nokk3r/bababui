"""SQLite-хранилище настроек, узлов и результатов."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import DATA_DIR

DEFAULTS: dict[str, str] = {
    "subscription_url": "",
    "subscription_insecure": "1",
    "scheduler_enabled": "1",
    "interval_minutes": "120",
    "concurrency": "1",
    "tls_insecure_if_no_sni": "1",
    "refresh_before_run": "1",
    "measure_download": "1",
    "measure_upload": "1",
    "retention_days": "30",
    "subscription_userinfo": "",
    "last_refresh_at": "",
    "last_refresh_error": "",
}

BOOL_KEYS = {
    "subscription_insecure",
    "scheduler_enabled",
    "tls_insecure_if_no_sni",
    "refresh_before_run",
    "measure_download",
    "measure_upload",
}
INT_KEYS = {
    "interval_minutes",
    "concurrency",
    "retention_days",
}
FORM_KEYS = [
    "subscription_url",
    "subscription_insecure",
    "scheduler_enabled",
    "interval_minutes",
    "concurrency",
    "tls_insecure_if_no_sni",
    "refresh_before_run",
    "measure_download",
    "measure_upload",
    "retention_days",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "checker.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                protocol TEXT NOT NULL,
                address TEXT NOT NULL,
                port INTEGER NOT NULL,
                network TEXT NOT NULL DEFAULT '',
                security TEXT NOT NULL DEFAULT '',
                badges TEXT NOT NULL DEFAULT '[]',
                link TEXT NOT NULL,
                supported INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                trigger TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                total INTEGER NOT NULL DEFAULT 0,
                ok_count INTEGER NOT NULL DEFAULT 0,
                fail_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                tested_at TEXT NOT NULL,
                latency_ms REAL,
                download_bps REAL,
                upload_bps REAL,
                download_bytes INTEGER,
                upload_bytes INTEGER,
                ok INTEGER NOT NULL,
                error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_results_node ON results(node_id, tested_at);
            CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
            """
        )
        for key, value in DEFAULTS.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO NOTHING",
                (key, value),
            )
        now = utcnow()
        conn.execute(
            """
            UPDATE runs
            SET status='failed', error='сервис перезапущен', finished_at=?
            WHERE status='running'
            """,
            (now,),
        )


def get_raw_settings() -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    found = {row["key"]: row["value"] for row in rows}
    merged = dict(DEFAULTS)
    merged.update(found)
    return merged


def public_settings(raw: dict[str, str] | None = None) -> dict:
    raw = raw or get_raw_settings()
    out: dict = {}
    for key in FORM_KEYS:
        value = raw.get(key, DEFAULTS.get(key, ""))
        if key in BOOL_KEYS:
            out[key] = value == "1"
        elif key in INT_KEYS:
            out[key] = int(value or 0)
        else:
            out[key] = value
    return out


def save_settings(values: dict) -> dict:
    raw = get_raw_settings()
    with connect() as conn:
        for key in FORM_KEYS:
            if key not in values:
                continue
            current = values[key]
            if key in BOOL_KEYS:
                stored = "1" if current else "0"
            else:
                stored = str(current)
            raw[key] = stored
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, stored),
            )
    return public_settings(raw)


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def sync_nodes(nodes: list) -> int:
    now = utcnow()
    ids: list[str] = []
    with connect() as conn:
        for node in nodes:
            ids.append(node.id)
            badges = json.dumps(node.badges, ensure_ascii=False)
            existing = conn.execute("SELECT id, enabled FROM nodes WHERE id=?", (node.id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE nodes
                    SET name=?, protocol=?, address=?, port=?, network=?, security=?, badges=?,
                        link=?, supported=?, reason=?, active=1, updated_at=?
                    WHERE id=?
                    """,
                    (
                        node.name,
                        node.protocol,
                        node.address,
                        node.port,
                        node.network,
                        node.security,
                        badges,
                        node.link,
                        1 if node.supported else 0,
                        node.reason,
                        now,
                        node.id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO nodes(
                        id, name, protocol, address, port, network, security, badges, link,
                        supported, reason, enabled, active, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        node.id,
                        node.name,
                        node.protocol,
                        node.address,
                        node.port,
                        node.network,
                        node.security,
                        badges,
                        node.link,
                        1 if node.supported else 0,
                        node.reason,
                        1 if node.supported else 0,
                        now,
                    ),
                )
        if ids:
            marks = ",".join("?" for _ in ids)
            conn.execute(f"UPDATE nodes SET active=0, updated_at=? WHERE id NOT IN ({marks})", (now, *ids))
        else:
            conn.execute("UPDATE nodes SET active=0, updated_at=?", (now,))
    return len(nodes)


def list_nodes() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT n.*,
                   r.latency_ms, r.download_bps, r.upload_bps, r.ok AS last_ok,
                   r.error AS last_error, r.tested_at AS last_tested_at
            FROM nodes n
            LEFT JOIN results r ON r.id = (
                SELECT r2.id FROM results r2
                WHERE r2.node_id = n.id
                ORDER BY r2.tested_at DESC, r2.id DESC
                LIMIT 1
            )
            ORDER BY n.name COLLATE NOCASE
            """
        ).fetchall()
    return [_node_row(row) for row in rows]


def get_node_link(node_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()


def nodes_for_run(node_ids: list[str] | None, include_disabled: bool) -> list[sqlite3.Row]:
    clauses = ["active=1", "supported=1"]
    params: list = []
    if not include_disabled:
        clauses.append("enabled=1")
    if node_ids is not None:
        if not node_ids:
            return []
        clauses.append(f"id IN ({','.join('?' for _ in node_ids)})")
        params.extend(node_ids)
    sql = f"SELECT * FROM nodes WHERE {' AND '.join(clauses)} ORDER BY name COLLATE NOCASE"
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def set_enabled(node_id: str, enabled: bool) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE nodes SET enabled=? WHERE id=? AND supported=1",
            (1 if enabled else 0, node_id),
        )
        return cur.rowcount > 0


def set_enabled_all(enabled: bool) -> int:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE nodes SET enabled=? WHERE active=1 AND supported=1",
            (1 if enabled else 0,),
        )
        return cur.rowcount


def create_run(trigger: str, total: int) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs(started_at, trigger, status, total)
            VALUES (?, ?, 'running', ?)
            """,
            (utcnow(), trigger, total),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, ok_count: int, fail_count: int, error: str = "") -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET finished_at=?, status=?, ok_count=?, fail_count=?, error=?
            WHERE id=?
            """,
            (utcnow(), status, ok_count, fail_count, error[:500], run_id),
        )


def insert_result(run_id: int, node_id: str, probe) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO results(
                run_id, node_id, tested_at, latency_ms, download_bps, upload_bps,
                download_bytes, upload_bytes, ok, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                node_id,
                utcnow(),
                probe.latency_ms,
                probe.download_bps,
                probe.upload_bps,
                probe.download_bytes,
                probe.upload_bytes,
                1 if probe.ok else 0,
                (probe.error or "")[:500],
            ),
        )


def list_runs(limit: int = 40) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            return None
        results = conn.execute(
            """
            SELECT r.tested_at, r.latency_ms, r.download_bps, r.upload_bps,
                   r.download_bytes, r.upload_bytes, r.ok, r.error,
                   n.name, n.protocol, n.address, n.port, n.id AS node_id
            FROM results r
            JOIN nodes n ON n.id = r.node_id
            WHERE r.run_id=?
            ORDER BY n.name COLLATE NOCASE
            """,
            (run_id,),
        ).fetchall()
    return {"run": dict(run), "results": [dict(row) for row in results]}


def node_history(node_id: str, limit: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT tested_at, latency_ms, download_bps, upload_bps, ok, error
            FROM results
            WHERE node_id=?
            ORDER BY tested_at DESC, id DESC
            LIMIT ?
            """,
            (node_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def series(since: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT node_id, tested_at, download_bps, upload_bps, latency_ms, ok
            FROM results
            WHERE tested_at >= ?
            ORDER BY tested_at ASC
            """,
            (since,),
        ).fetchall()
    return [dict(row) for row in rows]


def export_rows() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT r.tested_at, n.name, n.protocol, n.address, n.port,
                   r.latency_ms, r.download_bps, r.upload_bps, r.ok, r.error
            FROM results r
            JOIN nodes n ON n.id = r.node_id
            ORDER BY r.tested_at ASC
            """
        ).fetchall()


def clear_history() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM results")
        conn.execute("DELETE FROM runs")


def purge_old(days: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connect() as conn:
        conn.execute("DELETE FROM results WHERE tested_at < ?", (cutoff,))
        conn.execute("DELETE FROM runs WHERE started_at < ? AND status != 'running'", (cutoff,))


def _node_row(row: sqlite3.Row) -> dict:
    try:
        badges = json.loads(row["badges"] or "[]")
    except json.JSONDecodeError:
        badges = []
    return {
        "id": row["id"],
        "name": row["name"],
        "protocol": row["protocol"],
        "address": row["address"],
        "port": row["port"],
        "network": row["network"],
        "security": row["security"],
        "badges": badges,
        "supported": bool(row["supported"]),
        "reason": row["reason"],
        "enabled": bool(row["enabled"]),
        "active": bool(row["active"]),
        "latency_ms": row["latency_ms"],
        "download_bps": row["download_bps"],
        "upload_bps": row["upload_bps"],
        "last_ok": None if row["last_ok"] is None else bool(row["last_ok"]),
        "last_error": row["last_error"] or "",
        "last_tested_at": row["last_tested_at"],
    }
