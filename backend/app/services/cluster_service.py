"""
ClusterService
──────────────
Manages ClusterNode registration, heartbeats, and health checking.
The local node is auto-registered on startup.
Remote nodes call POST /api/cluster/heartbeat to stay 'online'.
"""

import logging
import platform
import socket
from datetime import datetime, timedelta
from typing import Any

import psutil
from sqlalchemy.orm import Session

from app.models.cluster_node import ClusterNode
from app.schemas.cluster import NodeHeartbeat

logger = logging.getLogger(__name__)

_HEARTBEAT_TIMEOUT_SECONDS = 30


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _get_cpu_model() -> str | None:
    try:
        import subprocess
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


class ClusterService:
    def __init__(self, db: Session):
        self.db = db

    # ── Auto-register local node ──────────────────────────────────────────────

    def auto_register_local(self) -> ClusterNode:
        """
        Called once on startup. Upserts the local node record.
        """
        hostname = socket.gethostname()
        existing = self.db.query(ClusterNode).filter(
            ClusterNode.hostname == hostname
        ).first()

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

        if existing:
            existing.ip_address = _get_local_ip()
            existing.cpu_count = psutil.cpu_count(logical=True) or 1
            existing.cpu_model = _get_cpu_model()
            existing.total_memory_gb = round(mem.total / (1024 ** 3), 2)
            existing.disk_total_gb = round(disk.total / (1024 ** 3), 2)
            existing.os_info = os_info
            existing.is_local = True
            existing.status = "online"
            existing.last_heartbeat = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        node = ClusterNode(
            hostname=hostname,
            ip_address=_get_local_ip(),
            cpu_count=psutil.cpu_count(logical=True) or 1,
            cpu_model=_get_cpu_model(),
            total_memory_gb=round(mem.total / (1024 ** 3), 2),
            disk_total_gb=round(disk.total / (1024 ** 3), 2),
            os_info=os_info,
            is_local=True,
            status="online",
            last_heartbeat=datetime.utcnow(),
        )
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        logger.info("Local node registered: %s (%s)", node.hostname, node.ip_address)
        return node

    # ── Remote heartbeat ──────────────────────────────────────────────────────

    def heartbeat(self, payload: NodeHeartbeat) -> ClusterNode:
        """Register a new remote node or refresh an existing one."""
        existing = self.db.query(ClusterNode).filter(
            ClusterNode.hostname == payload.hostname
        ).first()

        now = datetime.utcnow()

        if existing:
            existing.ip_address = payload.ip_address
            existing.cpu_count = payload.cpu_count
            existing.cpu_model = payload.cpu_model
            existing.total_memory_gb = payload.total_memory_gb
            existing.disk_total_gb = payload.disk_total_gb
            existing.os_info = payload.os_info
            existing.status = "online"
            existing.last_heartbeat = now
            existing.current_cpu_pct = payload.current_cpu_pct
            existing.current_mem_pct = payload.current_mem_pct
            existing.metadata_json = payload.metadata_json
            self.db.commit()
            self.db.refresh(existing)
            return existing

        node = ClusterNode(
            hostname=payload.hostname,
            ip_address=payload.ip_address,
            cpu_count=payload.cpu_count,
            cpu_model=payload.cpu_model,
            total_memory_gb=payload.total_memory_gb,
            disk_total_gb=payload.disk_total_gb or 0.0,
            os_info=payload.os_info,
            is_local=False,
            status="online",
            last_heartbeat=now,
            current_cpu_pct=payload.current_cpu_pct,
            current_mem_pct=payload.current_mem_pct,
            metadata_json=payload.metadata_json,
        )
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node

    # ── Health sweep ──────────────────────────────────────────────────────────

    def mark_stale_nodes_offline(self) -> int:
        """
        Mark nodes whose last heartbeat exceeds HEARTBEAT_TIMEOUT_SECONDS as offline.
        Returns the count of nodes marked offline.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=_HEARTBEAT_TIMEOUT_SECONDS)
        stale = (
            self.db.query(ClusterNode)
            .filter(
                ClusterNode.is_local == False,  # noqa: E712
                ClusterNode.status == "online",
                ClusterNode.last_heartbeat < cutoff,
            )
            .all()
        )
        for node in stale:
            node.status = "offline"
        if stale:
            self.db.commit()
        return len(stale)

    # ── Update local real-time metrics ───────────────────────────────────────

    def refresh_local_metrics(self) -> None:
        """Update current CPU/mem pct for the local node. Called by background task."""
        try:
            hostname = socket.gethostname()
            node = self.db.query(ClusterNode).filter(
                ClusterNode.hostname == hostname
            ).first()
            if node:
                node.current_cpu_pct = psutil.cpu_percent(interval=None)
                node.current_mem_pct = psutil.virtual_memory().percent
                node.last_heartbeat = datetime.utcnow()
                node.status = "online"
                self.db.commit()
        except Exception as exc:
            logger.warning("Failed to refresh local metrics: %s", exc)

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_nodes(self) -> list[ClusterNode]:
        return self.db.query(ClusterNode).order_by(ClusterNode.registered_at.asc()).all()

    def get_summary(self) -> dict[str, Any]:
        nodes = self.list_nodes()
        online = [n for n in nodes if n.status == "online"]
        offline = [n for n in nodes if n.status == "offline"]
        degraded = [n for n in nodes if n.status == "degraded"]

        return {
            "total_nodes": len(nodes),
            "online_nodes": len(online),
            "offline_nodes": len(offline),
            "degraded_nodes": len(degraded),
            "total_cpu_cores": sum(n.cpu_count for n in online),
            "total_memory_gb": round(sum(n.total_memory_gb for n in online), 2),
            "nodes": nodes,
        }

    def get_node(self, node_id: str) -> ClusterNode | None:
        return self.db.query(ClusterNode).filter(ClusterNode.id == node_id).first()

    def delete_node(self, node_id: str) -> bool:
        node = self.get_node(node_id)
        if not node or node.is_local:
            return False
        self.db.delete(node)
        self.db.commit()
        return True
