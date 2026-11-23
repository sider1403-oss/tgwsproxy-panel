"""Manage the MTProto proxy secrets (keys) stored in the proxy's own config."""
from __future__ import annotations

import hashlib
import re
import secrets as pysecrets

from . import config_editor, db, settings


def split_secrets(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in str(value).split(",") if p.strip()]


def key_of(raw: str) -> str | None:
    s = raw.strip()
    if s[:2].lower() in ("ee", "dd") and len(s) >= 34:
        candidate = s[2:34]
    elif len(s) == 32:
        candidate = s
    else:
        candidate = s[:32] if len(s) > 32 else s
    return candidate.lower() if len(candidate) == 32 else None


def key_id(key: str) -> str:
    """Stable opaque identifier so the list API never returns the secret itself."""
    return hashlib.sha256(key.lower().encode("utf-8")).hexdigest()[:16]


def mask_link(link: str | None) -> str | None:
    if not link:
        return None
    return re.sub(r"(secret=)[^&]+", r"\1********", link)


def link_for(key: str, env: dict, host: str | None = None) -> str:
    ip = host or env.get("TG_LINK_IP") or settings.PUBLIC_HOST
    port = env.get("TG_PORT") or "1443"
    domain = (env.get("TG_LISTEN_FAKETLS_DOMAIN") or "").strip()
    if domain:
        secret = "ee" + key + domain.encode("utf-8").hex()
    else:
        secret = "dd" + key
    return f"tg://proxy?server={ip}&port={port}&secret={secret}"


def lan_host() -> str | None:
    host = (settings.PUBLIC_HOST or "").strip()
    if host in ("", "127.0.0.1", "localhost", "0.0.0.0", "::1"):
        return None
    return host


def links_for(key: str, env: dict) -> dict:
    """Both a LAN link and the advertised (possibly public) link.

    LAN clients must use the LAN address: when they dial the public IP through
    the router's port forward, hairpin NAT may rewrite the source to the
    firewall address (e.g. 192.168.50.1) and the real client IP is lost.
    """
    external = (env.get("TG_LINK_IP") or "").strip() or lan_host() or settings.PUBLIC_HOST
    lan = lan_host()
    return {
        "link": link_for(key, env, external),
        "link_external": link_for(key, env, external),
        "link_lan": link_for(key, env, lan) if lan else None,
    }


def public_links(key: str, env: dict) -> dict:
    full = links_for(key, env)
    return {
        "link_lan": mask_link(full["link_lan"]),
        "link_external": mask_link(full["link_external"]),
    }


def resolve_key(identifier: str) -> str | None:
    """Resolve an opaque key id to the real secret (never expose this to clients)."""
    identifier = (identifier or "").strip().lower()
    if not identifier:
        return None
    env = config_editor.effective_env()
    for raw in split_secrets(env.get("TG_SECRET")):
        key = key_of(raw)
        if key and key_id(key) == identifier:
            return key
    for row in db.query("SELECT key FROM key_meta"):
        key = str(row["key"]).lower()
        if key_id(key) == identifier:
            return key
    return None


def _meta(key: str) -> dict:
    row = db.query_one("SELECT comment, created_at, disabled FROM key_meta WHERE key=?", (key,))
    if row:
        return {"comment": row["comment"] or "", "created_at": row["created_at"], "disabled": bool(row["disabled"])}
    return {"comment": "", "created_at": None, "disabled": False}


