"""SQLite-хранилище настроек, узлов и результатов."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import DATA_DIR
from app.parser import is_node_link

DEFAULTS: dict[str, str] = {
    "subscription_url": "",
    "subscription_insecure": "1",
    "scheduler_enabled": "1",
    "schedule_mode": "interval",
    "interval_minutes": "120",
    "cron_expression": "0 */2 * * *",
    "schedule_timezone": "",
    "concurrency": "1",
    "tls_insecure_if_no_sni": "1",
    "refresh_before_run": "1",
    "measure_download": "1",
    "measure_upload": "1",
    "retention_days": "30",
    "last_schedule_at": "",
}

BOOL_KEYS = {
    "subscription_insecure",
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
    "concurrency",
    "tls_insecure_if_no_sni",
    "measure_download",
    "measure_upload",
    "retention_days",
]


# Расписание у каждого источника своё, общего выключателя нет.
SOURCE_SCHEDULE_COLUMNS = {
    "schedule_enabled": "INTEGER NOT NULL DEFAULT 1",
    "schedule_mode": "TEXT NOT NULL DEFAULT 'interval'",
    "interval_minutes": "INTEGER NOT NULL DEFAULT 120",
    "cron_expression": "TEXT NOT NULL DEFAULT '0 */2 * * *'",
    "schedule_timezone": "TEXT NOT NULL DEFAULT ''",
    "refresh_before_run": "INTEGER NOT NULL DEFAULT 1",
    "last_scheduled_at": "TEXT NOT NULL DEFAULT ''",
}
SCHEDULE_FIELDS = ("schedule_enabled", "schedule_mode", "interval_minutes", "cron_expression", "schedule_timezone", "refresh_before_run")


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
                error TEXT NOT NULL DEFAULT '',
                alive INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_results_node ON results(node_id, tested_at);
            CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
            -- Источник узлов: подписка (адрес, который скачивается) или группа (ссылки, вписанные вручную).
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                links TEXT NOT NULL DEFAULT '',
                insecure INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                userinfo TEXT NOT NULL DEFAULT '',
                refreshed_at TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            -- Колонки расписания источника добавляются ниже через ALTER: так их получает и база без них.
            -- Узел один на всё приложение, с одной историей и одной галочкой, но может прийти из нескольких источников.
            CREATE TABLE IF NOT EXISTS source_nodes (
                source_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                PRIMARY KEY (source_id, node_id)
            );
            CREATE INDEX IF NOT EXISTS idx_source_nodes_node ON source_nodes(node_id);
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(results)")}
        if "alive" not in columns:
            conn.execute("ALTER TABLE results ADD COLUMN alive INTEGER")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
        if "sources" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN sources TEXT NOT NULL DEFAULT ''")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sources)")}
        for name, definition in SOURCE_SCHEDULE_COLUMNS.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE sources ADD COLUMN {name} {definition}")
        for key, value in DEFAULTS.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO NOTHING",
                (key, value),
            )
        _migrate_sources(conn)
        _migrate_source_schedules(conn)
        _migrate_global_pause(conn)
        now = utcnow()
        conn.execute(
            """
            UPDATE runs
            SET status='failed', error='[[service_restarted]]', finished_at=?
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


