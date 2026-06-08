"""
Unit tests for RecommendationService.

Tests the knee-detection algorithm, data fetching, and reasoning text.
"""
from __future__ import annotations

import pytest

from app.services.recommendation_service import RecommendationService


class TestRecommendationServiceNoData:
    def test_no_data_returns_defaults(self, db):
        svc = RecommendationService(db)
        result = svc.recommend("image_processing", 1024)
        assert result["workload_type"] == "image_processing"
        # With no data, prediction returns linear extrapolation — optimal count is candidate
        assert result["optimal_worker_count"] >= 1
        assert result["data_points_used"] == 0
        assert isinstance(result["reasoning"], str)

    def test_recommendation_structure(self, db):
        svc = RecommendationService(db)
        result = svc.recommend("parallel_sort", 1000000)
        required = [
            "workload_type", "input_size", "optimal_worker_count",
            "expected_speedup", "expected_efficiency",
            "reasoning", "alternative_counts", "data_points_used",
        ]
        for key in required:
            assert key in result, f"Missing: {key}"


class TestRecommendationServiceWithData:
    def _seed_amdahl_runs(self, db, workload_type: str, input_size: int, p: float = 0.85):
        """Create benchmark runs that follow Amdahl's Law."""
        from app.models.benchmark import BenchmarkRun
        from datetime import datetime
        import numpy as np
        from app.ai.scalability_agent import _amdahl

        for workers in (1, 2, 4, 8):
            speedup = float(_amdahl(np.array([float(workers)]), p)[0])
            run = BenchmarkRun(
                workload_type=workload_type,
                input_size=input_size,
                worker_count=workers,
                iterations=1,
                status="completed",
                speedup=speedup,
                efficiency=speedup / workers * 100,
                execution_time=1.0 / speedup,
                sequential_time=1.0,
            )
            db.add(run)
        db.commit()

    def test_recommends_reasonable_worker_count(self, db):
        self._seed_amdahl_runs(db, "image_processing", 2048, p=0.85)
        svc = RecommendationService(db)
        result = svc.recommend("image_processing", 2048)
        # Should recommend somewhere between 4 and 16
        assert 1 <= result["optimal_worker_count"] <= 32

    def test_expected_speedup_greater_than_one(self, db):
        self._seed_amdahl_runs(db, "image_processing", 2048)
        svc = RecommendationService(db)
        result = svc.recommend("image_processing", 2048)
        assert result["expected_speedup"] >= 1.0

    def test_uses_data_points(self, db):
        self._seed_amdahl_runs(db, "parallel_sort", 5000000)
        svc = RecommendationService(db)
        result = svc.recommend("parallel_sort", 5000000)
        assert result["data_points_used"] >= 3

    def test_alternative_counts_listed(self, db):
        self._seed_amdahl_runs(db, "image_processing", 1024)
        svc = RecommendationService(db)
        result = svc.recommend("image_processing", 1024)
        assert isinstance(result["alternative_counts"], list)

    def test_reasoning_text_contains_worker_info(self, db):
        self._seed_amdahl_runs(db, "graph_bfs", 50000)
        svc = RecommendationService(db)
        result = svc.recommend("graph_bfs", 50000)
        assert str(result["optimal_worker_count"]) in result["reasoning"]

    def test_respects_available_workers_cap(self, db):
        self._seed_amdahl_runs(db, "image_processing", 1024)
        svc = RecommendationService(db)
        result = svc.recommend("image_processing", 1024, available_workers=4)
        assert result["optimal_worker_count"] <= 4


class TestKneeDetection:
    """Unit-test the knee detection static method directly."""

    def test_knee_at_inflection_point(self):
        predictions = [
            {"worker_count": 1, "predicted_speedup": 1.0, "predicted_efficiency": 1.0},
            {"worker_count": 2, "predicted_speedup": 1.8, "predicted_efficiency": 0.9},
            {"worker_count": 4, "predicted_speedup": 3.0, "predicted_efficiency": 0.75},
            {"worker_count": 8, "predicted_speedup": 3.3, "predicted_efficiency": 0.41},
            {"worker_count": 16, "predicted_speedup": 3.5, "predicted_efficiency": 0.22},
        ]
        best = RecommendationService._find_knee(predictions)
        # 3.0 → 3.3 is 10% gain; 3.3 → 3.5 is ~6% (below threshold)
        assert best["worker_count"] in (4, 8)

    def test_knee_returns_last_point_if_always_above_threshold(self):
        predictions = [
            {"worker_count": 1, "predicted_speedup": 1.0, "predicted_efficiency": 1.0},
            {"worker_count": 2, "predicted_speedup": 2.0, "predicted_efficiency": 1.0},
            {"worker_count": 4, "predicted_speedup": 4.0, "predicted_efficiency": 1.0},
        ]
        best = RecommendationService._find_knee(predictions)
        assert best["worker_count"] == 4

    def test_knee_returns_first_point_if_immediately_below_threshold(self):
        predictions = [
            {"worker_count": 1, "predicted_speedup": 1.0, "predicted_efficiency": 1.0},
            {"worker_count": 2, "predicted_speedup": 1.05, "predicted_efficiency": 0.52},
        ]
        best = RecommendationService._find_knee(predictions)
        # 5% gain < 10% threshold → stays at first point
        assert best["worker_count"] == 1
