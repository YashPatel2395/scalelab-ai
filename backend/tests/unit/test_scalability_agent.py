"""
Unit tests for ScalabilityAgent (curve fitting + prediction logic).

Tests verify:
- Amdahl / Gustafson fitting against known data
- R² quality metrics
- Insufficient data handling
- Prediction bounds (speedup > 0, efficiency ≤ 1)
"""
from __future__ import annotations

import math
import pytest

from app.ai.scalability_agent import predict_scalability, _amdahl, _gustafson, _r_squared
import numpy as np


class TestAmdahlFunction:
    def test_single_worker_speedup_is_one(self):
        result = float(_amdahl(np.array([1.0]), 0.9)[0])
        assert abs(result - 1.0) < 0.001

    def test_linear_speedup_at_p_equals_one(self):
        # p=0.9999 ≈ 1: speedup should approach P
        result = float(_amdahl(np.array([4.0]), 0.9999)[0])
        assert result > 3.5

    def test_amdahl_ceiling(self):
        # At p=0.8, ceiling = 1/(1-0.8) = 5
        large_p = float(_amdahl(np.array([1000.0]), 0.8)[0])
        assert abs(large_p - 5.0) < 0.1

    def test_diminishing_returns(self):
        p_frac = 0.8
        s4 = float(_amdahl(np.array([4.0]), p_frac)[0])
        s8 = float(_amdahl(np.array([8.0]), p_frac)[0])
        s16 = float(_amdahl(np.array([16.0]), p_frac)[0])
        # Each doubling of workers gives less and less additional speedup
        assert (s8 - s4) > (s16 - s8)


class TestGustafsonFunction:
    def test_single_worker_is_one(self):
        result = float(_gustafson(np.array([1.0]), 0.2)[0])
        assert abs(result - 1.0) < 0.001

    def test_scales_with_p(self):
        # alpha=0: S = P (ideal linear)
        r4 = float(_gustafson(np.array([4.0]), 0.0)[0])
        assert abs(r4 - 4.0) < 0.001

    def test_serial_overhead_reduces_speedup(self):
        low = float(_gustafson(np.array([8.0]), 0.1)[0])
        high = float(_gustafson(np.array([8.0]), 0.4)[0])
        assert low > high


class TestRSquared:
    def test_perfect_fit_is_one(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        assert abs(_r_squared(y, y) - 1.0) < 1e-10

    def test_mean_prediction_is_zero(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        y_mean = np.full_like(y, np.mean(y))
        assert abs(_r_squared(y, y_mean)) < 1e-10

    def test_worse_prediction_lower_r2(self):
        y = np.array([1.0, 1.9, 2.8, 3.6])
        y_good = np.array([1.0, 2.0, 3.0, 4.0])
        y_bad = np.array([2.0, 1.5, 3.5, 3.0])
        assert _r_squared(y, y_good) > _r_squared(y, y_bad)


class TestPredictScalability:
    """Tests the main predict_scalability function end-to-end."""

    def _amdahl_data(self, p: float = 0.85, workers=(1, 2, 4, 8)):
        """Generate synthetic Amdahl data with no noise."""
        return [
            {"worker_count": w, "speedup": float(_amdahl(np.array([float(w)]), p)[0])}
            for w in workers
        ]

    def test_empty_data_returns_insufficient(self):
        result = predict_scalability([], [1, 2, 4])
        assert result["model_used"] == "insufficient_data"
        assert result["data_points_used"] == 0

    def test_single_data_point_returns_insufficient(self):
        result = predict_scalability([{"worker_count": 4, "speedup": 2.5}], [1, 2, 4])
        assert result["model_used"] == "insufficient_data"
        assert result["data_points_used"] == 1

    def test_two_data_points_returns_insufficient(self):
        data = [{"worker_count": 1, "speedup": 1.0}, {"worker_count": 2, "speedup": 1.8}]
        result = predict_scalability(data, [1, 2, 4])
        assert result["model_used"] == "insufficient_data"

    def test_fits_amdahl_data_with_high_r2(self):
        data = self._amdahl_data(p=0.85)
        result = predict_scalability(data, [1, 2, 4, 8])
        assert result["model_used"] in ("amdahl", "gustafson")
        assert result["r_squared"] is not None
        assert result["r_squared"] > 0.95  # good fit on clean data

    def test_predictions_cover_all_requested_workers(self):
        data = self._amdahl_data(p=0.8)
        targets = [1, 2, 4, 8, 16]
        result = predict_scalability(data, targets)
        predicted_workers = [p["worker_count"] for p in result["predictions"]]
        assert set(predicted_workers) == set(targets)

    def test_speedup_at_1_worker_is_close_to_one(self):
        data = self._amdahl_data(p=0.9)
        result = predict_scalability(data, [1, 2, 4])
        p1 = next(p for p in result["predictions"] if p["worker_count"] == 1)
        assert abs(p1["predicted_speedup"] - 1.0) < 0.1

    def test_speedup_increases_with_workers(self):
        data = self._amdahl_data(p=0.85)
        result = predict_scalability(data, [1, 2, 4, 8])
        speedups = sorted(result["predictions"], key=lambda x: x["worker_count"])
        for i in range(1, len(speedups)):
            assert speedups[i]["predicted_speedup"] >= speedups[i-1]["predicted_speedup"]

    def test_efficiency_bounded_0_to_1(self):
        data = self._amdahl_data(p=0.9)
        result = predict_scalability(data, [1, 2, 4, 8, 16])
        for p in result["predictions"]:
            assert 0.0 <= p["predicted_efficiency"] <= 1.0

    def test_amdahl_theoretical_max_speedup(self):
        # p=0.8, ceiling = 1/(1-0.8) = 5
        data = self._amdahl_data(p=0.8)
        result = predict_scalability(data, [1, 2, 4, 8])
        if result["model_used"] == "amdahl":
            assert result["theoretical_max_speedup"] is not None
            assert abs(result["theoretical_max_speedup"] - 5.0) < 0.5

    def test_deduplication_uses_median(self):
        """Multiple measurements for same worker count → median used."""
        data = [
            {"worker_count": 4, "speedup": 2.0},
            {"worker_count": 4, "speedup": 3.0},
            {"worker_count": 4, "speedup": 2.5},
            {"worker_count": 2, "speedup": 1.8},
            {"worker_count": 1, "speedup": 1.0},
        ]
        # Should not crash and use 3 unique worker counts
        result = predict_scalability(data, [1, 2, 4])
        assert result["data_points_used"] == 3

    def test_recommendation_text_present(self):
        data = self._amdahl_data(p=0.85)
        result = predict_scalability(data, [1, 2, 4])
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 10
