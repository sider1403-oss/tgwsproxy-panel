"""SQLite storage for the panel: sessions, events, samples and metadata."""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from . import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_ip TEXT NOT NULL,
    client_port INTEGER,
    dc INTEGER,
    media INTEGER DEFAULT 0,
    kind TEXT,
    closed_by TEXT,
    bytes_up INTEGER DEFAULT 0,
    bytes_down INTEGER DEFAULT 0,
    duration REAL DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    line TEXT,
    line_hash TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_sessions_ended ON sessions(ended_at);
CREATE INDEX IF NOT EXISTS idx_sessions_ip ON sessions(client_ip);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    category TEXT NOT NULL DEFAULT 'info',
    module TEXT,
    ip TEXT,
    message TEXT NOT NULL,
    line TEXT,
    line_hash TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_level ON events(level);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    conns INTEGER DEFAULT 0,
    rx INTEGER DEFAULT 0,
    tx INTEGER DEFAULT 0,
    speed_in REAL DEFAULT 0,
    speed_out REAL DEFAULT 0,
    cpu_host REAL DEFAULT 0,
    mem_used INTEGER DEFAULT 0,
    cpu_proxy REAL DEFAULT 0,
    mem_proxy INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);

CREATE TABLE IF NOT EXISTS key_meta (
    key TEXT PRIMARY KEY,
    comment TEXT DEFAULT '',
    created_at TEXT,
    disabled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);

