"""Privileged configuration operations (helper side only).

This is the former config_editor logic, with Docker access replaced by
docker_core and no database connection. All input must already be validated by
the helper dispatcher; the functions validate again where it matters.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
import threading
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from . import config_schema, docker_core, settings

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)

_apply_lock = threading.Lock()


def read_compose_text() -> str:
    return settings.COMPOSE_FILE.read_text(encoding="utf-8")


def load_compose():
    text = config_schema.load_compose_text(settings.COMPOSE_FILE)
    doc = _yaml.load(text)
    config_schema.services(doc)
    return doc, text


def compose_service() -> dict:
    doc, _ = load_compose()
    return config_schema.services(doc)


def service_env() -> dict:
    return config_schema.service_env(load_compose()[0])


def env_file_values() -> dict:
    out: dict[str, str] = {}
    if not settings.ENV_FILE.exists():
        return out
    for line in settings.ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def effective_env() -> dict:
    info = docker_core.inspect_container()
    if info:
        pairs = info.get("Config", {}).get("Env") or []
        out = {}
        for item in pairs:
            if "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
        if out:
            return out
    env = service_env()
    values = env_file_values()
    for k, v in list(env.items()):
        m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[^}]*)?\}", v or "")
        if m:
            env[k] = values.get(m.group(1), "")
    return env


def backup(tag: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", tag)[:40] or "manual"
    dest = settings.BACKUP_DIR / f"{stamp}-{safe}"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        dest.chmod(0o700)
    except OSError:
        pass
    shutil.copy2(settings.COMPOSE_FILE, dest / "docker-compose.yml")
    try:
        (dest / "docker-compose.yml").chmod(0o600)
    except OSError:
        pass
    if settings.ENV_FILE.exists():
        shutil.copy2(settings.ENV_FILE, dest / ".env")
        try:
            (dest / ".env").chmod(0o600)
        except OSError:
            pass
    meta = {"tag": tag, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "files": sorted(p.name for p in dest.iterdir())}
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        (dest / "meta.json").chmod(0o600)
    except OSError:
        pass
    _prune_backups()
    return dest


def _prune_backups(keep: int | None = None) -> None:
    keep = keep or settings.BACKUPS_KEEP
    try:
        dirs = sorted((d for d in settings.BACKUP_DIR.iterdir() if d.is_dir()), reverse=True)
    except OSError:
        return
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def list_backups() -> list[dict]:
    out = []
    if not settings.BACKUP_DIR.exists():
        return out
    for d in sorted(settings.BACKUP_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta = {}
        mf = d / "meta.json"
        if mf.exists():
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        out.append(
            {
                "name": d.name,
                "created_at": meta.get("created_at"),
                "tag": meta.get("tag"),
                "size": sum(p.stat().st_size for p in d.iterdir() if p.is_file()),
            }
        )
    return out


def backup_dir(name: str) -> Path:
    root = settings.BACKUP_DIR.resolve()
    src = (settings.BACKUP_DIR / str(name)).resolve()
    try:
        src.relative_to(root)
    except ValueError:
        raise config_schema.ConfigError("Некорректное имя резервной копии")
    if not src.is_dir() or not (src / "docker-compose.yml").exists():
        raise config_schema.ConfigError("Резервная копия не найдена")
    return src


def read_backup(name: str) -> bytes:
    src = backup_dir(name)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(src, arcname=src.name)
    return buf.getvalue()


def _write_env_secret(value: str) -> None:
    value = config_schema.validate_secret(value)
    settings.ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if settings.ENV_FILE.exists():
        lines = settings.ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("TG_SECRET="):
            lines[i] = f"TG_SECRET={value}"
            found = True
            break
    if not found:
        lines.append(f"TG_SECRET={value}")
    text = "\n".join(lines).rstrip("\n") + "\n"
    settings.ENV_FILE.write_text(text, encoding="utf-8")
    try:
        settings.ENV_FILE.chmod(0o600)
    except OSError:
        pass


def _restore_backup_files(src: Path) -> None:
    shutil.copy2(src / "docker-compose.yml", settings.COMPOSE_FILE)
    if (src / ".env").exists():
        shutil.copy2(src / ".env", settings.ENV_FILE)
        try:
            settings.ENV_FILE.chmod(0o600)
        except OSError:
            pass


def _wait_ready(timeout: float = 50.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        st = docker_core.status()
        last = st
        health = st.get("health")
        if st.get("running") and health in (None, "healthy"):
            return st
        time.sleep(1.5)
    return last


def validate_compose() -> dict:
    rc, out, err = docker_core.compose(["config", "-q"], timeout=30)
    return {"ok": rc == 0, "error": None if rc == 0 else (err or out).strip()[:2000]}


def apply(
    *,
    env_updates: dict[str, str] | None = None,
    dc_targets: list[dict] | None = None,
    secret_value: str | None = None,
    tag: str = "config",
) -> dict:
    """Validate and apply configuration changes; always keeps a backup."""
    with _apply_lock:
        started = time.time()
        env_updates = env_updates or {}
        clean: dict[str, str] = {}
        for k, v in env_updates.items():
            if k not in config_schema.ENV_SCHEMA:
                raise config_schema.ConfigError(f"Параметр {k} не разрешён к изменению через панель")
            clean[k] = config_schema.validate_value(k, v)
        targets = config_schema.validate_targets(dc_targets) if dc_targets is not None else None
        if secret_value is not None:
            secret_value = config_schema.validate_secret(secret_value)

        doc, _ = load_compose()
        svc = config_schema.services(doc)
        current_env = svc.get("environment") or {}
        env_sets = {k: v for k, v in clean.items() if str(current_env.get(k)) != v}
        current_command = [str(x) for x in (svc.get("command") or [])]
        targets_changed = targets is not None and config_schema.parse_dc_targets(current_command) != targets
        uses_env_file = "${TG_SECRET" in str(service_env().get("TG_SECRET", ""))
        if secret_value is not None:
            if uses_env_file:
                old_secret = (env_file_values().get("TG_SECRET") or "").strip()
            else:
                old_secret = str(current_env.get("TG_SECRET") or "").strip()
            secret_changed = old_secret != secret_value.strip()
        else:
            secret_changed = False

        if not env_sets and not targets_changed and not secret_changed:
            return {
                "ok": True,
                "noop": True,
                "message": "Изменений нет — перезапуск не требуется",
                "duration_ms": int((time.time() - started) * 1000),
                "state": docker_core.status(),
            }

        bak = backup(tag)
        old_compose = read_compose_text()
        old_env = settings.ENV_FILE.read_text(encoding="utf-8") if settings.ENV_FILE.exists() else None
        try:
            if env_sets:
                env = svc.get("environment")
                if env is None:
                    svc["environment"] = env = {}
                for k, v in env_sets.items():
                    env[k] = v
            if targets_changed and targets is not None:
                rebuilt: list = []
                inserted = False
                i = 0
                while i < len(current_command):
                    if current_command[i] == "--dc-ip" and i + 1 < len(current_command):
                        if not inserted:
                            for t in targets:
                                rebuilt.extend(["--dc-ip", DoubleQuotedScalarString(f"{t['dc']}:{t['ip']}")])
                            inserted = True
                        i += 2
                        continue
                    rebuilt.append(current_command[i])
                    i += 1
                if not inserted:
                    for t in targets:
                        rebuilt.extend(["--dc-ip", DoubleQuotedScalarString(f"{t['dc']}:{t['ip']}")])
                svc["command"] = rebuilt
            if secret_changed:
                assert secret_value is not None
                if uses_env_file:
                    _write_env_secret(secret_value)
                else:
                    svc.setdefault("environment", {})["TG_SECRET"] = secret_value

            buf = StringIO()
            _yaml.dump(doc, buf)
            new_text = buf.getvalue()
            if old_compose.startswith("\n") and not new_text.startswith("\n"):
                new_text = "\n" + new_text
            if old_compose.endswith("\n\n") and not new_text.endswith("\n\n"):
                new_text += "\n"
            if new_text != old_compose:
                settings.COMPOSE_FILE.write_text(new_text, encoding="utf-8")

            rc, out, err = docker_core.compose(["config", "-q"], timeout=30)
            if rc != 0:
                raise config_schema.ConfigError("Проверка compose не пройдена: " + (err or out).strip())

            rc, out, err = docker_core.compose(["up", "-d"], timeout=180)
            if rc != 0:
                raise config_schema.ConfigError("docker compose up -d: " + (err or out).strip()[-1500:])

            st = _wait_ready()
            if not st.get("running"):
                raise config_schema.ConfigError("Контейнер не перешёл в состояние running после применения")

            ok, tcp_msg = docker_core.tcp_check(settings.PUBLIC_HOST, int(effective_env().get("TG_PORT", 1443)))
            return {
                "ok": True,
                "backup": bak.name,
                "duration_ms": int((time.time() - started) * 1000),
                "output": (out or "").strip()[-4000:],
                "state": st,
                "port_check": tcp_msg,
                "warnings": [] if ok else [tcp_msg],
            }
        except Exception as exc:  # noqa: BLE001 - roll back on any failure
            try:
                settings.COMPOSE_FILE.write_text(old_compose, encoding="utf-8")
                if old_env is not None:
                    settings.ENV_FILE.write_text(old_env, encoding="utf-8")
            except OSError:
                pass
            rollback_msg = ""
            try:
                docker_core.compose(["up", "-d"], timeout=180)
                st = _wait_ready(30)
                rollback_msg = "Конфигурация восстановлена, контейнер запущен" if st.get("running") else "Откат выполнен, но контейнер не запущен"
            except Exception as exc2:  # noqa: BLE001
                rollback_msg = f"Ошибка откатa: {exc2}"
            return {
                "ok": False,
                "error": str(exc),
                "backup": bak.name,
                "rollback": rollback_msg,
                "duration_ms": int((time.time() - started) * 1000),
            }


def restore_backup(name: str) -> dict:
    with _apply_lock:
        src = backup_dir(name)
        bak = backup("before-restore")
        old_compose = read_compose_text()
        old_env = settings.ENV_FILE.read_text(encoding="utf-8") if settings.ENV_FILE.exists() else None
        try:
            _restore_backup_files(src)
            rc, out, err = docker_core.compose(["config", "-q"], timeout=30)
            if rc != 0:
                raise config_schema.ConfigError("Восстановленная конфигурация некорректна: " + (err or out).strip())
            rc, out, err = docker_core.compose(["up", "-d"], timeout=180)
            if rc != 0:
                raise config_schema.ConfigError("docker compose up -d: " + (err or out).strip())
            st = _wait_ready()
            return {"ok": True, "state": st, "backup_before_restore": bak.name, "output": (out or "").strip()[-2000:]}
        except Exception as exc:  # noqa: BLE001
            settings.COMPOSE_FILE.write_text(old_compose, encoding="utf-8")
            if old_env is not None:
                settings.ENV_FILE.write_text(old_env, encoding="utf-8")
            try:
                docker_core.compose(["up", "-d"], timeout=180)
            except Exception:  # noqa: BLE001
                pass
            return {"ok": False, "error": str(exc), "backup_before_restore": bak.name}
