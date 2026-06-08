"""
Mathematical verification tests for scalability calculations.

These tests verify that:
1. Amdahl's Law is implemented correctly
2. Gustafson's Law is implemented correctly
3. Speedup/efficiency derivations are mathematically correct
4. WorkloadResult.compute_derived() produces accurate values
5. Edge cases do not produce NaN or infinite values
"""
from __future__ import annotations

import math
import pytest
import numpy as np

from app.workloads.base import WorkloadResult
from app.ai.scalability_agent import _amdahl, _gustafson, _r_squared


class TestAmdahlMathematically:
    """
    Amdahl's Law: S(P) = 1 / ((1-p) + p/P)
    Known properties:
      - S(1) = 1 for all p
      - S(∞) = 1/(1-p)
      - S is monotonically increasing in P for fixed p > 0
      - S is monotonically increasing in p for fixed P > 1
    """

    @pytest.mark.parametrize("p", [0.0, 0.5, 0.8, 0.95, 0.999])
    def test_single_worker_gives_one(self, p):
        result = float(_amdahl(np.array([1.0]), p)[0])
        assert abs(result - 1.0) < 1e-9, f"Amdahl(P=1, p={p}) = {result}, expected 1.0"

    @pytest.mark.parametrize("p,ceiling", [
        (0.5, 2.0),
        (0.8, 5.0),
        (0.9, 10.0),
        (0.75, 4.0),
    ])
    def test_ceiling_matches_formula(self, p, ceiling):
        """At large P, speedup should approach 1/(1-p)."""
        result = float(_amdahl(np.array([1e6]), p)[0])
        assert abs(result - ceiling) < 0.01, f"Expected ceiling {ceiling}, got {result}"

    @pytest.mark.parametrize("p", [0.5, 0.7, 0.9])
    def test_monotonically_increasing_in_P(self, p):
        workers = [1, 2, 4, 8, 16, 32]
        speedups = [float(_amdahl(np.array([float(w)]), p)[0]) for w in workers]
        for i in range(1, len(speedups)):
            assert speedups[i] > speedups[i-1], \
                f"Amdahl not monotone at p={p}: S({workers[i]})={speedups[i]} <= S({workers[i-1]})={speedups[i-1]}"

    @pytest.mark.parametrize("P", [2, 4, 8, 16])
    def test_monotonically_increasing_in_p(self, P):
        p_vals = [0.1, 0.3, 0.5, 0.7, 0.9]
        speedups = [float(_amdahl(np.array([float(P)]), p)[0]) for p in p_vals]
        for i in range(1, len(speedups)):
            assert speedups[i] >= speedups[i-1], \
                f"Amdahl not monotone in p at P={P}"

    def test_no_nan_or_inf(self):
        for p in np.linspace(0, 0.9999, 50):
            for workers in [1, 2, 4, 8, 16, 32]:
                result = float(_amdahl(np.array([float(workers)]), p)[0])
                assert math.isfinite(result), f"Non-finite result: p={p}, P={workers}"

    def test_p_zero_gives_speedup_one(self):
        """Zero parallel fraction: serial-only, speedup = 1 always."""
        for workers in [1, 2, 4, 8]:
            result = float(_amdahl(np.array([float(workers)]), 0.0)[0])
            assert abs(result - 1.0) < 1e-9


class TestGustafsonMathematically:
    """
    Gustafson's Law: S(P) = P - α(P-1)
    Known properties:
      - S(1) = 1 for all α
      - S(P) = P when α = 0 (ideal)
      - S(P) = 1 when α = 1 (no speedup)
      - S is linear in P
    """

    @pytest.mark.parametrize("alpha", [0.0, 0.1, 0.3, 0.5, 0.9])
    def test_single_worker_gives_one(self, alpha):
        result = float(_gustafson(np.array([1.0]), alpha)[0])
        assert abs(result - 1.0) < 1e-9

    def test_zero_serial_gives_linear(self):
        """α=0: S(P) = P."""
        for P in [2, 4, 8, 16]:
            result = float(_gustafson(np.array([float(P)]), 0.0)[0])
            assert abs(result - P) < 1e-9

    def test_full_serial_gives_one(self):
        """α=1: S(P) = 1 for all P."""
        for P in [2, 4, 8]:
            result = float(_gustafson(np.array([float(P)]), 1.0)[0])
            assert abs(result - 1.0) < 1e-9

    def test_linear_in_P(self):
        """S(P) = P - α(P-1) is linear in P."""
        alpha = 0.3
        s2 = float(_gustafson(np.array([2.0]), alpha)[0])
        s4 = float(_gustafson(np.array([4.0]), alpha)[0])
        s8 = float(_gustafson(np.array([8.0]), alpha)[0])
        # Slope should be constant = (1 - alpha)
        slope_24 = (s4 - s2) / 2
        slope_48 = (s8 - s4) / 4
        assert abs(slope_24 - (1 - alpha)) < 1e-9
        assert abs(slope_48 - (1 - alpha)) < 1e-9