def _migrate_sources(conn: sqlite3.Connection) -> None:
    """Раньше все ссылки лежали одним полем в настройках. Каждый адрес становится подпиской,
    вписанные вручную узлы — одной группой. Узлы сразу привязываются к источникам, чтобы до первого
    обновления (например, без сети) они не выглядели ушедшими и не выпадали из проверки."""
    if conn.execute("SELECT 1 FROM settings WHERE key='sources_migrated'").fetchone():
        return
    raw = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}
    lines = [line.strip() for line in raw.get("subscription_url", "").splitlines() if line.strip()]
    links = [line for line in lines if is_node_link(line)]
    feeds = [line for line in lines if not is_node_link(line)]
    insecure = 0 if raw.get("subscription_insecure", "1") == "0" else 1
    now = utcnow()
    feed_ids = []
    for position, url in enumerate(feeds):
        # Трафик и время обновления раньше были общими: достаются первой подписке, чтобы строка не опустела.
        first = position == 0
        cur = conn.execute(
            "INSERT INTO sources(kind, url, insecure, userinfo, refreshed_at, error, created_at) VALUES ('subscription', ?, ?, ?, ?, '', ?)",
            (url, insecure, raw.get("subscription_userinfo", "") if first else "", raw.get("last_refresh_at", "") if first else "", now),
        )
        feed_ids.append(cur.lastrowid)
    group_id = None
    if links:
        cur = conn.execute(
            "INSERT INTO sources(kind, links, refreshed_at, created_at) VALUES ('group', ?, ?, ?)",
            ("\n".join(links), raw.get("last_refresh_at", ""), now),
        )
        group_id = cur.lastrowid
        marks = ",".join("?" for _ in links)
        conn.execute(
            f"INSERT OR IGNORE INTO source_nodes(source_id, node_id) SELECT ?, id FROM nodes WHERE active=1 AND link IN ({marks})",
            (group_id, *links),
        )
    fallback = feed_ids[0] if feed_ids else group_id
    if fallback is not None:
        conn.execute(
            """
            INSERT OR IGNORE INTO source_nodes(source_id, node_id)
            SELECT ?, id FROM nodes WHERE active=1 AND id NOT IN (SELECT node_id FROM source_nodes)
            """,
            (fallback,),
        )
    conn.execute("INSERT INTO settings(key, value) VALUES('sources_migrated', '1') ON CONFLICT(key) DO NOTHING")


def _migrate_source_schedules(conn: sqlite3.Connection) -> None:
    """Раньше расписание было одно на всех. Каждый источник получает его копию и время прошлого запуска,
    поэтому после обновления проверки идут как шли, а не все разом."""
    if conn.execute("SELECT 1 FROM settings WHERE key='source_schedules_migrated'").fetchone():
        return
    raw = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}
    last = raw.get("last_schedule_at", "")
    if not last:
        row = conn.execute("SELECT started_at FROM runs WHERE trigger='schedule' ORDER BY id DESC LIMIT 1").fetchone()
        last = row["started_at"] if row else ""
    try:
        interval = max(1, int(raw.get("interval_minutes") or 120))
    except ValueError:
        interval = 120
    conn.execute(
        """
        UPDATE sources SET schedule_mode=?, interval_minutes=?, cron_expression=?, schedule_timezone=?,
                           refresh_before_run=?, last_scheduled_at=?
        """,
        (
            "cron" if raw.get("schedule_mode") == "cron" else "interval",
            interval,
            raw.get("cron_expression") or "0 */2 * * *",
            raw.get("schedule_timezone", ""),
            0 if raw.get("refresh_before_run", "1") == "0" else 1,
            last,
        ),
    )
    conn.execute("INSERT INTO settings(key, value) VALUES('source_schedules_migrated', '1') ON CONFLICT(key) DO NOTHING")


def _migrate_global_pause(conn: sqlite3.Connection) -> None:
    """Общий выключатель расписания убран. Если он был выключен, выключается расписание каждого источника:
    после обновления ничего не начнёт проверяться само."""
    if conn.execute("SELECT 1 FROM settings WHERE key='global_pause_migrated'").fetchone():
        return
    row = conn.execute("SELECT value FROM settings WHERE key='scheduler_enabled'").fetchone()
    if row and row["value"] == "0":
        conn.execute("UPDATE sources SET schedule_enabled=0")
    conn.execute("INSERT INTO settings(key, value) VALUES('global_pause_migrated', '1') ON CONFLICT(key) DO NOTHING")


