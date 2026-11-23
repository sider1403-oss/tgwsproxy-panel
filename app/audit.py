"""Audit trail of administrative actions (no secrets stored)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db


def record(
    action: str,
    target: str | None = None,
    ok: bool = True,
    detail: object | None = None,
    ip: str | None = None,
    duration_ms: int | None = None,
) -> None:
    if isinstance(detail, (dict, list)):
        detail_text = json.dumps(detail, ensure_ascii=False)
    elif detail is None:
        detail_text = None
    else:
        detail_text = str(detail)
    if detail_text and len(detail_text) > 8000:
        detail_text = detail_text[:8000] + "…"
    db.execute(
        "INSERT INTO audit(ts,action,target,ok,ip,duration_ms,detail) VALUES(?,?,?,?,?,?,?)",
        (db.now_iso(), action, target, 1 if ok else 0, ip, duration_ms, detail_text),
    )


def list_entries(limit: int = 100, action: str | None = None, ok: bool | None = None) -> dict:
    where = ["1=1"]
    params: list = []
    if action:
        where.append("action LIKE ?")
        params.append(f"%{action}%")
    if ok is not None:
        where.append("ok=?")
        params.append(1 if ok else 0)
    clause = " AND ".join(where)
    total = db.query_one(f"SELECT COUNT(*) AS n FROM audit WHERE {clause}", tuple(params))["n"]
    rows = db.query(
        f"SELECT * FROM audit WHERE {clause} ORDER BY id DESC LIMIT ?",
        tuple(params + [limit]),
    )
    items = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        d["ok"] = bool(d["ok"])
        items.append(d)
    return {"items": items, "total": total}


def prune(days: int = 30) -> None:
    cutoff = db.iso(datetime.now(timezone.utc) - timedelta(days=days))
    db.execute("DELETE FROM audit WHERE ts < ?", (cutoff,))
