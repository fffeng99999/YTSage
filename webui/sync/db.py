"""
YTSage Sync - Database layer
=============================
dysync parity: SQLite by default, with MySQL and PostgreSQL selectable at
runtime and an online migration that copies every table between engines.

Design notes
------------
* SQLite stays the zero-dependency default; MySQL/PostgreSQL drivers are
  imported lazily so they are only required when actually selected.
* The rest of the store keeps writing portable SQL with `?` placeholders;
  this module rewrites them to `%s` for the DB-API "format" drivers.
* Column definitions live in TABLE_DEFS as generic types so the DDL can be
  emitted per dialect (AUTOINCREMENT / AUTO_INCREMENT / SERIAL differ, and
  MySQL refuses a DEFAULT on a TEXT column).
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..official_bridge import APP_DATA_DIR

logger = logging.getLogger("ytsage.webui.sync.db")

CONFIG_FILE = APP_DATA_DIR / "sync_database.json"

SUPPORTED_TYPES = ("sqlite", "mysql", "postgresql")

DEFAULT_CONFIG: Dict[str, Any] = {
    "type": "sqlite",
    "sqlite_path": "",          # empty -> <APP_DATA_DIR>/ytsage_sync.db
    "host": "127.0.0.1",
    "port": 0,                  # 0 -> dialect default (3306 / 5432)
    "database": "ytsage",
    "user": "",
    "password": "",
    "ssl": False,
}

DEFAULT_PORTS = {"mysql": 3306, "postgresql": 5432}

# ---------------------------------------------------------------------------
# Schema definition (generic types: PK / STR / TEXT / INT / REAL)
# ---------------------------------------------------------------------------

TABLE_DEFS: Dict[str, List[Tuple[str, str, str]]] = {
    "profiles": [
        ("id", "PK", ""),
        ("name", "STR", "NOT NULL"),
        ("cookie_source", "STR", "DEFAULT 'browser'"),
        ("cookie_browser", "STR", "DEFAULT 'chrome'"),
        ("cookie_browser_profile", "STR", "DEFAULT ''"),
        ("cookie_file_path", "STR", ""),
        ("root_path", "STR", "NOT NULL"),
        ("only_recent", "INT", "DEFAULT 0"),
        ("recent_limit", "INT", "DEFAULT 20"),
        ("folder_by_title", "INT", "DEFAULT 1"),
        ("enabled", "INT", "DEFAULT 1"),
        ("dedup_priority", "STR", "DEFAULT '[\"liked\",\"favorites\",\"playlist\",\"channel\",\"subscriptions\"]'"),
        ("created_at", "REAL", ""),
        ("updated_at", "REAL", ""),
        ("cookie_invalid", "INT", "DEFAULT 0"),
        ("cookie_checked_at", "REAL", ""),
        ("cookie_check_error", "TEXT", ""),
    ],
    "targets": [
        ("id", "PK", ""),
        ("profile_id", "INT", "NOT NULL"),
        ("kind", "STR", "NOT NULL"),
        ("url", "STR", "NOT NULL"),
        ("title", "STR", ""),
        ("folder", "STR", ""),
        ("enabled", "INT", "DEFAULT 1"),
        ("sort_index", "INT", "DEFAULT 0"),
        ("created_at", "REAL", ""),
        ("sync_mode", "STR", "DEFAULT 'sync'"),
        ("save_path", "STR", ""),
        ("channel_id", "STR", ""),
        ("avatar_url", "STR", ""),
        ("last_sync_at", "REAL", ""),
    ],
    "records": [
        ("id", "PK", ""),
        ("video_id", "STR", "NOT NULL UNIQUE"),
        ("video_title", "STR", ""),
        ("channel", "STR", ""),
        ("url", "STR", ""),
        ("kind", "STR", ""),
        ("profile_id", "INT", ""),
        ("target_id", "INT", ""),
        ("file_path", "STR", ""),
        ("size", "INT", "DEFAULT 0"),
        ("duration", "REAL", ""),
        ("status", "STR", "DEFAULT 'downloaded'"),
        ("last_sync", "REAL", ""),
        ("first_sync", "REAL", ""),
        ("download_job_id", "STR", ""),
        ("thumbnail_url", "STR", ""),
        ("deleted_at", "REAL", ""),
        ("nfo_generated", "INT", "DEFAULT 0"),
    ],
    "excludes": [
        ("video_id", "STR", "PRIMARY KEY"),
        ("reason", "STR", ""),
        ("created_at", "REAL", ""),
    ],
    "schedules": [
        ("id", "PK", ""),
        ("profile_id", "INT", "NOT NULL"),
        ("mode", "STR", "DEFAULT 'interval'"),
        ("interval_min", "INT", "DEFAULT 60"),
        ("hour", "INT", "DEFAULT 0"),
        ("minute", "INT", "DEFAULT 0"),
        ("weekday", "INT", "DEFAULT 1"),
        ("enabled", "INT", "DEFAULT 1"),
        ("last_run", "REAL", ""),
        ("next_run", "REAL", ""),
        ("created_at", "REAL", ""),
    ],
    "sync_runs": [
        ("id", "PK", ""),
        ("run_at", "REAL", ""),
        ("finished_at", "REAL", ""),
        ("profile_id", "INT", ""),
        ("kind", "STR", ""),
        ("total", "INT", "DEFAULT 0"),
        ("new_count", "INT", "DEFAULT 0"),
        ("skipped", "INT", "DEFAULT 0"),
        ("failed", "INT", "DEFAULT 0"),
        ("summary", "TEXT", ""),
    ],
    "sync_settings": [
        ("key", "STR", "PRIMARY KEY"),
        ("value", "TEXT", ""),
    ],
    "sync_daily_stats": [
        ("date", "STR", "PRIMARY KEY"),
        ("total_videos", "INT", "DEFAULT 0"),
        ("total_size", "INT", "DEFAULT 0"),
        ("liked_count", "INT", "DEFAULT 0"),
        ("playlist_count", "INT", "DEFAULT 0"),
        ("channel_count", "INT", "DEFAULT 0"),
        ("subs_count", "INT", "DEFAULT 0"),
        ("new_synced", "INT", "DEFAULT 0"),
    ],
}

INDEXES: List[Tuple[str, str, Sequence[str]]] = [
    ("idx_records_last_sync", "records", ("last_sync",)),
    ("idx_records_profile", "records", ("profile_id",)),
    ("idx_targets_profile", "targets", ("profile_id",)),
    ("idx_runs_profile", "sync_runs", ("profile_id",)),
]


# ---------------------------------------------------------------------------
# Dialects
# ---------------------------------------------------------------------------

class Dialect:
    """SQL flavour differences we actually rely on."""

    name = "sqlite"
    placeholder = "?"
    supports_default_on_text = True

    # -- DDL ---------------------------------------------------------------
    def pk_ddl(self, column: str = "id") -> str:
        return f"{column} INTEGER PRIMARY KEY AUTOINCREMENT"

    def column_type(self, kind: str) -> str:
        return {"STR": "TEXT", "TEXT": "TEXT", "INT": "INTEGER", "REAL": "REAL"}[kind]

    def create_table(self, table: str, tables: Optional[Dict[str, List[Tuple[str, str, str]]]] = None) -> str:
        defs = tables if tables is not None else TABLE_DEFS
        cols = []
        for name, kind, extra in defs[table]:
            if kind == "PK":
                cols.append(self.pk_ddl(name))
                continue
            if not self.supports_default_on_text and kind == "TEXT" and "DEFAULT" in extra.upper():
                extra = ""
            cols.append(f"{name} {self.column_type(kind)} {extra}".strip())
        return f"CREATE TABLE IF NOT EXISTS {table} (\n  " + ",\n  ".join(cols) + "\n)"

    def create_index(self, name: str, table: str, cols: Sequence[str]) -> str:
        return f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({', '.join(cols)})"

    # -- DML ---------------------------------------------------------------
    def insert_or_replace(self, table: str, cols: Sequence[str]) -> str:
        ph = ", ".join([self.placeholder] * len(cols))
        return f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({ph})"

    def insert_or_ignore(self, table: str, cols: Sequence[str]) -> str:
        ph = ", ".join([self.placeholder] * len(cols))
        return f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({ph})"

    # -- introspection -----------------------------------------------------
    def table_columns_sql(self, table: str):
        return f"PRAGMA table_info({table})", ()

    def table_columns_from_rows(self, rows) -> set:
        return {r["name"] for r in rows}

    def last_insert_id(self, cur) -> int:
        try:
            return int(cur.lastrowid or 0)
        except Exception:  # noqa: BLE001
            return 0

    # -- connection --------------------------------------------------------
    def post_connect(self, conn) -> None:
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:  # noqa: BLE001
            pass


class SQLiteDialect(Dialect):
    name = "sqlite"
    placeholder = "?"


class MySQLDialect(Dialect):
    """MySQL. Note: TEXT columns cannot carry a DEFAULT, hence VARCHAR(512)."""

    name = "mysql"
    placeholder = "%s"
    supports_default_on_text = False

    def pk_ddl(self, column: str = "id") -> str:
        return f"{column} INT AUTO_INCREMENT PRIMARY KEY"

    def column_type(self, kind: str) -> str:
        return {"STR": "VARCHAR(512)", "TEXT": "TEXT", "INT": "INT", "REAL": "DOUBLE"}[kind]

    def create_index(self, name: str, table: str, cols: Sequence[str]) -> str:
        # MySQL has no CREATE INDEX IF NOT EXISTS; the caller tolerates errors.
        return f"CREATE INDEX {name} ON {table} ({', '.join(cols)})"

    def insert_or_replace(self, table: str, cols: Sequence[str]) -> str:
        ph = ", ".join([self.placeholder] * len(cols))
        return f"REPLACE INTO {table} ({', '.join(cols)}) VALUES ({ph})"

    def insert_or_ignore(self, table: str, cols: Sequence[str]) -> str:
        ph = ", ".join([self.placeholder] * len(cols))
        return f"INSERT IGNORE INTO {table} ({', '.join(cols)}) VALUES ({ph})"

    def table_columns_sql(self, table: str):
        return (
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name=%s",
            (table,),
        )

    def table_columns_from_rows(self, rows) -> set:
        return {r["name"] for r in rows}

    def post_connect(self, conn) -> None:
        pass


class PostgresDialect(Dialect):
    name = "postgresql"
    placeholder = "%s"

    def pk_ddl(self, column: str = "id") -> str:
        return f"{column} SERIAL PRIMARY KEY"

    def column_type(self, kind: str) -> str:
        return {"STR": "VARCHAR(512)", "TEXT": "TEXT", "INT": "INTEGER", "REAL": "DOUBLE PRECISION"}[kind]

    def create_index(self, name: str, table: str, cols: Sequence[str]) -> str:
        return f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({', '.join(cols)})"

    def insert_or_replace(self, table: str, cols: Sequence[str]) -> str:
        ph = ", ".join([self.placeholder] * len(cols))
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols)
        pk = _primary_key_of(table)
        return (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
            f"ON CONFLICT ({pk}) DO UPDATE SET {updates}"
        )

    def insert_or_ignore(self, table: str, cols: Sequence[str]) -> str:
        ph = ", ".join([self.placeholder] * len(cols))
        return (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
            "ON CONFLICT DO NOTHING"
        )

    def table_columns_sql(self, table: str):
        return (
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )

    def table_columns_from_rows(self, rows) -> set:
        return {r["name"] for r in rows}

    def last_insert_id(self, cur) -> int:
        # psycopg2 has no lastrowid; SERIAL columns keep a sequence.
        try:
            cur.execute("SELECT LASTVAL()")
            row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:  # noqa: BLE001
            return 0

    def post_connect(self, conn) -> None:
        pass


def _primary_key_of(table: str) -> str:
    for name, _kind, extra in TABLE_DEFS[table]:
        if "PRIMARY KEY" in extra.upper():
            return name
    return "id"


DIALECTS = {"sqlite": SQLiteDialect(), "mysql": MySQLDialect(), "postgresql": PostgresDialect()}


def get_dialect(db_type: Optional[str]) -> Dialect:
    return DIALECTS.get((db_type or "sqlite").lower(), DIALECTS["sqlite"])


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_cfg_lock = threading.RLock()


def _default_sqlite_path() -> str:
    return str(APP_DATA_DIR / "ytsage_sync.db")


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_FILE.exists():
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8") or "{}"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sync][db] cannot read {CONFIG_FILE}: {e}")
    cfg["type"] = (cfg.get("type") or "sqlite").lower()
    if cfg["type"] not in SUPPORTED_TYPES:
        cfg["type"] = "sqlite"
    return cfg


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    clean = dict(DEFAULT_CONFIG)
    clean.update({k: v for k, v in (cfg or {}).items() if k in DEFAULT_CONFIG})
    clean["type"] = (clean.get("type") or "sqlite").lower()
    if clean["type"] not in SUPPORTED_TYPES:
        raise ValueError(f"unsupported database type: {clean['type']}")
    with _cfg_lock:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return clean


def describe(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Config summary safe to send to the browser (no password)."""
    cfg = cfg or load_config()
    out = dict(cfg)
    out["password"] = "***" if cfg.get("password") else ""
    out["supported_types"] = list(SUPPORTED_TYPES)
    if out["type"] == "sqlite":
        out["sqlite_path"] = cfg.get("sqlite_path") or _default_sqlite_path()
    if not out.get("port"):
        out["port"] = DEFAULT_PORTS.get(out["type"], 0)
    return out


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _driver_error(db_type: str) -> RuntimeError:
    pkg = "pymysql" if db_type == "mysql" else "psycopg2-binary"
    return RuntimeError(
        f"{db_type} support needs the '{pkg}' package: pip install {pkg}"
    )


