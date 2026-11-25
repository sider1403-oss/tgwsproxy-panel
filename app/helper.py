"""Privileged helper: small, explicit allowlist over a Unix socket.

Run only by tgws-panel-helper.service as root. The panel (uid tgws-panel) is the
only accepted peer. There is deliberately no generic command execution.
"""
from __future__ import annotations

import base64
import grp
import json
import os
import pwd
import re
import signal
import socket
import struct
import sys
import threading
import traceback
from datetime import datetime, timezone

from . import config_ops, config_schema, docker_core, log_ops, net_ops, settings

MAX_REQUEST = settings.HELPER_MAX_REQUEST
MAX_CONNECTIONS = 8

_stop = threading.Event()
_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
BACKUP_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[A-Za-z0-9_.-]{1,40}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(msg: str) -> None:
    print(f"{_now()} {msg}", flush=True)


def _int(value, name: str, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: ожидается целое число")
    if not lo <= n <= hi:
        raise ValueError(f"{name}: вне диапазона {lo}..{hi}")
    return n


def _str(value, name: str, maxlen: int = 4096) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name}: ожидается строка")
    if len(value) > maxlen:
        raise ValueError(f"{name}: слишком длинное значение")
    return value


def _require_keys(params: dict, allowed: set[str]) -> None:
    extra = set(params) - allowed
    if extra:
        raise ValueError("Недопустимые параметры: " + ", ".join(sorted(extra)))


def _panel_uid() -> int:
    try:
        return pwd.getpwnam("tgws-panel").pw_uid
    except KeyError:
        raise RuntimeError("пользователь tgws-panel не создан")


def _panel_gid() -> int:
    try:
        return grp.getgrnam("tgws-panel").gr_gid
    except KeyError:
        raise RuntimeError("группа tgws-panel не создана")


def _peer(conn: socket.socket) -> tuple[int, int, int]:
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", raw)


def _peer_allowed(pid: int, uid: int) -> bool:
    if uid != _panel_uid():
        return False
    if not settings.HELPER_REQUIRE_CGROUP:
        return True
    try:
        with open(f"/proc/{pid}/cgroup", "r", encoding="utf-8") as fh:
            cgroup = fh.read()
    except OSError:
        return False
    return "tgws-panel.service" in cgroup


def dispatch(op: str, params: dict) -> dict:
    if not isinstance(params, dict):
        raise ValueError("params должен быть объектом")

    if op == "ping":
        _require_keys(params, set())
        return {"ok": True, "ts": _now()}

    if op == "docker.status":
        _require_keys(params, set())
        return docker_core.status()

    if op == "docker.logs":
        _require_keys(params, {"lines", "since"})
        lines = _int(params.get("lines", 100), "lines", 1, 2000)
        since = params.get("since")
        if since is not None:
            since = _str(since, "since", 40)
            if since and not ISO_RE.fullmatch(since):
                raise ValueError("since: ожидается ISO-8601 UTC")
        return docker_core.logs(lines, since or None)

    if op == "docker.service":
        _require_keys(params, {"action"})
        action = _str(params.get("action"), "action", 16)
        if action not in ("start", "stop", "restart"):
            raise ValueError("action: допустимо start/stop/restart")
        return docker_core.service(action)

    if op == "docker.version":
        _require_keys(params, {"refresh"})
        return {"version": docker_core.version(bool(params.get("refresh", False)))}

    if op == "net.connections":
        _require_keys(params, set())
        st = docker_core.status()
        port = int(st.get("proxy_port") or settings.PROXY_PORT)
        return {"items": net_ops.active_connections(port), "updated_at": _now()}

    if op == "net.counters":
        _require_keys(params, set())
        return net_ops.net_counters()

    if op == "net.kill":
        _require_keys(params, {"ip", "port"})
        ip = _str(params.get("ip"), "ip", 64)
        port = _int(params.get("port"), "port", 1, 65535)
        ok, message = net_ops.kill_connection(ip, port)
        return {"ok": ok, "message": message}

    if op == "container.proc":
        _require_keys(params, set())
        pid = docker_core.container_pid()
        return docker_core.proc_stat(pid) if pid else None

    if op == "config.env":
        _require_keys(params, set())
        env = config_ops.effective_env()
        try:
            keys = sorted(config_ops.env_file_values().keys())
        except OSError:
            keys = []
        return {"env": env, "env_file_keys": keys}

    if op == "config.validate":
        _require_keys(params, set())
        return config_ops.validate_compose()

    if op == "config.apply":
        _require_keys(params, {"environment", "dc_targets", "secret", "tag"})
        environment = params.get("environment") or {}
        if not isinstance(environment, dict) or len(environment) > 64:
            raise ValueError("environment: ожидается объект (<=64 ключей)")
        clean: dict[str, str] = {}
        for k, v in environment.items():
            if k not in config_schema.ENV_SCHEMA:
                raise ValueError(f"Параметр {k} не разрешён")
            clean[str(k)] = _str(v, str(k), 4096)
        dc_targets = params.get("dc_targets")
        if dc_targets is not None:
            if not isinstance(dc_targets, list) or len(dc_targets) > 16:
                raise ValueError("dc_targets: ожидается массив (<=16)")
            if any(not isinstance(t, dict) for t in dc_targets):
                raise ValueError("dc_targets: элементы должны быть объектами")
        secret = params.get("secret")
        if secret is not None:
            secret = config_schema.validate_secret(_str(secret, "secret", 4096))
        tag = _str(params.get("tag") or "config", "tag", 40)
        if not config_schema.TAG_RE.fullmatch(tag):
            raise ValueError("tag: недопустимые символы")
        return config_ops.apply(env_updates=clean, dc_targets=dc_targets, secret_value=secret, tag=tag)

    if op == "config.restore":
        _require_keys(params, {"name"})
        name = _str(params.get("name"), "name", 80)
        if not BACKUP_RE.fullmatch(name):
            raise ValueError("Некорректное имя резервной копии")
        return config_ops.restore_backup(name)

    if op == "backup.list":
        _require_keys(params, set())
        return {"items": config_ops.list_backups()}

    if op == "backup.read":
        _require_keys(params, {"name"})
        name = _str(params.get("name"), "name", 80)
        if not BACKUP_RE.fullmatch(name):
            raise ValueError("Некорректное имя резервной копии")
        data = config_ops.read_backup(name)
        if len(data) > settings.HELPER_BACKUP_MAX_BYTES:
            raise ValueError("Резервная копия слишком большая")
        return {"name": name, "data": base64.b64encode(data).decode("ascii")}

    if op == "storage.stats":
        _require_keys(params, set())
        backups = config_ops.list_backups()
        return {
            "docker_log": log_ops.docker_log_stats(),
            "backups": {"count": len(backups), "bytes": sum(int(b.get("size") or 0) for b in backups)},
        }

    if op == "logs.list":
        _require_keys(params, set())
        return log_ops.list_files()

    if op == "logs.read":
        _require_keys(params, {"inode", "offset", "max_bytes"})
        inode = _str(params.get("inode"), "inode", 32)
        offset = _int(params.get("offset"), "offset", 0, 2**40)
        max_bytes = _int(params.get("max_bytes", 1024 * 1024), "max_bytes", 1, 1024 * 1024)
        return log_ops.read_chunk(inode, offset, max_bytes)

    raise ValueError("Неизвестная операция")


