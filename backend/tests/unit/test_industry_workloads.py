"""
Unit tests for the five industry benchmark workloads.

Each workload is tested with small input sizes so the test suite stays fast.
Three tests per workload:
  - sequential (worker_count=1) — verifies basic correctness and WorkloadResult shape.
  - parallel   (worker_count=2) — verifies parallelism path runs without error.
  - scaling_consistency         — both variants succeed with positive timing values.
"""

from __future__ import annotations

import pytest


# ─── AI Inference ─────────────────────────────────────────────────────────────

class TestAiInferenceWorkload:
    """AI Inference Pipeline — 5 000 documents, 128-dim embeddings."""

    INPUT_SIZE = 5000

    def test_sequential(self):
        from app.workloads.ai_inference import AiInferenceWorkload
        w = AiInferenceWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0
        assert isinstance(result.extra, dict)
        assert result.extra["corpus_size"] == self.INPUT_SIZE
        assert result.extra["embedding_dim"] == 128

    def test_parallel(self):
        from app.workloads.ai_inference import AiInferenceWorkload
        w = AiInferenceWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0

    def test_scaling_consistency(self):
        from app.workloads.ai_inference import AiInferenceWorkload
        w = AiInferenceWorkload()
        r1 = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        r2 = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert r1.execution_time > 0
        assert r2.execution_time > 0
        assert r1.sequential_time > 0
        assert r2.sequential_time > 0

    def test_workload_type_field(self):
        from app.workloads.ai_inference import AiInferenceWorkload
        w = AiInferenceWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.workload_type == "ai_inference"

    def test_extra_has_pipeline_stages(self):
        from app.workloads.ai_inference import AiInferenceWorkload
        w = AiInferenceWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert "pipeline_stages" in result.extra
        assert len(result.extra["pipeline_stages"]) == 4


# ─── ETL Pipeline ─────────────────────────────────────────────────────────────

class TestEtlPipelineWorkload:
    """ETL Data Pipeline — 50 000 records."""

    INPUT_SIZE = 50000

    def test_sequential(self):
        from app.workloads.etl_pipeline import EtlPipelineWorkload
        w = EtlPipelineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0
        assert isinstance(result.extra, dict)
        assert result.extra["records"] == self.INPUT_SIZE

    def test_parallel(self):
        from app.workloads.etl_pipeline import EtlPipelineWorkload
        w = EtlPipelineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0

    def test_scaling_consistency(self):
        from app.workloads.etl_pipeline import EtlPipelineWorkload
        w = EtlPipelineWorkload()
        r1 = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        r2 = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert r1.execution_time > 0
        assert r2.execution_time > 0

    def test_workload_type_field(self):
        from app.workloads.etl_pipeline import EtlPipelineWorkload
        w = EtlPipelineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.workload_type == "etl_pipeline"

    def test_extra_has_group_info(self):
        from app.workloads.etl_pipeline import EtlPipelineWorkload
        w = EtlPipelineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert "distinct_groups_found" in result.extra
        assert result.extra["distinct_groups_found"] > 0
        assert result.extra["group_buckets"] == 480


# ─── Log Processing ───────────────────────────────────────────────────────────

class TestLogProcessingWorkload:
    """Log Processing Pipeline — 50 000 log lines."""

    INPUT_SIZE = 50000

    def test_sequential(self):
        from app.workloads.log_processing import LogProcessingWorkload
        w = LogProcessingWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0
        assert isinstance(result.extra, dict)
        assert result.extra["log_lines"] == self.INPUT_SIZE

    def test_parallel(self):
        from app.workloads.log_processing import LogProcessingWorkload
        w = LogProcessingWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0

    def test_scaling_consistency(self):
        from app.workloads.log_processing import LogProcessingWorkload
        w = LogProcessingWorkload()
        r1 = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        r2 = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert r1.execution_time > 0
        assert r2.execution_time > 0

    def test_workload_type_field(self):
        from app.workloads.log_processing import LogProcessingWorkload
        w = LogProcessingWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.workload_type == "log_processing"

    def test_extra_has_distinct_groups(self):
        from app.workloads.log_processing import LogProcessingWorkload
        w = LogProcessingWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert "distinct_groups" in result.extra
        assert result.extra["distinct_groups"] > 0