def list_keys() -> dict:
    env = config_editor.effective_env()
    raws = split_secrets(env.get("TG_SECRET"))
    active = []
    seen = set()
    for raw in raws:
        key = key_of(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        meta = _meta(key)
        active.append(
            {
                "id": key_id(key),
                "masked": key[:4] + "…" + key[-4:],
                "enabled": True,
                "comment": meta["comment"],
                "created_at": meta["created_at"],
                **public_links(key, env),
            }
        )
    disabled = []
    for row in db.query("SELECT key, comment, created_at FROM key_meta WHERE disabled=1 ORDER BY created_at DESC"):
        if row["key"] in seen:
            continue
        disabled.append(
            {
                "id": key_id(row["key"]),
                "masked": row["key"][:4] + "…" + row["key"][-4:],
                "enabled": False,
                "comment": row["comment"] or "",
                "created_at": row["created_at"],
                **public_links(row["key"], env),
            }
        )
    return {
        "keys": active,
        "disabled": disabled,
        "total": len(active) + len(disabled),
        "secret_source": "env_file" if "${TG_SECRET" in str(config_editor.service_env().get("TG_SECRET", "")) else "compose",
        "stats_supported": False,
        "stats_note": (
            "tg-ws-proxy 2.7.2 не пишет использованный секрет (ключ) в лог: каждая строка сессии "
            "содержит только IP клиента, DC, объём и длительность. Поэтому раздельная статистика "
            "по ключам (подключения, трафик, последнее подключение) технически недоступна — "
            "панель показывает только глобальную статистику."
        ),
        "lan_host": lan_host(),
        "external_host": (env.get("TG_LINK_IP") or "").strip() or lan_host() or settings.PUBLIC_HOST,
        "reveal_required": True,
    }


def _apply_raws(raws: list[str], tag: str) -> dict:
    if not raws:
        raise ValueError("Нельзя оставить прокси без ключей: нужен хотя бы один")
    return config_editor.apply(secret_value=",".join(raws), tag=tag)


def add_key(comment: str = "") -> dict:
    env = config_editor.effective_env()
    raws = split_secrets(env.get("TG_SECRET"))
    key = pysecrets.token_hex(16)
    if any(key_of(r) == key for r in raws):
        raise ValueError("Сгенерированный ключ совпал с существующим, повторите")
    result = _apply_raws(raws + [key], "keys:add")
    if not result.get("ok"):
        return result
    db.execute(
        "INSERT INTO key_meta(key,comment,created_at,disabled) VALUES(?,?,?,0) "
        "ON CONFLICT(key) DO UPDATE SET disabled=0",
        (key, comment.strip(), db.now_iso()),
    )
    result["key"] = key
    result["id"] = key_id(key)
    result.update(links_for(key, config_editor.effective_env()))
    return result


def set_comment(key: str, comment: str) -> dict:
    key = key.lower()
    row = db.query_one("SELECT key FROM key_meta WHERE key=?", (key,))
    if row is None:
        db.execute(
            "INSERT INTO key_meta(key,comment,created_at,disabled) VALUES(?,?,?,0)",
            (key, comment.strip(), db.now_iso()),
        )
    else:
        db.execute("UPDATE key_meta SET comment=? WHERE key=?", (comment.strip(), key))
    return {"ok": True, "comment": comment.strip()}


def disable_key(key: str) -> dict:
    key = key.lower()
    env = config_editor.effective_env()
    raws = split_secrets(env.get("TG_SECRET"))
    remaining = [r for r in raws if key_of(r) != key]
    if len(remaining) == len(raws):
        raise ValueError("Ключ не найден в конфигурации")
    if not remaining:
        raise ValueError("Нельзя отключить последний активный ключ")
    result = _apply_raws(remaining, "keys:disable")
    if result.get("ok"):
        db.execute(
            "INSERT INTO key_meta(key,comment,created_at,disabled) VALUES(?,?,?,1) "
            "ON CONFLICT(key) DO UPDATE SET disabled=1",
            (key, _meta(key)["comment"], _meta(key)["created_at"] or db.now_iso()),
        )
    return result


def enable_key(key: str) -> dict:
    key = key.lower()
    env = config_editor.effective_env()
    raws = split_secrets(env.get("TG_SECRET"))
    if any(key_of(r) == key for r in raws):
        db.execute("UPDATE key_meta SET disabled=0 WHERE key=?", (key,))
        return {"ok": True, "message": "Ключ уже активен"}
    result = _apply_raws(raws + [key], "keys:enable")
    if result.get("ok"):
        db.execute("UPDATE key_meta SET disabled=0 WHERE key=?", (key,))
    return result


def delete_key(key: str) -> dict:
    key = key.lower()
    env = config_editor.effective_env()
    raws = split_secrets(env.get("TG_SECRET"))
    remaining = [r for r in raws if key_of(r) != key]
    if len(remaining) != len(raws):
        if not remaining:
            raise ValueError("Нельзя удалить последний активный ключ")
        result = _apply_raws(remaining, "keys:delete")
        if not result.get("ok"):
            return result
    db.execute("DELETE FROM key_meta WHERE key=?", (key,))
    return {"ok": True}


def key_stats(key: str) -> dict:
    return {
        "supported": False,
        "reason": "Прокси не маркирует сессии ключом, поэтому персональная статистика невозможна.",
        "alternatives": [
            "Разделить пользователей по отдельным портам/экземплярам — требует изменения архитектуры.",
            "Сопоставлять по IP клиента вручную (IP не привязан к ключу).",
        ],
    }
