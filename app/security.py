"""Authentication, sessions, CSRF, rate limiting and the security journal.

The panel runs on a trusted LAN; this module adds a single-admin login with
Argon2id password hashes, server-side sessions in SQLite, CSRF protection and
an audit trail of security events.  No secret or password is ever written to
logs or returned by the list APIs.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request, Response

from . import db, logutil, settings

COOKIE_NAME = "tgws_session"
CSRF_COOKIE = "tgws_csrf"

IDLE_MINUTES = max(5, settings.SESSION_IDLE_MINUTES)
ABSOLUTE_HOURS = max(1, settings.SESSION_ABSOLUTE_HOURS)

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
DUMMY_HASH = _hasher.hash("not-a-real-password-for-timing")
_unauth_last: dict[str, float] = {}
_unauth_lock = threading.Lock()

COMMON_PASSWORDS = {
    "password",
    "password123",
    "password1234",
    "admin",
    "admin123",
    "administrator",
    "qwerty",
    "qwerty123",
    "123456789012",
    "letmein",
    "welcome",
    "tgwsproxy",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return db.iso(_now())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _trusted_networks() -> list[ipaddress._BaseNetwork]:
    raw = (settings.TRUSTED_PROXIES or "").strip()
    result = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return result


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return "—"
    peer = request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            peer_ip = None
        if peer_ip and any(peer_ip in net for net in _trusted_networks()):
            first = forwarded.split(",")[0].strip()
            try:
                ipaddress.ip_address(first)
                return first
            except ValueError:
                pass
    return peer


def is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if request.client:
        try:
            peer = ipaddress.ip_address(request.client.host)
        except ValueError:
            peer = None
        if peer and any(peer in net for net in _trusted_networks()):
            proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
            return proto == "https"
    return False


def _allowed_origins() -> set[str]:
    port = settings.PANEL_PORT
    origins = {
        f"http://{settings.PUBLIC_HOST}:{port}",
        f"https://{settings.PUBLIC_HOST}:{port}",
        f"http://localhost:{port}",
        f"https://localhost:{port}",
        f"http://127.0.0.1:{port}",
        f"https://127.0.0.1:{port}",
    }
    for item in (settings.ALLOWED_ORIGINS or "").split(","):
        item = item.strip().rstrip("/")
        if item:
            origins.add(item)
    return {x.rstrip("/") for x in origins}


def origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}"
    if not origin:
        return True  # non-browser clients still need CSRF
    return origin.rstrip("/") in _allowed_origins()


# ── passwords ────────────────────────────────────────────────────────────────

def validate_password(password: str, username: str) -> str | None:
    if len(password) < 12:
        return "Пароль должен быть не короче 12 символов"
    if len(password) > 256:
        return "Пароль слишком длинный"
    if password.lower() == (username or "").lower():
        return "Пароль не должен совпадать с логином"
    if password.lower() in COMMON_PASSWORDS:
        return "Пароль слишком распространён"
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        return "Пароль должен содержать буквы и цифры"
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def maybe_rehash(password_hash: str, password: str) -> str | None:
    try:
        if _hasher.check_needs_rehash(password_hash):
            return _hasher.hash(password)
    except (VerificationError, InvalidHashError):
        return None
    return None


# ── users ────────────────────────────────────────────────────────────────────

def user_count() -> int:
    return int(db.query_one("SELECT COUNT(*) AS n FROM users")["n"])


def setup_required() -> bool:
    return user_count() == 0


def get_user_by_username(username: str) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE username=?", (username.strip().lower(),))
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    return dict(row) if row else None


def create_admin(username: str, password: str, must_change: bool = False) -> dict:
    username = (username or "").strip().lower()
    if not username or len(username) > 64 or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
        raise ValueError("Логин: 1–64 символа, буквы/цифры/._-")
    if username in {"admin", "root", "administrator", "user", "guest"}:
        raise ValueError("Этот логин зарезервирован; выберите другой")
    error = validate_password(password, username)
    if error:
        raise ValueError(error)
    if get_user_by_username(username):
        raise ValueError("Пользователь уже существует")
    db.execute(
        "INSERT INTO users(username,password_hash,is_active,is_admin,must_change_password,created_at) "
        "VALUES(?,?,1,1,?,?)",
        (username, hash_password(password), 1 if must_change else 0, now_iso()),
    )
    return get_user_by_username(username) or {}


def set_password(user_id: int, password: str) -> None:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    error = validate_password(password, user["username"])
    if error:
        raise ValueError(error)
    db.execute(
        "UPDATE users SET password_hash=?,must_change_password=0,failed_login_count=0,locked_until=NULL WHERE id=?",
        (hash_password(password), user_id),
    )


# ── first-run setup ──────────────────────────────────────────────────────────

def _setup_code_path():
    return settings.CONFIG_DIR / "setup_code"


def ensure_setup_state() -> None:
    """First-run page is open while there is no admin; remove the legacy setup code."""
    settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        settings.CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    try:
        _setup_code_path().unlink()
    except OSError:
        pass


def finish_setup(username: str, password: str) -> dict:
    if not setup_required():
        raise ValueError("Администратор уже создан")
    user = create_admin(username, password, must_change=False)
    try:
        _setup_code_path().unlink()
    except OSError:
        pass
    return user


# ── sessions ─────────────────────────────────────────────────────────────────

def _idle_expiry(base: datetime) -> datetime:
    return base + timedelta(minutes=IDLE_MINUTES)


def _absolute_expiry(base: datetime) -> datetime:
    return base + timedelta(hours=ABSOLUTE_HOURS)


def create_session(user: dict, request: Request) -> dict:
    sid = secrets.token_hex(8)
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = _now()
    db.execute(
        "INSERT INTO auth_sessions(id,token_hash,user_id,csrf_token,created_at,last_seen,idle_expires_at,expires_at,ip,user_agent) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            sid,
            token_hash(token),
            user["id"],
            csrf,
            db.iso(now),
            db.iso(now),
            db.iso(_idle_expiry(now)),
            db.iso(_absolute_expiry(now)),
            client_ip(request),
            (request.headers.get("user-agent") or "")[:300],
        ),
    )
    return {"token": token, "csrf": csrf, "sid": sid}


def load_session(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    row = db.query_one(
        "SELECT s.*, u.username, u.is_active, u.must_change_password, u.last_login_at, u.last_login_ip "
        "FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked=0",
        (token_hash(raw),),
    )
    if not row:
        return None
    now = _now()
    idle = db.parse_iso(row["idle_expires_at"])
    absolute = db.parse_iso(row["expires_at"])
    if not idle or not absolute or now >= idle or now >= absolute or not row["is_active"]:
        db.execute("UPDATE auth_sessions SET revoked=1 WHERE id=?", (row["id"],))
        return None
    last_seen = db.parse_iso(row["last_seen"])
    if not last_seen or (now - last_seen).total_seconds() > 60:
        db.execute(
            "UPDATE auth_sessions SET last_seen=?, idle_expires_at=? WHERE id=?",
            (db.iso(now), db.iso(_idle_expiry(now)), row["id"]),
        )
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "csrf": row["csrf_token"],
        "must_change_password": bool(row["must_change_password"]),
        "last_login_at": row["last_login_at"],
        "last_login_ip": row["last_login_ip"],
        "ip": row["ip"],
        "created_at": row["created_at"],
        "last_seen": row["last_seen"],
        "expires_at": row["expires_at"],
    }


def set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=ABSOLUTE_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=is_https(request),
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=is_https(request), httponly=True, samesite="lax")


def set_csrf_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=max(600, ABSOLUTE_HOURS * 3600),
        httponly=True,
        samesite="lax",
        secure=is_https(request),
        path="/",
    )


def revoke_session(sid: str, user_id: int) -> bool:
    cur = db.query_one("SELECT id FROM auth_sessions WHERE id=? AND user_id=? AND revoked=0", (sid, user_id))
    if not cur:
        return False
    db.execute("UPDATE auth_sessions SET revoked=1 WHERE id=?", (sid,))
    return True


def revoke_other_sessions(user_id: int, keep_sid: str) -> int:
    rows = db.query("SELECT id FROM auth_sessions WHERE user_id=? AND revoked=0 AND id<>?", (user_id, keep_sid))
    for row in rows:
        db.execute("UPDATE auth_sessions SET revoked=1 WHERE id=?", (row["id"],))
    return len(rows)


def revoke_all_sessions(user_id: int) -> int:
    rows = db.query("SELECT id FROM auth_sessions WHERE user_id=? AND revoked=0", (user_id,))
    db.execute("UPDATE auth_sessions SET revoked=1 WHERE user_id=?", (user_id,))
    return len(rows)


def list_sessions(user_id: int, current_sid: str) -> list[dict]:
    rows = db.query(
        "SELECT id,ip,user_agent,created_at,last_seen,expires_at,revoked FROM auth_sessions "
        "WHERE user_id=? AND revoked=0 AND expires_at>? AND idle_expires_at>? ORDER BY last_seen DESC",
        (user_id, now_iso(), now_iso()),
    )
    out = []
    for row in rows:
        d = dict(row)
        d["current"] = d["id"] == current_sid
        d["revoked"] = bool(d["revoked"])
        out.append(d)
    return out


# ── CSRF / origin ────────────────────────────────────────────────────────────

def csrf_matches(request: Request, expected: str) -> bool:
    supplied = request.headers.get("x-csrf-token") or ""
    return bool(expected) and secrets.compare_digest(supplied, expected)


def pre_csrf_matches(request: Request) -> bool:
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    supplied = request.headers.get("x-csrf-token") or ""
    return bool(cookie) and bool(supplied) and secrets.compare_digest(cookie, supplied)


# ── rate limiting ────────────────────────────────────────────────────────────

def record_attempt(ip: str, username: str, success: bool) -> None:
    db.execute(
        "INSERT INTO auth_attempts(ts,ip,username,success) VALUES(?,?,?,?)",
        (now_iso(), ip, (username or "")[:64], 1 if success else 0),
    )
    db.execute(
        "DELETE FROM auth_attempts WHERE id NOT IN (SELECT id FROM auth_attempts ORDER BY id DESC LIMIT 10000)"
    )


def rate_limited(ip: str, username: str) -> tuple[bool, int]:
    """Return (blocked, retry_after_seconds)."""
    now = _now()
    since_15 = db.iso(now - timedelta(minutes=15))
    since_1 = db.iso(now - timedelta(minutes=1))
    user = get_user_by_username(username)
    if user and user.get("locked_until"):
        locked = db.parse_iso(user["locked_until"])
        if locked and locked > now:
            return True, max(1, int((locked - now).total_seconds()))
    per_user = db.query_one(
        "SELECT COUNT(*) AS n FROM auth_attempts WHERE ip=? AND username=? AND success=0 AND ts>=?",
        (ip, (username or "").lower(), since_15),
    )["n"]
    if per_user >= 5:
        return True, 900
    per_ip = db.query_one(
        "SELECT COUNT(*) AS n FROM auth_attempts WHERE ip=? AND success=0 AND ts>=?", (ip, since_15)
    )["n"]
    if per_ip >= 20:
        return True, 900
    burst = db.query_one("SELECT COUNT(*) AS n FROM auth_attempts WHERE ip=? AND ts>=?", (ip, since_1))["n"]
    if burst >= 20:
        return True, 60
    return False, 0


def mark_failure(username: str) -> None:
    user = get_user_by_username(username)
    if not user:
        return
    count = int(user.get("failed_login_count") or 0) + 1
    locked = None
    if count >= 5:
        locked = db.iso(_now() + timedelta(minutes=15))
    db.execute(
        "UPDATE users SET failed_login_count=?, locked_until=? WHERE id=?",
        (count, locked, user["id"]),
    )


def mark_success(user: dict, ip: str) -> None:
    db.execute(
        "UPDATE users SET failed_login_count=0,locked_until=NULL,last_login_at=?,last_login_ip=? WHERE id=?",
        (now_iso(), ip, user["id"]),
    )


# ── security journal ─────────────────────────────────────────────────────────

def log_event(event: str, request: Request | None = None, username: str | None = None, detail: str | None = None) -> None:
    ip = client_ip(request) if request is not None else None
    ua = (request.headers.get("user-agent") or "")[:300] if request is not None else None
    if detail:
        detail = str(detail)[:1000]
    db.execute(
        "INSERT INTO security_events(ts,event,username,ip,user_agent,detail) VALUES(?,?,?,?,?,?)",
        (now_iso(), event, username, ip, ua, detail),
    )
    db.execute(
        "DELETE FROM security_events WHERE id NOT IN (SELECT id FROM security_events ORDER BY id DESC LIMIT 20000)"
    )


def log_unauthorized(request: Request) -> None:
    ip = client_ip(request)
    now = time.time()
    with _unauth_lock:
        last = _unauth_last.get(ip, 0.0)
        if now - last < 60:
            return
        _unauth_last[ip] = now
    log_event("unauthorized_api", request, detail=f"{request.method} {request.url.path}")


def cleanup() -> None:
    now = _now()
    old_sessions = db.iso(now - timedelta(days=7))
    db.execute("DELETE FROM auth_sessions WHERE expires_at < ? OR (revoked=1 AND last_seen < ?)", (db.iso(now), old_sessions))
    db.execute("DELETE FROM auth_attempts WHERE ts < ?", (db.iso(now - timedelta(days=30)),))
    db.execute("DELETE FROM security_events WHERE ts < ?", (db.iso(now - timedelta(days=90)),))


def harden_permissions() -> None:
    """Keep panel data/secrets readable only by the panel user.

    Backups are owned by root and managed exclusively by the privileged helper;
    the panel must not chmod or traverse them.
    """
    for path, mode in (
        (settings.DATA_DIR, 0o700),
        (settings.CONFIG_DIR, 0o700),
        (settings.LOG_DIR, 0o750),
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(mode)
        except OSError:
            pass
    for path in (settings.DB_PATH, settings.DB_PATH.with_name(settings.DB_PATH.name + "-wal"), settings.DB_PATH.with_name(settings.DB_PATH.name + "-shm")):
        try:
            if path.exists():
                path.chmod(0o600)
        except OSError:
            pass


def security_overview(user: dict, sid: str) -> dict:
    failed_24 = db.query_one(
        "SELECT COUNT(*) AS n FROM auth_attempts WHERE success=0 AND ts>=?",
        (db.iso(_now() - timedelta(hours=24)),),
    )["n"]
    active = db.query_one(
        "SELECT COUNT(*) AS n FROM auth_sessions WHERE user_id=? AND revoked=0 AND expires_at>? AND idle_expires_at>?",
        (user["id"], now_iso(), now_iso()),
    )["n"]
    last_fail = db.query_one(
        "SELECT ts,ip,username FROM auth_attempts WHERE success=0 ORDER BY id DESC LIMIT 1"
    )
    return {
        "username": user["username"],
        "last_login_at": user.get("last_login_at"),
        "last_login_ip": user.get("last_login_ip"),
        "failed_24h": failed_24,
        "active_sessions": active,
        "last_failed": dict(last_fail) if last_fail else None,
        "current_session": sid,
    }


def security_events(limit: int = 100) -> list[dict]:
    rows = db.query(
        "SELECT id,ts,event,username,ip,user_agent,detail FROM security_events ORDER BY id DESC LIMIT ?",
        (min(max(limit, 1), 500),),
    )
    return [dict(r) for r in rows]


def failed_attempts(limit: int = 50) -> list[dict]:
    rows = db.query(
        "SELECT ts,ip,username FROM auth_attempts WHERE success=0 ORDER BY id DESC LIMIT ?",
        (min(max(limit, 1), 200),),
    )
    return [dict(r) for r in rows]


def ensure_admin_or_setup() -> None:
    """Startup helper: setup code + cleanup."""
    ensure_setup_state()
    cleanup()


def must_change_allowed(path: str) -> bool:
    return path.startswith("/api/auth/") or path.startswith("/api/security/") or path == "/api/health"
