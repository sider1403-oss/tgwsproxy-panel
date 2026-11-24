"""Background collector: reads logs, active sockets and host/container metrics."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from . import alerts, db, devices, dockerctl, logutil, netns, parser, settings

STATE: dict = {
    "proxy": {},
    "active": [],
    "metrics": {
        "active_count": 0,
        "speed_in": 0.0,
        "speed_out": 0.0,
        "cpu_host": 0.0,
        "mem_used": 0,
        "mem_total": 0,
        "cpu_proxy": 0.0,
        "mem_proxy": 0,
        "rx": 0,
        "tx": 0,
    },
    "updated_at": None,
    "logs": {"events": 0, "sessions": 0},
}

_lock = threading.Lock()


def snapshot() -> dict:
    with _lock:
        return {
            "proxy": dict(STATE["proxy"]),
            "active": [dict(c) for c in STATE["active"]],
            "metrics": dict(STATE["metrics"]),
            "updated_at": STATE["updated_at"],
            "logs": dict(STATE["logs"]),
        }


class Collector(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="panel-collector")
        self.stop_event = threading.Event()
        self.ingestor = parser.LogIngestor()
        self.prev_counters: tuple[int, int] | None = None
        self.prev_counters_at: float | None = None
        self.prev_proc: tuple[float, int] | None = None  # (ticks, ts)
        self.prev_host_cpu: tuple[int, int] | None = None
        self.prev_host_cpu_at: float | None = None
        self.speeds = (0.0, 0.0)
        self.started_at: str | None = None
        self.seen: dict[str, str] = {}
        self.last_sample = 0.0
        self.last_version = 0.0
        self.last_prune = 0.0
        self.version: str | None = None
        self._load_seen()

    def _load_seen(self) -> None:
        for row in db.query("SELECT id, first_seen FROM connection_seen"):
            self.seen[row["id"]] = row["first_seen"]

    def run(self) -> None:
        # Initial backlog import (existing docker logs) on first start.
        try:
            self.ingestor.ingest()
        except Exception as exc:  # noqa: BLE001
            self._log(f"initial ingest failed: {exc}")
        try:
            db.prune()
            self.last_prune = time.time()
        except Exception as exc:  # noqa: BLE001
            self._log(f"initial prune failed: {exc}")
        while not self.stop_event.is_set():
            started = time.time()
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                self._log(f"collector error: {exc}")
            elapsed = time.time() - started
            self.stop_event.wait(max(0.2, 2.0 - elapsed))

    def _log(self, msg: str) -> None:
        logutil.append(msg)

    def tick(self) -> None:
        now = time.time()
        st = dockerctl.status()
        pid = st.get("pid") if st.get("running") else None
        try:
            devices.sync_netmon()
        except Exception as exc:  # noqa: BLE001 - device hints are best-effort
            self._log(f"netmon sync failed: {exc}")

        if st.get("started_at") != self.started_at:
            self.started_at = st.get("started_at")
            self.prev_counters = None
            self.prev_proc = None
            self.speeds = (0.0, 0.0)

        nev, ns = self.ingestor.ingest()

        if st.get("running") and now - self.last_version > 600:
            self.version = dockerctl.version()
            self.last_version = now
        version = self.version or db.get_meta("proxy_version")

        active: list[dict] = []
        if pid:
            try:
                conns = netns.active_connections(int(st.get("proxy_port") or settings.PROXY_PORT))
            except Exception as exc:  # noqa: BLE001 - helper outage must not stop collection
                self._log(f"active connections unavailable: {exc}")
                conns = []
            for c in conns:
                cid = f"{c['ip']}:{c['port']}"
                first = self.seen.get(cid)
                if first is None:
                    first = db.now_iso()
                    self.seen[cid] = first
                    db.execute(
                        "INSERT OR REPLACE INTO connection_seen(id, first_seen) VALUES(?,?)", (cid, first)
                    )
                first_dt = db.parse_iso(first)
                c["first_seen"] = first
                c["duration"] = (
                    max(0, int((datetime.now(timezone.utc) - first_dt).total_seconds())) if first_dt else 0
                )
                active.append(c)
            # forget sockets that disappeared
            current_ids = {f"{c['ip']}:{c['port']}" for c in active}
            if len(self.seen) > 2000:
                self.seen = {k: v for k, v in self.seen.items() if k in current_ids}

        rx = tx = 0
        if pid:
            counters = dockerctl.net_counters()
            if counters:
                rx, tx = counters
                if self.prev_counters and self.prev_counters_at:
                    dt = max(0.001, now - self.prev_counters_at)
                    d_in = rx - self.prev_counters[0]
                    d_out = tx - self.prev_counters[1]
                    if d_in >= 0 and d_out >= 0:
                        self.speeds = (d_in / dt, d_out / dt)
                    else:
                        self.speeds = (0.0, 0.0)
                self.prev_counters = (rx, tx)
                self.prev_counters_at = now

        # CPU of this LXC container (cgroup v2), not host-wide /proc/stat.
        cpu_host = STATE["metrics"].get("cpu_host", 0.0)
        usage = dockerctl.lxc_cpu_usec()
        if usage is not None and self.prev_host_cpu is not None and self.prev_host_cpu_at:
            dt = max(0.001, now - self.prev_host_cpu_at)
            d_usage = usage - self.prev_host_cpu  # microseconds
            if d_usage >= 0:
                cpu_host = max(0.0, min(800.0, 100.0 * d_usage / 1_000_000.0 / dt))
        if usage is not None:
            self.prev_host_cpu = usage
            self.prev_host_cpu_at = now

        mem_total, mem_used = dockerctl.host_mem()

        cpu_proxy = STATE["metrics"].get("cpu_proxy", 0.0)
        mem_proxy = STATE["metrics"].get("mem_proxy", 0)
        if pid:
            ps = dockerctl.proc_stat()
            if ps:
                mem_proxy = ps["rss"]
                if self.prev_proc:
                    dt = max(0.001, now - self.prev_proc[1])
                    d_ticks = ps["ticks"] - self.prev_proc[0]
                    cpu_proxy = max(0.0, min(100.0 * 8, 100.0 * d_ticks / ps["hz"] / dt))
                self.prev_proc = (ps["ticks"], now)

        with _lock:
            STATE["proxy"] = {
                "available": st.get("available", True),
                "exists": st.get("exists"),
                "state": st.get("state"),
                "running": st.get("running"),
                "health": st.get("health"),
                "uptime": st.get("uptime"),
                "started_at": st.get("started_at"),
                "restart_policy": st.get("restart_policy"),
                "image": st.get("image"),
                "image_id": st.get("image_id"),
                "pid": st.get("pid"),
                "ports": st.get("ports", []),
                "exit_code": st.get("exit_code"),
                "error": st.get("error"),
                "version": version,
            }
            STATE["active"] = active
            STATE["metrics"] = {
                "active_count": len(active),
                "speed_in": round(self.speeds[0], 1),
                "speed_out": round(self.speeds[1], 1),
                "cpu_host": round(cpu_host, 1),
                "mem_used": mem_used,
                "mem_total": mem_total,
                "cpu_proxy": round(cpu_proxy, 2),
                "mem_proxy": mem_proxy,
                "rx": rx,
                "tx": tx,
            }
            STATE["updated_at"] = db.now_iso()
            STATE["logs"]["events"] += nev
            STATE["logs"]["sessions"] += ns

        try:
            alerts.evaluate(st, None)
        except Exception as exc:  # noqa: BLE001
            self._log(f"alerts evaluate failed: {exc}")

        if now - self.last_sample >= 5:
            self.last_sample = now
            db.execute(
                "INSERT INTO samples(ts,conns,rx,tx,speed_in,speed_out,cpu_host,mem_used,cpu_proxy,mem_proxy) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    db.now_iso(),
                    len(active),
                    rx,
                    tx,
                    round(self.speeds[0], 1),
                    round(self.speeds[1], 1),
                    round(cpu_host, 1),
                    mem_used,
                    round(cpu_proxy, 2),
                    mem_proxy,
                ),
            )

        if now - self.last_prune >= 300:
            self.last_prune = now
            try:
                db.prune()
            except Exception as exc:  # noqa: BLE001
                self._log(f"prune failed: {exc}")

    def stop(self) -> None:
        self.stop_event.set()