def history_stats() -> dict:
    """Сколько хранится истории и сколько места она занимает. Размер считается по страницам таблиц истории;
    если SQLite собран без dbstat, отдаётся размер всей базы вместе с журналом."""
    with connect() as conn:
        results = conn.execute("SELECT COUNT(*), MIN(tested_at) FROM results").fetchone()
        runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        try:
            size = conn.execute(
                "SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name IN ('results', 'runs', 'idx_results_node', 'idx_results_run')"
            ).fetchone()[0]
            whole = False
        except sqlite3.OperationalError:
            size = sum(path.stat().st_size for path in (db_path(), db_path().with_name("checker.db-wal")) if path.exists())
            whole = True
    return {"results": results[0], "runs": runs, "oldest": results[1], "bytes": int(size), "whole_database": whole}


def _source_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "name": row["name"],
        "url": row["url"],
        "links": row["links"],
        "insecure": bool(row["insecure"]),
        "title": row["title"],
        "userinfo": row["userinfo"],
        "refreshed_at": row["refreshed_at"] or None,
        "error": row["error"],
        "schedule_enabled": bool(row["schedule_enabled"]),
        "schedule_mode": row["schedule_mode"],
        "interval_minutes": row["interval_minutes"],
        "cron_expression": row["cron_expression"],
        "schedule_timezone": row["schedule_timezone"],
        "refresh_before_run": bool(row["refresh_before_run"]),
        "last_scheduled_at": row["last_scheduled_at"] or None,
    }


def list_sources() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    return [_source_row(row) for row in rows]