# ─── Fraud Detection ──────────────────────────────────────────────────────────

class TestFraudDetectionWorkload:
    """Fraud Detection Pipeline — 10 000 transactions."""

    INPUT_SIZE = 10000

    def test_sequential(self):
        from app.workloads.fraud_detection import FraudDetectionWorkload
        w = FraudDetectionWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0
        assert isinstance(result.extra, dict)
        assert result.extra["transactions"] == self.INPUT_SIZE

    def test_parallel(self):
        from app.workloads.fraud_detection import FraudDetectionWorkload
        w = FraudDetectionWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0

    def test_scaling_consistency(self):
        from app.workloads.fraud_detection import FraudDetectionWorkload
        w = FraudDetectionWorkload()
        r1 = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        r2 = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert r1.execution_time > 0
        assert r2.execution_time > 0

    def test_workload_type_field(self):
        from app.workloads.fraud_detection import FraudDetectionWorkload
        w = FraudDetectionWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.workload_type == "fraud_detection"

    def test_review_queue_populated(self):
        from app.workloads.fraud_detection import FraudDetectionWorkload
        w = FraudDetectionWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.extra["review_queue_size"] > 0
        assert result.extra["highest_risk_score"] > 0.0
        assert result.extra["features"] == 20
        assert result.extra["interaction_terms"] == 10


# ─── Recommendation Engine ────────────────────────────────────────────────────

class TestRecommendationEngineWorkload:
    """Recommendation Engine — 10 000 catalog items."""

    INPUT_SIZE = 10000

    def test_sequential(self):
        from app.workloads.recommendation_engine import RecommendationEngineWorkload
        w = RecommendationEngineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0
        assert isinstance(result.extra, dict)
        assert result.extra["catalog_size"] == self.INPUT_SIZE

    def test_parallel(self):
        from app.workloads.recommendation_engine import RecommendationEngineWorkload
        w = RecommendationEngineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert result.execution_time > 0
        assert result.sequential_time > 0
        assert result.speedup > 0
        assert result.efficiency > 0

    def test_scaling_consistency(self):
        from app.workloads.recommendation_engine import RecommendationEngineWorkload
        w = RecommendationEngineWorkload()
        r1 = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        r2 = w.run(input_size=self.INPUT_SIZE, worker_count=2, iterations=1)
        assert r1.execution_time > 0
        assert r2.execution_time > 0

    def test_workload_type_field(self):
        from app.workloads.recommendation_engine import RecommendationEngineWorkload
        w = RecommendationEngineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.workload_type == "recommendation_engine"

    def test_recommendations_returned(self):
        from app.workloads.recommendation_engine import RecommendationEngineWorkload
        w = RecommendationEngineWorkload()
        result = w.run(input_size=self.INPUT_SIZE, worker_count=1, iterations=1)
        assert result.extra["item_factors"] == 64
        assert result.extra["final_recommendations"] == 20
        assert len(result.extra["top_rec_indices"]) == 5


# ─── Registry integration ─────────────────────────────────────────────────────

class TestWorkloadRegistry:
    """Verify all five new workloads are properly registered."""

    def test_all_five_in_registry(self):
        from app.workloads import WORKLOAD_REGISTRY
        for wt in ("ai_inference", "etl_pipeline", "log_processing",
                   "fraud_detection", "recommendation_engine"):
            assert wt in WORKLOAD_REGISTRY, f"{wt} missing from WORKLOAD_REGISTRY"

    def test_all_five_in_metadata(self):
        from app.workloads import WORKLOAD_METADATA
        for wt in ("ai_inference", "etl_pipeline", "log_processing",
                   "fraud_detection", "recommendation_engine"):
            assert wt in WORKLOAD_METADATA, f"{wt} missing from WORKLOAD_METADATA"

    def test_metadata_has_required_keys(self):
        from app.workloads import WORKLOAD_METADATA
        required = ("name", "description", "input_label", "default_size",
                    "size_presets", "complexity")
        for wt in ("ai_inference", "etl_pipeline", "log_processing",
                   "fraud_detection", "recommendation_engine"):
            meta = WORKLOAD_METADATA[wt]
            for key in required:
                assert key in meta, f"{wt} metadata missing key '{key}'"
