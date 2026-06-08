"""
API tests for /api/benchmarks endpoints.

Tests request validation, response shape, error handling, and lifecycle.
"""
from __future__ import annotations

import pytest


class TestCreateBenchmark:
    def test_valid_payload_returns_202(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        })
        assert resp.status_code == 202

    def test_response_has_id_and_pending_status(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        })
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert data["workload_type"] == "image_processing"

    def test_invalid_workload_type_returns_400(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "nonexistent_workload",
            "input_size": 100,
            "worker_count": 2,
            "iterations": 1,
        })
        assert resp.status_code == 400

    def test_missing_required_field_returns_422(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            # missing input_size and worker_count
        })
        assert resp.status_code == 422

    def test_worker_count_zero_returns_422(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 100,
            "worker_count": 0,  # invalid: ge=1
            "iterations": 1,
        })
        assert resp.status_code == 422

    def test_worker_count_exceeds_maximum_returns_422(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 100,
            "worker_count": 100,  # invalid: le=32
            "iterations": 1,
        })
        assert resp.status_code == 422

    def test_iterations_exceeds_max_returns_422(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 100,
            "worker_count": 2,
            "iterations": 100,  # invalid: le=10
        })
        assert resp.status_code == 422

    def test_negative_input_size_returns_422(self, client):
        resp = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": -1,
            "worker_count": 2,
            "iterations": 1,
        })
        assert resp.status_code == 422

    def test_all_valid_workload_types_accepted(self, client):
        for wt in ("matrix_multiplication", "parallel_sort", "image_processing", "graph_bfs"):
            resp = client.post("/api/benchmarks", json={
                "workload_type": wt,
                "input_size": 100,
                "worker_count": 1,
                "iterations": 1,
            })
            assert resp.status_code == 202, f"Expected 202 for {wt}, got {resp.status_code}"


class TestListBenchmarks:
    def test_empty_list_returns_200(self, client):
        resp = client.get("/api/benchmarks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_after_create_list_has_items(self, client):
        client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        })
        resp = client.get("/api/benchmarks")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_filter_by_workload_type(self, client):
        client.post("/api/benchmarks", json={
            "workload_type": "image_processing", "input_size": 64, "worker_count": 1, "iterations": 1,
        })
        client.post("/api/benchmarks", json={
            "workload_type": "parallel_sort", "input_size": 1000, "worker_count": 1, "iterations": 1,
        })
        resp = client.get("/api/benchmarks?workload_type=image_processing")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["workload_type"] == "image_processing" for r in data)

    def test_limit_parameter_respected(self, client):
        for _ in range(5):
            client.post("/api/benchmarks", json={
                "workload_type": "image_processing", "input_size": 64, "worker_count": 1, "iterations": 1,
            })
        resp = client.get("/api/benchmarks?limit=3")
        assert len(resp.json()) <= 3


class TestGetBenchmark:
    def test_get_existing_benchmark(self, client):
        created = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        }).json()
        resp = client.get(f"/api/benchmarks/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/benchmarks/does-not-exist-xyz")
        assert resp.status_code == 404

    def test_response_has_all_required_fields(self, client):
        created = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        }).json()
        resp = client.get(f"/api/benchmarks/{created['id']}")
        data = resp.json()
        for field in ("id", "workload_type", "input_size", "worker_count", "status", "created_at"):
            assert field in data


class TestDeleteBenchmark:
    def test_delete_existing(self, client):
        created = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        }).json()
        resp = client.delete(f"/api/benchmarks/{created['id']}")
        assert resp.status_code == 204
        # Verify gone
        assert client.get(f"/api/benchmarks/{created['id']}").status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/benchmarks/ghost-id-xyz")
        assert resp.status_code == 404


class TestBenchmarkStats:
    def test_stats_endpoint_returns_200(self, client):
        resp = client.get("/api/benchmarks/stats")
        assert resp.status_code == 200

    def test_stats_has_required_fields(self, client):
        resp = client.get("/api/benchmarks/stats")
        data = resp.json()
        for field in ("total_runs", "completed_runs", "failed_runs", "best_speedup", "average_efficiency"):
            assert field in data


class TestAnalyzeBenchmark:
    def test_analyze_nonexistent_returns_404(self, client):
        resp = client.post("/api/benchmarks/ghost-id/analyze")
        assert resp.status_code == 404

    def test_analyze_pending_run_returns_422(self, client):
        created = client.post("/api/benchmarks", json={
            "workload_type": "image_processing",
            "input_size": 64,
            "worker_count": 1,
            "iterations": 1,
        }).json()
        resp = client.post(f"/api/benchmarks/{created['id']}/analyze")
        # Pending run cannot be analyzed
        assert resp.status_code in (422, 404)

    def test_analyze_completed_run_returns_analysis(self, client, make_benchmark_run):
        run = make_benchmark_run()
        resp = client.post(f"/api/benchmarks/{run.id}/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data
        assert "bottleneck_type" in data["analysis"]


class TestReportEndpoint:
    def test_report_existing_returns_200(self, client, make_benchmark_run):
        run = make_benchmark_run()
        resp = client.get(f"/api/benchmarks/{run.id}/report")
        assert resp.status_code == 200

    def test_report_has_required_fields(self, client, make_benchmark_run):
        run = make_benchmark_run()
        data = client.get(f"/api/benchmarks/{run.id}/report").json()
        # ReportResponse schema: benchmark_id, workload_type, configuration, metrics, analysis, generated_at
        for field in ("benchmark_id", "workload_type", "configuration", "metrics", "generated_at"):
            assert field in data, f"Missing field: {field}"

    def test_report_nonexistent_returns_404(self, client):
        resp = client.get("/api/benchmarks/ghost-report-xyz/report")
        assert resp.status_code == 404

    def test_report_configuration_matches_run(self, client, make_benchmark_run):
        run = make_benchmark_run()
        data = client.get(f"/api/benchmarks/{run.id}/report").json()
        assert data["configuration"]["worker_count"] == run.worker_count
        assert data["configuration"]["workload_type"] == run.workload_type

    def test_report_metrics_has_status(self, client, make_benchmark_run):
        run = make_benchmark_run()
        data = client.get(f"/api/benchmarks/{run.id}/report").json()
        assert "status" in data["metrics"]
        # The run fixture creates a completed run; verify status is surfaced in metrics
        assert data["metrics"]["status"] in ("completed", "pending", "running", "failed")
