"""
Unit tests for ClusterService.

Tests node registration, heartbeat upsert, stale detection, and metrics.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from app.services.cluster_service import ClusterService
from app.schemas.cluster import NodeHeartbeat
from app.models.cluster_node import ClusterNode


class TestClusterAutoRegister:
    def test_auto_register_creates_local_node(self, db):
        svc = ClusterService(db)
        node = svc.auto_register_local()
        assert node.is_local is True
        assert node.status == "online"
        assert node.hostname is not None
        assert node.cpu_count >= 1
        assert node.total_memory_gb > 0

    def test_auto_register_is_idempotent(self, db):
        svc = ClusterService(db)
        node1 = svc.auto_register_local()
        node2 = svc.auto_register_local()
        assert node1.id == node2.id
        nodes = db.query(ClusterNode).filter(ClusterNode.is_local == True).all()
        assert len(nodes) == 1


class TestClusterHeartbeat:
    def _payload(self, hostname="worker-01", ip="10.0.0.1"):
        return NodeHeartbeat(
            hostname=hostname,
            ip_address=ip,
            cpu_count=8,
            total_memory_gb=32.0,
            current_cpu_pct=45.0,
            current_mem_pct=60.0,
        )

    def test_heartbeat_registers_new_node(self, db):
        svc = ClusterService(db)
        node = svc.heartbeat(self._payload())
        assert node.hostname == "worker-01"
        assert node.status == "online"
        assert node.is_local is False
        assert node.current_cpu_pct == 45.0

    def test_heartbeat_upserts_existing_node(self, db):
        svc = ClusterService(db)
        svc.heartbeat(self._payload(hostname="w1"))
        updated = svc.heartbeat(NodeHeartbeat(
            hostname="w1",
            ip_address="10.0.0.2",   # changed IP
            cpu_count=8,
            total_memory_gb=32.0,
            current_cpu_pct=90.0,
        ))
        assert updated.ip_address == "10.0.0.2"
        assert updated.current_cpu_pct == 90.0
        # Should not create duplicate
        nodes = db.query(ClusterNode).filter(ClusterNode.hostname == "w1").all()
        assert len(nodes) == 1

    def test_heartbeat_resets_status_to_online(self, db):
        svc = ClusterService(db)
        node = svc.heartbeat(self._payload(hostname="w2"))
        # Manually mark offline
        node.status = "offline"
        db.commit()
        # Heartbeat should restore to online
        refreshed = svc.heartbeat(self._payload(hostname="w2"))
        assert refreshed.status == "online"


class TestClusterStaleDetection:
    def test_marks_stale_nodes_offline(self, db):
        svc = ClusterService(db)
        # Create a node with an old heartbeat
        old_time = datetime.utcnow() - timedelta(seconds=60)
        node = ClusterNode(
            hostname="stale-node",
            ip_address="10.0.0.99",
            cpu_count=4,
            total_memory_gb=8.0,
            is_local=False,
            status="online",
            last_heartbeat=old_time,
        )
        db.add(node)
        db.commit()

        count = svc.mark_stale_nodes_offline()
        assert count >= 1
        db.refresh(node)
        assert node.status == "offline"

    def test_does_not_mark_fresh_nodes_offline(self, db):
        svc = ClusterService(db)
        # Fresh heartbeat
        node = ClusterNode(
            hostname="fresh-node",
            ip_address="10.0.0.1",
            cpu_count=4,
            total_memory_gb=8.0,
            is_local=False,
            status="online",
            last_heartbeat=datetime.utcnow(),
        )
        db.add(node)
        db.commit()

        svc.mark_stale_nodes_offline()
        db.refresh(node)
        assert node.status == "online"

    def test_local_node_never_marked_offline(self, db):
        svc = ClusterService(db)
        old_time = datetime.utcnow() - timedelta(seconds=120)
        node = ClusterNode(
            hostname="local-node",
            ip_address="127.0.0.1",
            cpu_count=8,
            total_memory_gb=16.0,
            is_local=True,
            status="online",
            last_heartbeat=old_time,
        )
        db.add(node)
        db.commit()

        svc.mark_stale_nodes_offline()
        db.refresh(node)
        assert node.status == "online"  # is_local=True → exempt


class TestClusterSummary:
    def test_summary_empty(self, db):
        svc = ClusterService(db)
        summary = svc.get_summary()
        assert summary["total_nodes"] == 0
        assert summary["online_nodes"] == 0
        assert summary["total_cpu_cores"] == 0

    def test_summary_counts_correctly(self, db):
        svc = ClusterService(db)
        for i in range(3):
            svc.heartbeat(NodeHeartbeat(
                hostname=f"node-{i}",
                ip_address=f"10.0.0.{i}",
                cpu_count=4,
                total_memory_gb=8.0,
            ))
        # Mark one offline
        node = db.query(ClusterNode).filter(ClusterNode.hostname == "node-2").first()
        node.status = "offline"
        db.commit()

        summary = svc.get_summary()
        assert summary["online_nodes"] == 2
        assert summary["offline_nodes"] == 1
        assert summary["total_cpu_cores"] == 8  # 2 online × 4 cores


class TestClusterDelete:
    def test_delete_remote_node(self, db):
        svc = ClusterService(db)
        node = svc.heartbeat(NodeHeartbeat(
            hostname="removable",
            ip_address="10.0.0.10",
            cpu_count=4,
            total_memory_gb=8.0,
        ))
        assert svc.delete_node(node.id) is True
        assert svc.get_node(node.id) is None

    def test_cannot_delete_local_node(self, db):
        svc = ClusterService(db)
        local = svc.auto_register_local()
        assert svc.delete_node(local.id) is False
        assert svc.get_node(local.id) is not None
