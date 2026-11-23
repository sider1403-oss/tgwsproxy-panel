"""Authentication and security API routes."""
from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from . import security

router = APIRouter()

SETUP_CODE_HINT = "/opt/tgws-panel/config/setup_code"


def _user_public(user: dict) -> dict:
    return {
        "username": user["username"],
        "must_change_password": bool(user.get("must_change_password")),
        "last_login_at": user.get("last_login_at"),
        "last_login_ip": user.get("last_login_ip"),
    }


@router.get("/api/auth/status")
def auth_status(request: Request, response: Response):
    session = security.load_session(request)
    if session:
        security.set_csrf_cookie(response, session["csrf"], request)
        return {
            "setup_required": False,
            "authenticated": True,
            "user": {
                "username": session["username"],
                "must_change_password": session["must_change_password"],
                "last_login_at": session["last_login_at"],
                "last_login_ip": session["last_login_ip"],
            },
            "csrf": session["csrf"],
        }

    pre = request.cookies.get(security.CSRF_COOKIE) or secrets.token_urlsafe(32)
    security.set_csrf_cookie(response, pre, request)
    return {
        "setup_required": security.setup_required(),
        "authenticated": False,
        "user": None,
        "csrf": pre,
        "setup_code_hint": SETUP_CODE_HINT if security.setup_required() else None,
    }


@router.post("/api/auth/setup")
def auth_setup(request: Request, response: Response, payload: dict = Body(...)):
    if not security.setup_required():
        raise HTTPException(403, "Первоначальная настройка уже завершена")
    ip = security.client_ip(request)
    blocked, retry = security.rate_limited(ip, "__setup__")
    if blocked:
        security.log_event("setup_blocked", request, detail=f"retry={retry}")
        raise HTTPException(429, "Слишком много попыток. Повторите позже", headers={"Retry-After": str(retry)})
    code = str(payload.get("code") or "")
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    try:
        user = security.finish_setup(username, password, code)
    except ValueError as exc:
        security.record_attempt(ip, "__setup__", False)
        security.log_event("setup_failed", request, username=username, detail=str(exc))
        time.sleep(0.7)
        raise HTTPException(400, str(exc)) from exc
    security.record_attempt(ip, "__setup__", True)
    security.mark_success(user, ip)
    sess = security.create_session(user, request)
    security.set_session_cookie(response, sess["token"], request)
    security.set_csrf_cookie(response, sess["csrf"], request)
    security.log_event("setup_admin", request, username=user["username"])
    security.log_event("login_success", request, username=user["username"], detail="setup")
    return {"ok": True, "user": _user_public(security.get_user_by_username(user["username"]) or user), "csrf": sess["csrf"]}


@router.post("/api/auth/login")
def auth_login(request: Request, response: Response, payload: dict = Body(...)):
    username = str(payload.get("username") or "").strip().lower()
    password = str(payload.get("password") or "")
    ip = security.client_ip(request)
    blocked, retry = security.rate_limited(ip, username)
    if blocked:
        security.log_event("login_blocked", request, username=username, detail=f"retry={retry}")
        raise HTTPException(429, f"Слишком много попыток. Повторите через {retry} с", headers={"Retry-After": str(retry)})

    user = security.get_user_by_username(username)
    ok = bool(user and user.get("is_active") and security.verify_password(user["password_hash"], password))
    if not user:
        security.verify_password(security.DUMMY_HASH, password)
    if not ok:
        security.record_attempt(ip, username, False)
        security.mark_failure(username)
        security.log_event("login_failed", request, username=username)
        time.sleep(0.7)
        raise HTTPException(401, "Неверный логин или пароль")

    new_hash = security.maybe_rehash(user["password_hash"], password)
    if new_hash:
        security.db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
    security.record_attempt(ip, username, True)
    security.mark_success(user, ip)
    sess = security.create_session(user, request)
    security.set_session_cookie(response, sess["token"], request)
    security.set_csrf_cookie(response, sess["csrf"], request)
    security.log_event("login_success", request, username=user["username"])
    fresh = security.get_user_by_username(user["username"]) or user
    return {"ok": True, "user": _user_public(fresh), "csrf": sess["csrf"]}


