"""Parse the proxy's tracing log lines into sessions and events."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import db, dockerctl, settings

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MSG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+(?P<level>[A-Z]+)\s+"
    r"(?P<module>\S+):\s?(?P<msg>.*)$"
)
LEVEL_RE = re.compile(r"\b(INFO|WARN|WARNING|ERROR|DEBUG|TRACE)\b")
SESSION_RE = re.compile(
    r"^\[(?P<ip>[^\]]+):(?P<port>\d+)\] DC(?P<dc>\d+)(?P<media>m)? (?P<kind>.+?) "
    r"session closed by (?P<by>client|upstream): ↑(?P<up>[0-9.]+(?:[KMGTP]?B))\s+"
    r"↓(?P<down>[0-9.]+(?:[KMGTP]?B))\s+(?P<dur>[0-9.]+)s$"
)
SIZE_RE = re.compile(r"^([0-9.]+)([KMGTP]?B)$")
VERSION_BANNER_RE = re.compile(r"tg-ws-proxy-rs v(\d+\.\d+\.\d+)")
SIZE_MULT = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4, "PB": 1024**5}


def human_to_bytes(value: str) -> int:
    m = SIZE_RE.match(value.strip())
    if not m:
        return 0
    return int(round(float(m.group(1)) * SIZE_MULT.get(m.group(2), 1)))


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def categorize(level: str, message: str) -> str:
    low = message.lower()
    if "session closed by" in low:
        return "session"
    if level == "ERROR":
        return "error"
    if any(k in low for k in ("cooldown", "cf proxy", "background probe", "tcp fallback", "upstream", "pool:", "ws ", "cf ws")):
        return "upstream"
    if level in ("WARN", "WARNING"):
        return "error"
    if "telegram mtproto ws bridge proxy" in low or "listening on" in low or "cloudflare proxy domain" in low:
        return "system"
    if "tg-ws-proxy" in low and "v" in low:
        return "system"
    return "info"


def parse_message(raw_line: str, fallback_ts: str) -> dict | None:
    line = strip_ansi(raw_line).rstrip("\r\n")
    if not line.strip():
        return None
    ts = fallback_ts
    level = "INFO"
    module = None
    message = line
    m = MSG_RE.match(line)
    if m:
        ts = m.group("ts")
        level = m.group("level")
        module = m.group("module")
        message = m.group("msg")
    else:
        lm = LEVEL_RE.search(line)
        if lm:
            level = lm.group(1)
        parsed = db.parse_iso(ts)
        ts = db.iso(parsed) if parsed else fallback_ts
    parsed_ts = db.parse_iso(ts)
    if parsed_ts is None:
        parsed_ts = db.parse_iso(fallback_ts) or datetime.now(timezone.utc)
    ts = db.iso(parsed_ts)
    if level == "WARNING":
        level = "WARN"
    if level == "TRACE":
        level = "DEBUG"

    ip = None
    im = re.match(r"^\[([^\]]+):(\d+)\]", message)
    if im:
        ip = im.group(1)

    event = {
        "ts": ts,
        "level": level,
        "category": categorize(level, message),
        "module": module,
        "ip": ip,
        "message": message,
        "line": line,
    }

    session = None
    sm = SESSION_RE.match(message)
    if sm:
        session = {
            "client_ip": sm.group("ip"),
            "client_port": int(sm.group("port")),
            "dc": int(sm.group("dc")),
            "media": bool(sm.group("media")),
            "kind": sm.group("kind").strip(),
            "closed_by": sm.group("by"),
            "bytes_up": human_to_bytes(sm.group("up")),
            "bytes_down": human_to_bytes(sm.group("down")),
            "duration": float(sm.group("dur")),
            "ended_at": ts,
            "line": line,
        }
    return {"event": event, "session": session}


class LogIngestor:
    def __init__(self) -> None:
        self._last_container: str | None = None

    def _log_files(self) -> list[Path]:
        info = dockerctl.inspect_container()
        if not info:
            return []
        log_path = info.get("LogPath")
        if not log_path:
            return []
        base = Path(log_path)
        if not base.exists():
            return []
        files = [base]
        try:
            files.extend(sorted(base.parent.glob(base.name + ".*")))
        except OSError:
            pass
        # Process oldest first, current file last.
        files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0)
        return files

    def _offset_for(self, inode: str, path: Path) -> int:
        row = db.query_one("SELECT offset FROM log_files WHERE inode=?", (inode,))
        if row is None:
            return 0
        offset = int(row["offset"])
        try:
            if offset > path.stat().st_size:
                return 0
        except OSError:
            return 0
        return offset

    def ingest(self) -> tuple[int, int]:
        events: list[dict] = []
        sessions: list[dict] = []
        for path in self._log_files():
            try:
                st = path.stat()
            except OSError:
                continue
            inode = str(st.st_ino)
            offset = self._offset_for(inode, path)
            try:
                with open(path, "rb") as fh:
                    fh.seek(offset)
                    data = fh.read()
            except OSError:
                continue
            if not data:
                continue
            complete = data.split(b"\n")
            # The last chunk is not newline-terminated: leave it for the next pass.
            tail = complete.pop() if complete and not data.endswith(b"\n") else b""
            consumed = len(data) - len(tail)
            for raw in complete:
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                text = obj.get("log", "")
                entry_ts = obj.get("time") or db.now_iso()
                parsed = parse_message(text, entry_ts)
                if not parsed:
                    continue
                events.append(parsed["event"])
                if parsed["session"]:
                    sessions.append(parsed["session"])
                banner = VERSION_BANNER_RE.search(parsed["event"]["message"])
                if banner:
                    db.set_meta("proxy_version", banner.group(1))
            new_offset = offset + consumed
            db.execute(
                "INSERT INTO log_files(inode,path,offset) VALUES(?,?,?) "
                "ON CONFLICT(inode) DO UPDATE SET offset=excluded.offset, path=excluded.path",
                (inode, str(path), new_offset),
            )
        nev = db.bulk_insert_events(events)
        ns = db.bulk_insert_sessions(sessions)
        return nev, ns

    def reset_for_new_container(self) -> None:
        """Nothing to do: offsets are keyed by inode, a new container has new files."""
        self._last_container = None


def read_all_backlog() -> tuple[int, int]:
    return LogIngestor().ingest()
