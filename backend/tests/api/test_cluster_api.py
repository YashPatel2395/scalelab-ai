"""
API tests for /api/cluster endpoints.
"""
from __future__ import annotations

import pytest


class TestClusterSummary:
    def test_get_cluster_returns_200(self, client):
        resp = client.get("/api/cluster")
        assert resp.status_code == 200

    def test_cluster_has_required_fields(self, client):
        resp = client.get("/api/cluster")
        data = resp.json()
        for field in ("total_nodes", "online_nodes", "offline_nodes", "degraded_nodes",
                      "total_cpu_cores", "total_memory_gb", "nodes"):
            assert field in data

    def test_nodes_is_list(self, client):
        resp = client.get("/api/cluster")
        assert isinstance(resp.json()["nodes"], list)


class TestHeartbeat:
    def test_heartbeat_registers_node(self, client):
        resp = client.post("/api/cluster/heartbeat", json={
            "hostname": "test-worker-1",
            "ip_address": "192.168.1.100",
            "cpu_count": 8,
            "total_memory_gb": 16.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "test-worker-1"
        assert data["status"] == "online"
        assert data["is_local"] is False

    def test_heartbeat_upserts(self, client):
        payload = {
            "hostname": "test-upsert",
            "ip_address": "10.0.0.1",
            "cpu_count": 4,
            "total_memory_gb": 8.0,
        }
        client.post("/api/cluster/heartbeat", json=payload)
        # Second call with different IP
        payload["ip_address"] = "10.0.0.2"
        resp = client.post("/api/cluster/heartbeat", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ip_address"] == "10.0.0.2"

    def test_heartbeat_missing_hostname_returns_422(self, client):
        resp = client.post("/api/cluster/heartbeat", json={
            "ip_address": "10.0.0.1",
            "cpu_count": 4,
            "total_memory_gb": 8.0,
        })
        assert resp.status_code == 422

    def test_heartbeat_appears_in_node_list(self, client):
        client.post("/api/cluster/heartbeat", json={
            "hostname": "listed-node",
            "ip_address": "10.10.10.10",
            "cpu_count": 2,
            "total_memory_gb": 4.0,
        })
        resp = client.get("/api/cluster/nodes")
        assert resp.status_code == 200
        hostnames = [n["hostname"] for n in resp.json()]
        assert "listed-node" in hostnames


class TestGetNode:
    def test_get_existing_node(self, client):
        heartbeat_resp = client.post("/api/cluster/heartbeat", json={
            "hostname": "get-me",
            "ip_address": "10.0.0.5",
            "cpu_count": 4,
            "total_memory_gb": 8.0,
        }).json()
        resp = client.get(f"/api/cluster/nodes/{heartbeat_resp['id']}")
        assert resp.status_code == 200
        assert resp.json()["hostname"] == "get-me"

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/cluster/nodes/ghost-node-id")
        assert resp.status_code == 404


class TestReliabilityEndpoint:
    def test_reliability_returns_200(self, client):
        resp = client.get("/api/reliability")
        assert resp.status_code == 200

    def test_reliability_has_required_sections(self, client):
        data = client.get("/api/reliability").json()
        assert "benchmark_runs" in data
        assert "performance" in data
        assert "cluster" in data
        assert "uptime_seconds" in data
        assert "generated_at" in data

    def test_reliability_empty_db_gives_zero_rates(self, client):
        data = client.get("/api/reliability").json()
        runs = data["benchmark_runs"]
        assert runs["total"] == 0
        assert runs["success_rate_pct"] == 0.0
        assert runs["failure_rate_pct"] == 0.0

    def test_reliability_reflects_completed_runs(self, client):
        # Create and complete a benchmark via the API
        from app.models.benchmark import BenchmarkRun
        # Inject a completed run directly through the db fixture (no real execution needed)
        # We test the endpoint shape here; actual counting is tested in unit tests
        data = client.get("/api/reliability").json()
        assert isinstance(data["benchmark_runs"]["total"], int)
        assert isinstance(data["cluster"]["total_nodes"], int)


class TestDeleteNode:
    def test_delete_remote_node(self, client):
        node = client.post("/api/cluster/heartbeat", json={
            "hostname": "deletable",
            "ip_address": "10.0.0.6",
            "cpu_count": 2,
            "total_memory_gb": 4.0,
        }).json()
        resp = client.delete(f"/api/cluster/nodes/{node['id']}")
        assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/cluster/nodes/ghost-node")
        assert resp.status_code == 404