@router.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    sess = getattr(request.state, "session", None)
    if sess:
        security.revoke_session(sess["id"], sess["user_id"])
        security.log_event("logout", request, username=sess["username"])
    security.clear_session_cookie(response, request)
    response.delete_cookie(security.CSRF_COOKIE, path="/", secure=security.is_https(request))
    return {"ok": True}


@router.post("/api/auth/password")
def auth_password(request: Request, payload: dict = Body(...)):
    sess = getattr(request.state, "session", None)
    if not sess:
        raise HTTPException(401, "Not authenticated")
    current = str(payload.get("current_password") or "")
    new = str(payload.get("new_password") or "")
    user = security.get_user_by_id(sess["user_id"])
    if not user or not security.verify_password(user["password_hash"], current):
        security.log_event("password_change_failed", request, username=sess["username"])
        time.sleep(0.5)
        raise HTTPException(400, "Текущий пароль неверен")
    if current == new:
        raise HTTPException(400, "Новый пароль должен отличаться от текущего")
    try:
        security.set_password(user["id"], new)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    revoked = security.revoke_other_sessions(user["id"], sess["id"])
    security.log_event("password_changed", request, username=user["username"], detail=f"revoked_other={revoked}")
    return {"ok": True, "revoked_other": revoked}


@router.get("/api/security/overview")
def security_overview(request: Request):
    sess = getattr(request.state, "session", None)
    user = security.get_user_by_id(sess["user_id"]) if sess else None
    if not sess or not user:
        raise HTTPException(401, "Not authenticated")
    data = security.security_overview(user, sess["id"])
    data["sessions"] = security.list_sessions(user["id"], sess["id"])
    return data


@router.get("/api/security/sessions")
def security_sessions(request: Request):
    sess = getattr(request.state, "session", None)
    if not sess:
        raise HTTPException(401, "Not authenticated")
    return {"sessions": security.list_sessions(sess["user_id"], sess["id"])}


@router.delete("/api/security/sessions/{sid}")
def security_session_revoke(sid: str, request: Request, response: Response):
    sess = getattr(request.state, "session", None)
    if not sess:
        raise HTTPException(401, "Not authenticated")
    ok = security.revoke_session(sid, sess["user_id"])
    if not ok:
        raise HTTPException(404, "Сессия не найдена")
    security.log_event("session_revoked", request, username=sess["username"], detail=f"session={sid[:8]}")
    if sid == sess["id"]:
        security.clear_session_cookie(response, request)
        return {"ok": True, "current": True}
    return {"ok": True, "current": False}


@router.post("/api/security/sessions/revoke-others")
def security_revoke_others(request: Request):
    sess = getattr(request.state, "session", None)
    if not sess:
        raise HTTPException(401, "Not authenticated")
    count = security.revoke_other_sessions(sess["user_id"], sess["id"])
    security.log_event("sessions_revoked_others", request, username=sess["username"], detail=f"count={count}")
    return {"ok": True, "revoked": count}


@router.post("/api/security/sessions/revoke-all")
def security_revoke_all(request: Request, response: Response):
    sess = getattr(request.state, "session", None)
    if not sess:
        raise HTTPException(401, "Not authenticated")
    count = security.revoke_all_sessions(sess["user_id"])
    security.log_event("sessions_revoked_everywhere", request, username=sess["username"], detail=f"count={count}")
    security.clear_session_cookie(response, request)
    response.delete_cookie(security.CSRF_COOKIE, path="/", secure=security.is_https(request))
    return {"ok": True, "revoked": count}


@router.get("/api/security/events")
def security_events(request: Request, limit: int = Query(100, ge=1, le=500)):
    if not getattr(request.state, "session", None):
        raise HTTPException(401, "Not authenticated")
    return {"events": security.security_events(limit)}


@router.get("/api/security/attempts")
def security_attempts(request: Request, limit: int = Query(50, ge=1, le=200)):
    if not getattr(request.state, "session", None):
        raise HTTPException(401, "Not authenticated")
    return {"attempts": security.failed_attempts(limit)}