CREATE TABLE IF NOT EXISTS log_files (
    inode TEXT PRIMARY KEY,
    path TEXT,
    offset INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS connection_seen (
    id TEXT PRIMARY KEY,
    first_seen TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    ok INTEGER DEFAULT 1,
    ip TEXT,
    duration_ms INTEGER,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);

CREATE TABLE IF NOT EXISTS diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    ok INTEGER DEFAULT 0,
    status TEXT,
    summary TEXT,
    detail TEXT,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_diag_ts ON diagnostics(ts);

CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    rule TEXT,
    level TEXT,
    message TEXT,
    delivered INTEGER DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_ts ON alert_log(ts);

CREATE TABLE IF NOT EXISTS device_hints (
    ip TEXT PRIMARY KEY,
    family TEXT,
    label TEXT,
    ttl INTEGER,
    window INTEGER,
    mss INTEGER,
    ws INTEGER,
    ts INTEGER,
    sack INTEGER,
    options TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS device_labels (
    ip TEXT PRIMARY KEY,
    family TEXT,
    label TEXT,
    updated_at TEXT
);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(settings.DB_PATH, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA journal_size_limit=8388608")
        c.execute("PRAGMA wal_autocheckpoint=1000")
        c.executescript(SCHEMA)
        c.commit()
        _conn = c
    return _conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    # trim nanoseconds to microseconds
    if "." in v:
        head, tail = v.split(".", 1)
        frac = "".join(ch for ch in tail if ch.isdigit())[:6]
        tz = ""
        for i, ch in enumerate(tail):
            if ch in "+-":
                tz = tail[i:]
                break
        v = f"{head}.{frac}{tz}" if tz else f"{head}.{frac}"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        c = conn()
        cur = c.execute(sql, params)
        c.commit()
        return cur


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _lock:
        return conn().execute(sql, params).fetchone()


def get_meta(key: str, default: str | None = None) -> str | None:
    row = query_one("SELECT v FROM meta WHERE k=?", (key,))
    return row["v"] if row else default


def set_meta(key: str, value: str) -> None:
    execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))


def bulk_insert_events(items: list[dict]) -> int:
    if not items:
        return 0
    rows = [
        (
            i["ts"],
            i["level"],
            i["category"],
            i.get("module"),
            i.get("ip"),
            i["message"],
            i["line"],
            hashlib.sha1(i["line"].encode("utf-8", "replace")).hexdigest(),
        )
        for i in items
    ]
    with _lock:
        c = conn()
        before = c.total_changes
        c.executemany(
            "INSERT OR IGNORE INTO events(ts,level,category,module,ip,message,line,line_hash) "
            "VALUES(?,?,?,?,?,?,?,?)",
            rows,
        )
        c.commit()
        return c.total_changes - before


def bulk_insert_sessions(items: list[dict]) -> int:
    if not items:
        return 0
    rows = []
    for i in items:
        started = parse_iso(i["ended_at"])
        started_at = iso(started - timedelta(seconds=i["duration"])) if started else None
        rows.append(
            (
                i["client_ip"],
                i["client_port"],
                i["dc"],
                1 if i["media"] else 0,
                i["kind"],
                i["closed_by"],
                i["bytes_up"],
                i["bytes_down"],
                i["duration"],
                started_at,
                i["ended_at"],
                i["line"],
                hashlib.sha1(i["line"].encode("utf-8", "replace")).hexdigest(),
            )
        )
    with _lock:
        c = conn()
        before = c.total_changes
        c.executemany(
            "INSERT OR IGNORE INTO sessions(client_ip,client_port,dc,media,kind,closed_by,bytes_up,bytes_down,"
            "duration,started_at,ended_at,line,line_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        c.commit()
        return c.total_changes - before


def insert_event(
    *,
    ts: str,
    level: str,
    category: str,
    module: str | None,
    ip: str | None,
    message: str,
    line: str,
) -> bool:
    h = hashlib.sha1(line.encode("utf-8", "replace")).hexdigest()
    with _lock:
        c = conn()
        try:
            c.execute(
                "INSERT INTO events(ts,level,category,module,ip,message,line,line_hash) VALUES(?,?,?,?,?,?,?,?)",
                (ts, level, category, module, ip, message, line, h),
            )
            c.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def insert_session(
    *,
    client_ip: str,
    client_port: int,
    dc: int,
    media: bool,
    kind: str,
    closed_by: str,
    bytes_up: int,
    bytes_down: int,
    duration: float,
    ended_at: str,
    line: str,
) -> bool:
    h = hashlib.sha1(line.encode("utf-8", "replace")).hexdigest()
    started = parse_iso(ended_at)
    started_at = iso(started - timedelta(seconds=duration)) if started else None
    with _lock:
        c = conn()
        try:
            c.execute(
                "INSERT INTO sessions(client_ip,client_port,dc,media,kind,closed_by,bytes_up,bytes_down,"
                "duration,started_at,ended_at,line,line_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    client_ip,
                    client_port,
                    dc,
                    1 if media else 0,
                    kind,
                    closed_by,
                    bytes_up,
                    bytes_down,
                    duration,
                    started_at,
                    ended_at,
                    line,
                    h,
                ),
            )
            c.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def prune() -> None:
    """Bound the database: time retention, row caps and a hard size guard."""
    now = datetime.now(timezone.utc)
    event_cutoff = iso(now - timedelta(days=settings.KEEP_DAYS))
    session_cutoff = iso(now - timedelta(days=settings.KEEP_SESSIONS_DAYS))
    audit_cutoff = iso(now - timedelta(days=30))
    seen_cutoff = iso(now - timedelta(days=2))
    with _lock:
        c = conn()
        c.execute("DELETE FROM events WHERE ts < ?", (event_cutoff,))
        c.execute("DELETE FROM samples WHERE ts < ?", (event_cutoff,))
        c.execute("DELETE FROM sessions WHERE ended_at < ?", (session_cutoff,))
        c.execute("DELETE FROM connection_seen WHERE first_seen < ?", (seen_cutoff,))
        c.execute("DELETE FROM audit WHERE ts < ?", (audit_cutoff,))
        c.execute(
            "DELETE FROM device_hints WHERE updated_at < ?",
            (iso(now - timedelta(days=180)),),
        )

        for table, max_rows in (("events", settings.KEEP_EVENTS_MAX), ("sessions", settings.KEEP_SESSIONS_MAX)):
            total = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if total > max_rows:
                c.execute(
                    f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} ORDER BY id ASC LIMIT ?)",
                    (total - max_rows,),
                )
        c.commit()
        try:
            c.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.Error:
            pass

        # Hard guard: if the database still exceeds the limit, keep only the
        # newest rows and compact the file so it cannot grow without bound.
        try:
            size = settings.DB_PATH.stat().st_size
        except OSError:
            size = 0
        limit = settings.DB_SIZE_LIMIT_MB * 1024 * 1024
        if size > limit:
            for table, keep_rows in (("events", 50000), ("sessions", 50000), ("samples", 50000)):
                total = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if total > keep_rows:
                    c.execute(
                        f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} ORDER BY id ASC LIMIT ?)",
                        (total - keep_rows,),
                    )
            c.commit()
            try:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            try:
                c.execute("VACUUM")
            except sqlite3.Error:
                pass