class TestWorkloadResultDerived:
    """
    Tests WorkloadResult.compute_derived() produces correct speedup/efficiency.
    Speedup = sequential_time / execution_time
    Efficiency = (speedup / worker_count) * 100
    """

    def test_basic_speedup_calculation(self):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=4,
            iterations=1,
            sequential_time=4.0,
            execution_time=1.0,
        )
        r.compute_derived()
        assert abs(r.speedup - 4.0) < 1e-9

    def test_basic_efficiency_calculation(self):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=4,
            iterations=1,
            sequential_time=4.0,
            execution_time=2.0,  # speedup = 2
        )
        r.compute_derived()
        # efficiency = (2/4) * 100 = 50%
        assert abs(r.efficiency - 50.0) < 1e-9

    def test_single_worker_efficiency_is_100(self):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=1,
            iterations=1,
            sequential_time=1.0,
            execution_time=1.0,
        )
        r.compute_derived()
        assert abs(r.efficiency - 100.0) < 1e-9

    def test_zero_execution_time_uses_fallback(self):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=4,
            iterations=1,
            sequential_time=0.0,
            execution_time=0.0,
        )
        r.compute_derived()
        # Should not crash; fallback values
        assert r.speedup == 1.0
        assert r.efficiency == 100.0

    @pytest.mark.parametrize("seq,par,workers,expected_speedup", [
        (1.0, 0.5, 2, 2.0),
        (1.0, 0.25, 4, 4.0),
        (1.0, 0.8, 1, 1.25),
        (2.0, 1.0, 2, 2.0),
    ])
    def test_speedup_parametrized(self, seq, par, workers, expected_speedup):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=workers,
            iterations=1,
            sequential_time=seq,
            execution_time=par,
        )
        r.compute_derived()
        assert abs(r.speedup - expected_speedup) < 1e-6

    def test_speedup_rounds_to_4_decimal_places(self):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=3,
            iterations=1,
            sequential_time=1.0,
            execution_time=0.3,  # speedup = 3.3333...
        )
        r.compute_derived()
        # Should be rounded to 4 decimal places
        assert len(str(r.speedup).split(".")[-1]) <= 4


class TestEfficiencyBounds:
    """
    Super-linear speedup (efficiency > 100%) is physically unusual but possible
    due to cache effects. The system should not clip it.
    """

    def test_superlinear_speedup_not_clipped(self):
        r = WorkloadResult(
            workload_type="test",
            input_size=100,
            worker_count=4,
            iterations=1,
            sequential_time=1.0,
            execution_time=0.2,  # speedup = 5x, efficiency = 125%
        )
        r.compute_derived()
        assert r.speedup > 4.0
        assert r.efficiency > 100.0


class TestRSquaredMath:
    """Mathematical properties of R² computation."""

    def test_identical_predictions_give_r2_one(self):
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(_r_squared(y, y) - 1.0) < 1e-10

    def test_constant_true_gives_r2_one(self):
        """When all y values are the same, R² is defined as 1.0 (no variance to explain)."""
        y = np.array([3.0, 3.0, 3.0, 3.0])
        assert _r_squared(y, y) == 1.0

    def test_r2_symmetry_is_not_expected(self):
        """R² is not symmetric — check it doesn't accidentally apply both ways."""
        y = np.array([1.0, 2.0, 3.0])
        y_hat = np.array([1.1, 2.2, 2.8])
        r2_forward = _r_squared(y, y_hat)
        assert r2_forward <= 1.0

    @pytest.mark.parametrize("noise_scale", [0.5, 1.0])
    def test_noisier_data_gives_lower_r2(self, noise_scale):
        """Higher noise should produce lower R² than low-noise predictions."""
        rng = np.random.default_rng(42)
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        low_noise = y + rng.normal(0, 0.001, len(y))
        high_noise = y + rng.normal(0, noise_scale, len(y))
        r2_low = _r_squared(y, low_noise)
        r2_high = _r_squared(y, high_noise)
        # With clearly different noise levels this should be deterministic
        assert r2_low >= r2_high, (
            f"Expected r2_low ({r2_low:.4f}) >= r2_high ({r2_high:.4f}) "
            f"for noise_scale={noise_scale}"
        )