def get_source(source_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    return _source_row(row) if row else None


def has_sources() -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM sources LIMIT 1").fetchone() is not None


def _schedule_values(schedule: dict) -> dict:
    values = {key: schedule[key] for key in SCHEDULE_FIELDS if key in schedule}
    for key in ("schedule_enabled", "refresh_before_run"):
        if key in values:
            values[key] = 1 if values[key] else 0
    return values


def create_source(kind: str, name: str, url: str, links: str, insecure: bool, **schedule) -> int:
    values = {"kind": kind, "name": name, "url": url, "links": links, "insecure": 1 if insecure else 0,
              "created_at": utcnow(), **_schedule_values(schedule)}
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO sources({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )
        return int(cur.lastrowid)


def update_source(source_id: int, name: str, url: str, links: str, insecure: bool, **schedule) -> bool:
    values = {"name": name, "url": url, "links": links, "insecure": 1 if insecure else 0, **_schedule_values(schedule)}
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE sources SET {', '.join(f'{key}=?' for key in values)} WHERE id=?",
            (*values.values(), source_id),
        )
        return cur.rowcount > 0


def mark_scheduled(source_ids: list[int], stamp: str) -> None:
    """Старт проверки по расписанию: от него источник отсчитывает следующий интервал."""
    with connect() as conn:
        conn.executemany("UPDATE sources SET last_scheduled_at=? WHERE id=?", [(stamp, source_id) for source_id in source_ids])


def set_source_status(source_id: int, **values: str) -> None:
    """Итог обновления источника: время, ошибка, трафик и название из заголовков подписки."""
    allowed = {key: value for key, value in values.items() if key in {"refreshed_at", "error", "userinfo", "title"}}
    if not allowed:
        return
    assignments = ", ".join(f"{key}=?" for key in allowed)
    with connect() as conn:
        conn.execute(f"UPDATE sources SET {assignments} WHERE id=?", (*allowed.values(), source_id))


def delete_source(source_id: int) -> bool:
    with connect() as conn:
        members = [row["node_id"] for row in conn.execute("SELECT node_id FROM source_nodes WHERE source_id=?", (source_id,))]
        deleted = conn.execute("DELETE FROM sources WHERE id=?", (source_id,)).rowcount
        conn.execute("DELETE FROM source_nodes WHERE source_id=?", (source_id,))
        _refresh_active(conn, members, utcnow())
    return bool(deleted)


def set_source_enabled(source_id: int, enabled: bool) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE nodes SET enabled=?
            WHERE supported=1 AND id IN (SELECT node_id FROM source_nodes WHERE source_id=?)
            """,
            (1 if enabled else 0, source_id),
        )
        return cur.rowcount


def checkable_counts() -> dict[int, int]:
    """Сколько узлов каждого источника попадёт в проверку: в списке, поддерживаются и включены."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.source_id, COUNT(*) AS total
            FROM source_nodes s JOIN nodes n ON n.id = s.node_id
            WHERE n.active=1 AND n.supported=1 AND n.enabled=1
            GROUP BY s.source_id
            """
        ).fetchall()
    return {row["source_id"]: row["total"] for row in rows}


def count_active_nodes() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM nodes WHERE active=1").fetchone()[0])


def _refresh_active(conn: sqlite3.Connection, node_ids, now: str) -> None:
    """Узел в списке, пока его присылает хоть один источник; иначе он «ушедший»."""
    node_ids = list(node_ids)
    for start in range(0, len(node_ids), 500):
        chunk = node_ids[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        conn.execute(
            f"""
            UPDATE nodes
            SET active = EXISTS(SELECT 1 FROM source_nodes s WHERE s.node_id = nodes.id), updated_at=?
            WHERE id IN ({marks})
            """,
            (now, *chunk),
        )


def sync_nodes(source_id: int, nodes: list) -> int:
    """Состав одного источника. Узлы других источников не трогаются."""
    now = utcnow()
    ids: list[str] = []
    current = {node.id for node in nodes}
    with connect() as conn:
        for node in nodes:
            ids.append(node.id)
            badges = json.dumps(node.badges, ensure_ascii=False)
            _adopt_legacy_id(conn, node, current)
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
        previous = {row["node_id"] for row in conn.execute("SELECT node_id FROM source_nodes WHERE source_id=?", (source_id,))}
        conn.execute("DELETE FROM source_nodes WHERE source_id=?", (source_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO source_nodes(source_id, node_id) VALUES (?, ?)",
            [(source_id, node_id) for node_id in ids],
        )
        _refresh_active(conn, previous - current, now)
    return len(nodes)


def _adopt_legacy_id(conn: sqlite3.Connection, node, current: set[str]) -> None:
    """Раньше id не учитывал SNI и ключи. Узел забирает галочку и историю старой записи."""
    legacy = node.legacy_id
    if not legacy or legacy == node.id or legacy in current:
        return
    if conn.execute("SELECT 1 FROM nodes WHERE id=?", (node.id,)).fetchone():
        return
    cur = conn.execute("UPDATE nodes SET id=? WHERE id=?", (node.id, legacy))
    if cur.rowcount:
        conn.execute("UPDATE results SET node_id=? WHERE node_id=?", (node.id, legacy))
        conn.execute("UPDATE OR IGNORE source_nodes SET node_id=? WHERE node_id=?", (node.id, legacy))


def list_nodes() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT n.*,
                   r.latency_ms, r.download_bps, r.upload_bps, r.ok AS last_ok, r.alive AS last_alive,
                   r.error AS last_error, r.tested_at AS last_tested_at,
                   (SELECT GROUP_CONCAT(s.source_id) FROM source_nodes s WHERE s.node_id = n.id) AS source_ids
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


def nodes_for_run(node_ids: list[str] | None, include_disabled: bool, source_ids: list[int] | None = None) -> list[sqlite3.Row]:
    clauses = ["active=1", "supported=1"]
    params: list = []
    if source_ids is not None:
        # Узел из двух источников, которым пора одновременно, попадает в прогон один раз.
        clauses.append(f"id IN (SELECT node_id FROM source_nodes WHERE source_id IN ({','.join('?' for _ in source_ids)}))")
        params.extend(source_ids)
    if not include_disabled:
        clauses.append("enabled=1")
    if node_ids is not None:
        if not node_ids:
            return []
        clauses.append(f"id IN ({','.join('?' for _ in node_ids)})")
        params.extend(node_ids)
    # Первыми идут давно не проверенные: остановленный прогон продолжается с непроверенных,
    # а узел, упавший по таймауту, уходит в конец и не держит следующий запуск.
    sql = f"""
        SELECT * FROM nodes WHERE {' AND '.join(clauses)}
        ORDER BY (SELECT MAX(tested_at) FROM results WHERE results.node_id = nodes.id),
                 name COLLATE NOCASE
    """
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


def create_run(trigger: str, total: int, sources: list[str] | None = None) -> int:
    """sources — названия источников проверки по расписанию на момент старта: история переживает их переименование и удаление."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs(started_at, trigger, status, total, sources)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (utcnow(), trigger, total, json.dumps(sources, ensure_ascii=False) if sources else ""),
        )
        return int(cur.lastrowid)


