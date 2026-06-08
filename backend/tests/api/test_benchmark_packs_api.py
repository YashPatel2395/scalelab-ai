"""
API tests for /api/benchmark-packs endpoints.

Uses the shared `client` fixture from tests/conftest.py.
"""

from __future__ import annotations

import pytest


class TestListBenchmarkPacks:
    def test_list_packs_returns_all_five(self, client):
        res = client.get("/api/benchmark-packs")
        assert res.status_code == 200
        packs = res.json()
        assert len(packs) == 5
        ids = {p["id"] for p in packs}
        assert ids == {
            "ai_inference",
            "etl_pipeline",
            "log_processing",
            "fraud_detection",
            "recommendation_engine",
        }

    def test_list_packs_returns_200(self, client):
        res = client.get("/api/benchmark-packs")
        assert res.status_code == 200

    def test_pack_has_required_fields(self, client):
        res = client.get("/api/benchmark-packs")
        assert res.status_code == 200
        for pack in res.json():
            assert "id" in pack
            assert "name" in pack
            assert "workload_type" in pack
            assert "stages" in pack
            assert "expected_bottleneck" in pack
            assert "scalability_grade" in pack
            assert "estimated_runtime_s" in pack
            assert len(pack["stages"]) >= 3

    def test_pack_has_optional_enrichment_fields(self, client):
        res = client.get("/api/benchmark-packs")
        for pack in res.json():
            assert "subtitle" in pack
            assert "domain" in pack
            assert "domain_tag" in pack
            assert "tags" in pack
            assert "color" in pack
            assert "size_presets" in pack
            assert "default_input_size" in pack

    def test_estimated_runtime_is_positive(self, client):
        res = client.get("/api/benchmark-packs")
        for pack in res.json():
            assert pack["estimated_runtime_s"] > 0

    def test_size_presets_non_empty(self, client):
        res = client.get("/api/benchmark-packs")
        for pack in res.json():
            assert len(pack["size_presets"]) >= 2


class TestGetSinglePack:
    def test_get_single_pack_ai_inference(self, client):
        res = client.get("/api/benchmark-packs/ai_inference")
        assert res.status_code == 200
        assert res.json()["workload_type"] == "ai_inference"

    def test_get_single_pack_etl_pipeline(self, client):
        res = client.get("/api/benchmark-packs/etl_pipeline")
        assert res.status_code == 200
        assert res.json()["id"] == "etl_pipeline"

    def test_get_single_pack_log_processing(self, client):
        res = client.get("/api/benchmark-packs/log_processing")
        assert res.status_code == 200
        assert res.json()["id"] == "log_processing"

    def test_get_single_pack_fraud_detection(self, client):
        res = client.get("/api/benchmark-packs/fraud_detection")
        assert res.status_code == 200
        assert res.json()["id"] == "fraud_detection"

    def test_get_single_pack_recommendation_engine(self, client):
        res = client.get("/api/benchmark-packs/recommendation_engine")
        assert res.status_code == 200
        assert res.json()["id"] == "recommendation_engine"

    def test_get_nonexistent_pack_returns_404(self, client):
        res = client.get("/api/benchmark-packs/nonexistent")
        assert res.status_code == 404

    def test_get_nonexistent_pack_error_message(self, client):
        res = client.get("/api/benchmark-packs/does_not_exist")
        assert res.status_code == 404
        data = res.json()
        assert "detail" in data

    def test_single_pack_has_all_required_fields(self, client):
        res = client.get("/api/benchmark-packs/fraud_detection")
        pack = res.json()
        for field in ("id", "name", "workload_type", "stages",
                      "expected_bottleneck", "scalability_grade",
                      "estimated_runtime_s"):
            assert field in pack, f"Missing field: {field}"


class TestPackWorkloadRegistryIntegration:
    def test_pack_workload_types_in_registry(self, client):
        from app.workloads import WORKLOAD_REGISTRY
        res = client.get("/api/benchmark-packs")
        assert res.status_code == 200
        for pack in res.json():
            assert pack["workload_type"] in WORKLOAD_REGISTRY, (
                f"workload_type '{pack['workload_type']}' not found in WORKLOAD_REGISTRY"
            )

    def test_pack_workload_types_in_metadata(self, client):
        from app.workloads import WORKLOAD_METADATA
        res = client.get("/api/benchmark-packs")
        for pack in res.json():
            assert pack["workload_type"] in WORKLOAD_METADATA, (
                f"workload_type '{pack['workload_type']}' not found in WORKLOAD_METADATA"
            )