def _send(conn: socket.socket, data: bytes) -> None:
    try:
        conn.sendall(data)
    except OSError:
        pass


def handle(conn: socket.socket) -> None:
    pid = uid = gid = -1
    try:
        pid, uid, gid = _peer(conn)
        if not _peer_allowed(pid, uid):
            _log(f"reject peer pid={pid} uid={uid} gid={gid}")
            _send(conn, b'{"ok":false,"error":"forbidden peer","code":"peer"}\n')
            return
        conn.settimeout(300)
        buf = bytearray()
        while b"\n" not in buf and len(buf) <= MAX_REQUEST:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
        if len(buf) > MAX_REQUEST:
            _send(conn, b'{"ok":false,"error":"request too large","code":"request"}\n')
            return
        line = bytes(buf).split(b"\n", 1)[0]
        if not line:
            return
        try:
            req = json.loads(line.decode("utf-8"))
        except ValueError:
            _send(conn, b'{"ok":false,"error":"invalid json","code":"request"}\n')
            return
        op = req.get("op")
        params = req.get("params") or {}
        if not isinstance(op, str):
            raise ValueError("op: ожидается строка")
        started = datetime.now(timezone.utc)
        result = dispatch(op, params)
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        _log(f"op={op} uid={uid} pid={pid} ms={elapsed} ok=1")
        response = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode("utf-8") + b"\n"
        _send(conn, response)
    except config_schema.ConfigError as exc:
        _log(f"op failed uid={uid} pid={pid}: {exc}")
        _send(conn, json.dumps({"ok": False, "error": str(exc), "code": "validation"}, ensure_ascii=False).encode() + b"\n")
    except ValueError as exc:
        _log(f"op rejected uid={uid} pid={pid}: {exc}")
        _send(conn, json.dumps({"ok": False, "error": str(exc), "code": "validation"}, ensure_ascii=False).encode() + b"\n")
    except net_ops.NetnsError as exc:
        _log(f"op netns failed uid={uid} pid={pid}: {exc}")
        _send(conn, json.dumps({"ok": False, "error": str(exc), "code": "netns"}, ensure_ascii=False).encode() + b"\n")
    except (BrokenPipeError, ConnectionResetError):
        return
    except Exception as exc:  # noqa: BLE001 - never leak a traceback to the panel
        _log(f"op error uid={uid} pid={pid}: {exc}\n{traceback.format_exc()}")
        _send(conn, json.dumps({"ok": False, "error": "внутренняя ошибка helper", "code": "internal"}, ensure_ascii=False).encode() + b"\n")
    finally:
        try:
            conn.close()
        except OSError:
            pass


def serve() -> None:
    path = settings.HELPER_SOCKET
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o660)
    try:
        os.chown(path, 0, _panel_gid())
    except OSError:
        pass
    sock.listen(16)
    sock.settimeout(1.0)
    _log(f"helper listening on {path}")
    while not _stop.is_set():
        try:
            conn, _addr = sock.accept()
        except socket.timeout:
            continue
        except OSError:
            if _stop.is_set():
                break
            continue
        if not _slots.acquire(blocking=False):
            try:
                _send(conn, b'{"ok":false,"error":"too many connections","code":"busy"}\n')
                conn.close()
            except OSError:
                pass
            continue
        threading.Thread(target=_worker, args=(conn,), daemon=True).start()


def _worker(conn: socket.socket) -> None:
    try:
        handle(conn)
    finally:
        _slots.release()


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    try:
        serve()
    finally:
        try:
            settings.HELPER_SOCKET.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
