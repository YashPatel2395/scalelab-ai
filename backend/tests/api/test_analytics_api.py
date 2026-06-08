"""
API tests for /api/analytics endpoints.
"""
from __future__ import annotations

import pytest


class TestPredictEndpoint:
    def test_predict_returns_200(self, client):
        resp = client.post("/api/analytics/predict", json={
            "workload_type": "image_processing",
            "input_size": 2048,
            "target_worker_counts": [1, 2, 4],
        })
        assert resp.status_code == 200

    def test_predict_response_structure(self, client):
        resp = client.post("/api/analytics/predict", json={
            "workload_type": "image_processing",
            "input_size": 2048,
        })
        data = resp.json()
        for field in ("workload_type", "input_size", "model_used",
                      "data_points_used", "predictions", "recommendation"):
            assert field in data

    def test_predict_with_no_data_returns_insufficient(self, client):
        resp = client.post("/api/analytics/predict", json={
            "workload_type": "image_processing",
            "input_size": 99999,  # no data for this size
        })
        assert resp.status_code == 200
        assert resp.json()["model_used"] == "insufficient_data"

    def test_predict_with_seeded_data(self, client, db, make_benchmark_run):
        """Seed multiple runs then call predict — should fit a model."""
        for workers, speedup in [(1, 1.0), (2, 1.8), (4, 2.9), (8, 3.7)]:
            make_benchmark_run(
                workload_type="image_processing",
                input_size=4096,
                worker_count=workers,
                speedup=speedup,
            )
        resp = client.post("/api/analytics/predict", json={
            "workload_type": "image_processing",
            "input_size": 4096,
            "target_worker_counts": [1, 2, 4, 8, 16],
        })
        data = resp.json()
        assert data["model_used"] in ("amdahl", "gustafson")
        assert data["r_squared"] is not None
        assert data["r_squared"] > 0.5


class TestRecommendEndpoint:
    def test_recommend_returns_200(self, client):
        resp = client.post("/api/analytics/recommend", json={
            "workload_type": "image_processing",
            "input_size": 1024,
        })
        assert resp.status_code == 200

    def test_recommend_response_structure(self, client):
        resp = client.post("/api/analytics/recommend", json={
            "workload_type": "image_processing",
            "input_size": 1024,
        })
        data = resp.json()
        for field in ("workload_type", "input_size", "optimal_worker_count",
                      "expected_speedup", "reasoning"):
            assert field in data

    def test_recommend_respects_available_workers(self, client):
        resp = client.post("/api/analytics/recommend", json={
            "workload_type": "image_processing",
            "input_size": 1024,
            "available_workers": 4,
        })
        assert resp.json()["optimal_worker_count"] <= 4


class TestBottleneckEndpoint:
    def test_bottleneck_nonexistent_returns_404(self, client):
        resp = client.get("/api/analytics/bottleneck/ghost-id")
        assert resp.status_code == 404

    def test_bottleneck_pending_run_returns_422(self, client, db, make_benchmark_run):
        run = make_benchmark_run(status="pending")
        resp = client.get(f"/api/analytics/bottleneck/{run.id}")
        assert resp.status_code == 422

    def test_bottleneck_completed_run_returns_report(self, client, make_benchmark_run):
        run = make_benchmark_run()
        resp = client.get(f"/api/analytics/bottleneck/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["benchmark_id"] == run.id
        assert "bottleneck_type" in data
        assert "severity" in data
        assert "root_cause" in data
        assert isinstance(data["recommendations"], list)


class TestMPIEndpoint:
    def test_mpi_returns_200(self, client):
        resp = client.get("/api/analytics/mpi?n_processes=2&matrix_size=64")
        assert resp.status_code == 200

    def test_mpi_response_structure(self, client):
        resp = client.get("/api/analytics/mpi?n_processes=2&matrix_size=64")
        data = resp.json()
        for field in ("n_processes", "matrix_size", "computation_time",
                      "communication_time", "synchronization_time",
                      "total_time", "mpi_available", "breakdown_pct"):
            assert field in data

    def test_mpi_breakdown_sums_to_100(self, client):
        resp = client.get("/api/analytics/mpi?n_processes=2&matrix_size=64")
        pct = resp.json()["breakdown_pct"]
        total = pct["computation"] + pct["communication"] + pct["synchronization"]
        assert abs(total - 100.0) < 1.0

    def test_mpi_invalid_n_processes_returns_422(self, client):
        resp = client.get("/api/analytics/mpi?n_processes=0&matrix_size=128")
        assert resp.status_code == 422

    def test_mpi_invalid_matrix_size_returns_422(self, client):
        resp = client.get("/api/analytics/mpi?n_processes=2&matrix_size=10000")
        assert resp.status_code == 422

    def test_mpi_total_time_positive(self, client):
        resp = client.get("/api/analytics/mpi?n_processes=2&matrix_size=64")
        assert resp.json()["total_time"] > 0