def connect(cfg: Optional[Dict[str, Any]] = None):
    """Open a connection using the given (or stored) configuration."""
    cfg = cfg or load_config()
    db_type = (cfg.get("type") or "sqlite").lower()

    if db_type == "sqlite":
        path = cfg.get("sqlite_path") or _default_sqlite_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        get_dialect("sqlite").post_connect(conn)
        return conn

    if db_type == "mysql":
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as e:  # pragma: no cover - optional driver
            raise _driver_error("mysql") from e
        return pymysql.connect(
            host=cfg.get("host") or "127.0.0.1",
            port=int(cfg.get("port") or DEFAULT_PORTS["mysql"]),
            user=cfg.get("user") or "",
            password=cfg.get("password") or "",
            database=cfg.get("database") or "ytsage",
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            ssl={"ssl": {}} if cfg.get("ssl") else None,
        )

    if db_type == "postgresql":
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as e:  # pragma: no cover - optional driver
            raise _driver_error("postgresql") from e
        conn = psycopg2.connect(
            host=cfg.get("host") or "127.0.0.1",
            port=int(cfg.get("port") or DEFAULT_PORTS["postgresql"]),
            user=cfg.get("user") or "",
            password=cfg.get("password") or "",
            dbname=cfg.get("database") or "ytsage",
            sslmode="require" if cfg.get("ssl") else "prefer",
        )
        conn.autocommit = False
        return conn

    raise ValueError(f"unsupported database type: {db_type}")