def _run_row(row: sqlite3.Row) -> dict:
    run = dict(row)
    try:
        run["sources"] = json.loads(run.get("sources") or "[]")
    except json.JSONDecodeError:
        run["sources"] = []
    return run


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
                download_bytes, upload_bytes, ok, error, alive
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                None if probe.alive is None else int(probe.alive),
            ),
        )


def list_runs(limit: int = 40) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_run_row(row) for row in rows]


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            return None
        results = conn.execute(
            """
            SELECT r.tested_at, r.latency_ms, r.download_bps, r.upload_bps,
                   r.download_bytes, r.upload_bytes, r.ok, r.error, r.alive,
                   n.name, n.protocol, n.address, n.port, n.id AS node_id
            FROM results r
            JOIN nodes n ON n.id = r.node_id
            WHERE r.run_id=?
            ORDER BY n.name COLLATE NOCASE
            """,
            (run_id,),
        ).fetchall()
    return {"run": _run_row(run), "results": [dict(row) for row in results]}


def node_history(node_id: str, limit: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT tested_at, latency_ms, download_bps, upload_bps, ok, error, alive
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
            SELECT node_id, tested_at, download_bps, upload_bps, latency_ms, ok, alive
            FROM results
            WHERE tested_at >= ?
            ORDER BY tested_at ASC
            """,
            (since,),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_results(per_node: int) -> list[dict]:
    """Последние проверки каждого узла за любое время: полоска в таблице не должна зависеть от окна в 48 часов."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT node_id, tested_at, download_bps, upload_bps, latency_ms, ok, alive
            FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY tested_at DESC, id DESC) AS position
                FROM results
            )
            WHERE position <= ?
            ORDER BY tested_at ASC, id ASC
            """,
            (per_node,),
        ).fetchall()
    return [dict(row) for row in rows]


def export_rows() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT r.tested_at, n.name, n.protocol, n.address, n.port,
                   r.latency_ms, r.download_bps, r.upload_bps, r.ok, r.error, r.alive
            FROM results r
            JOIN nodes n ON n.id = r.node_id
            ORDER BY r.tested_at ASC
            """
        ).fetchall()


def clear_history() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM results")
        conn.execute("DELETE FROM runs")


def delete_run(run_id: int) -> bool:
    """Удаляет прогон с его результатами. Идущий прогон не трогается: в него ещё пишут результаты."""
    with connect() as conn:
        deleted = conn.execute("DELETE FROM runs WHERE id=? AND status != 'running'", (run_id,)).rowcount
        if deleted:
            conn.execute("DELETE FROM results WHERE run_id=?", (run_id,))
    return bool(deleted)


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
        "last_alive": None if row["last_alive"] is None else bool(row["last_alive"]),
        "last_error": row["last_error"] or "",
        "last_tested_at": row["last_tested_at"],
        "sources": sorted(int(part) for part in (row["source_ids"] or "").split(",") if part),
    }
