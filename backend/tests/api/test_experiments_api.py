"""
API tests for /api/experiments endpoints.
"""
from __future__ import annotations

import pytest


class TestCreateExperiment:
    def test_create_returns_201(self, client):
        resp = client.post("/api/experiments", json={"name": "Test Exp"})
        assert resp.status_code == 201

    def test_create_with_all_fields(self, client):
        resp = client.post("/api/experiments", json={
            "name": "Full Exp",
            "description": "A description",
            "workload_type": "image_processing",
            "tags": ["perf", "v2"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Full Exp"
        assert "perf" in data["tags"]

    def test_missing_name_returns_422(self, client):
        resp = client.post("/api/experiments", json={"description": "no name"})
        assert resp.status_code == 422

    def test_empty_name_returns_422(self, client):
        resp = client.post("/api/experiments", json={"name": ""})
        assert resp.status_code == 422

    def test_response_has_run_ids_list(self, client):
        resp = client.post("/api/experiments", json={"name": "empty"})
        data = resp.json()
        assert data["run_ids"] == []


class TestListExperiments:
    def test_list_empty(self, client):
        resp = client.get("/api/experiments")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client):
        client.post("/api/experiments", json={"name": "E1"})
        client.post("/api/experiments", json={"name": "E2"})
        resp = client.get("/api/experiments")
        assert len(resp.json()) >= 2


class TestGetExperiment:
    def test_get_existing(self, client):
        created = client.post("/api/experiments", json={"name": "X"}).json()
        resp = client.get(f"/api/experiments/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/experiments/ghost-exp-id")
        assert resp.status_code == 404


class TestUpdateExperiment:
    def test_update_name(self, client):
        created = client.post("/api/experiments", json={"name": "Old"}).json()
        resp = client.patch(f"/api/experiments/{created['id']}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_update_nonexistent_returns_404(self, client):
        resp = client.patch("/api/experiments/ghost", json={"name": "x"})
        assert resp.status_code == 404


class TestAddRunsToExperiment:
    def test_add_valid_run(self, client, make_benchmark_run):
        created = client.post("/api/experiments", json={"name": "E"}).json()
        run = make_benchmark_run()
        resp = client.post(f"/api/experiments/{created['id']}/runs", json={"run_ids": [run.id]})
        assert resp.status_code == 200
        assert run.id in resp.json()["run_ids"]

    def test_add_nonexistent_run_returns_404(self, client):
        created = client.post("/api/experiments", json={"name": "E"}).json()
        resp = client.post(f"/api/experiments/{created['id']}/runs", json={"run_ids": ["ghost-run"]})
        assert resp.status_code == 404

    def test_add_to_nonexistent_experiment_returns_404(self, client, make_benchmark_run):
        run = make_benchmark_run()
        resp = client.post("/api/experiments/ghost/runs", json={"run_ids": [run.id]})
        assert resp.status_code == 404

    def test_empty_run_ids_returns_422(self, client):
        created = client.post("/api/experiments", json={"name": "E"}).json()
        resp = client.post(f"/api/experiments/{created['id']}/runs", json={"run_ids": []})
        assert resp.status_code == 422


class TestCompareExperiment:
    def test_compare_empty_returns_empty_runs(self, client):
        created = client.post("/api/experiments", json={"name": "Empty"}).json()
        resp = client.get(f"/api/experiments/{created['id']}/compare")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []

    def test_compare_with_runs(self, client, make_benchmark_run):
        created = client.post("/api/experiments", json={"name": "With Runs"}).json()
        run1 = make_benchmark_run(speedup=2.0)
        run2 = make_benchmark_run(speedup=3.0)
        client.post(f"/api/experiments/{created['id']}/runs", json={"run_ids": [run1.id, run2.id]})
        resp = client.get(f"/api/experiments/{created['id']}/compare")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 2
        assert data["summary"]["best_speedup"] == 3.0

    def test_compare_nonexistent_returns_404(self, client):
        resp = client.get("/api/experiments/ghost/compare")
        assert resp.status_code == 404


class TestDeleteExperiment:
    def test_delete_existing(self, client):
        created = client.post("/api/experiments", json={"name": "To Delete"}).json()
        resp = client.delete(f"/api/experiments/{created['id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/experiments/{created['id']}").status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/experiments/ghost")
        assert resp.status_code == 404