def create_schema(conn, dialect: Optional[Dialect] = None,
                  tables: Optional[Dict[str, List[Tuple[str, str, str]]]] = None,
                  indexes: Sequence[Tuple[str, str, Sequence[str]]] = ()) -> None:
    """Create tables + indexes (idempotent enough for all three engines).

    Defaults to the sync schema; pass `tables`/`indexes` to create another set
    (used by the Web UI's own task database).
    """
    dialect = dialect or get_dialect(load_config().get("type"))
    defs = tables if tables is not None else TABLE_DEFS
    idx = indexes if indexes else INDEXES
    cur = conn.cursor()
    try:
        for table in defs:
            cur.execute(dialect.create_table(table, defs))
        conn.commit()
        for name, table, cols in idx:
            try:
                cur.execute(dialect.create_index(name, table, cols))
                conn.commit()
            except Exception:  # noqa: BLE001 - index already exists is fine
                conn.rollback()
    finally:
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Migration between engines (dysync: DatabaseMigrationService)
# ---------------------------------------------------------------------------

STATUS_FILE = APP_DATA_DIR / "sync_migration_status.json"
HISTORY_FILE = APP_DATA_DIR / "sync_migration_history.json"
MIGRATION_BATCH = 500


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sync][db] cannot write {path}: {e}")


def migration_status() -> Dict[str, Any]:
    try:
        if STATUS_FILE.exists():
            return json.loads(STATUS_FILE.read_text(encoding="utf-8") or "{}")
    except Exception:  # noqa: BLE001
        pass
    return {"running": False}


def migration_history() -> List[Dict[str, Any]]:
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8") or "[]")
    except Exception:  # noqa: BLE001
        pass
    return []


def test_connection(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Try to open + use a connection. Never raises."""
    try:
        conn = connect(cfg)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    try:
        d = get_dialect((cfg.get("type") or "sqlite").lower())
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        return {"ok": True, "type": d.name}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def migrate_data(
    source_cfg: Dict[str, Any],
    target_cfg: Dict[str, Any],
    tables: Optional[List[str]] = None,
    batch_size: int = MIGRATION_BATCH,
) -> Dict[str, Any]:
    """Copy every table from one engine to another (dysync: 数据库迁移).

    The target is rebuilt from scratch (tables created, then emptied) so the
    result is an exact copy rather than a merge. Runs in batches so a large
    records table does not have to fit in memory.
    """
    tables = [t for t in (tables or list(TABLE_DEFS)) if t in TABLE_DEFS]
    d_src = get_dialect((source_cfg or {}).get("type"))
    d_dst = get_dialect((target_cfg or {}).get("type"))

    started = time.time()
    state: Dict[str, Any] = {
        "running": True, "started_at": started,
        "from": (source_cfg or {}).get("type"), "to": (target_cfg or {}).get("type"),
        "current_table": "", "tables_done": 0, "tables_total": len(tables),
        "rows_copied": 0, "copied": {}, "error": "",
    }
    _write_json(STATUS_FILE, state)

    src = dst = None
    try:
        src = connect(source_cfg)
        dst = connect(target_cfg)
        create_schema(dst, d_dst)

        for table in tables:
            state["current_table"] = table
            _write_json(STATUS_FILE, state)

            cols = [c for c, _k, _e in TABLE_DEFS[table]]
            select_cols = ", ".join(cols)
            inserts = ", ".join([d_dst.placeholder] * len(cols))
            insert_sql = f"INSERT INTO {table} ({select_cols}) VALUES ({inserts})"

            # Exact copy: drop whatever the target had for this table.
            try:
                cur = dst.cursor()
                cur.execute(f"DELETE FROM {table}")
                cur.close()
                dst.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[sync][db] cannot clear target {table}: {e}")
                try:
                    dst.rollback()
                except Exception:  # noqa: BLE001
                    pass

            copied = 0
            offset = 0
            while True:
                cur = src.cursor()
                cur.execute(
                    f"SELECT {select_cols} FROM {table} "
                    f"LIMIT {d_src.placeholder} OFFSET {d_src.placeholder}",
                    (batch_size, offset),
                )
                rows = dict_rows(cur)
                cur.close()
                if not rows:
                    break
                seq = [tuple(r.get(c) for c in cols) for r in rows]
                wcur = dst.cursor()
                wcur.executemany(insert_sql, seq)
                wcur.close()
                dst.commit()
                copied += len(rows)
                offset += len(rows)
                state["rows_copied"] = state.get("rows_copied", 0) + len(rows)
                _write_json(STATUS_FILE, state)
                if len(rows) < batch_size:
                    break

            state["copied"][table] = copied
            state["tables_done"] = state.get("tables_done", 0) + 1
            _write_json(STATUS_FILE, state)

        result = {
            "ok": True, "tables": state["copied"],
            "rows": sum(state["copied"].values()),
            "from": state["from"], "to": state["to"],
            "duration": round(time.time() - started, 2),
        }
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[sync][db] migration failed: {e}")
        state["error"] = str(e)
        _write_json(STATUS_FILE, state)
        result = {"ok": False, "error": str(e), "tables": state["copied"]}
    finally:
        state["running"] = False
        state["finished_at"] = time.time()
        _write_json(STATUS_FILE, state)
        for conn in (src, dst):
            if conn is None:
                continue
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # Keep a short history of past migrations (dysync keeps one too).
    try:
        hist = migration_history()
        hist.insert(0, {k: v for k, v in result.items() if k != "tables"})
        _write_json(HISTORY_FILE, hist[:20])
    except Exception:  # noqa: BLE001
        pass
    return result


def dict_rows(cursor) -> List[Dict[str, Any]]:
    """Normalize a cursor result into dicts for any driver."""
    try:
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(dict(r))
        elif hasattr(r, "keys"):  # sqlite3.Row
            out.append({k: r[k] for k in r.keys()})
        else:
            out.append(r)
    return out
