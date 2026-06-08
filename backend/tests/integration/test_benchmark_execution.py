"""
Integration tests for full benchmark execution.

These tests run real workloads (small sizes) end-to-end:
  database → service → workload → metrics → database

Each test validates the complete data pipeline, not just individual components.
"""
from __future__ import annotations

import pytest
import time

from app.services.benchmark_service import BenchmarkService
from app.schemas.benchmark import BenchmarkRunCreate


class TestEndToEndExecution:
    """
    Run real workloads with minimum viable sizes.
    Validates: status transitions, metric computation, observability data.
    """

    @pytest.mark.parametrize("workload_type,input_size,workers", [
        ("image_processing", 64, 1),
        ("image_processing", 64, 2),
        ("parallel_sort", 10000, 1),
        ("parallel_sort", 10000, 2),
        ("graph_bfs", 500, 1),
        ("graph_bfs", 500, 2),
        # matrix_multiplication: 128×128 matrix, sequential then parallel path
        ("matrix_multiplication", 128, 1),
        ("matrix_multiplication", 128, 2),
    ])
    def test_execution_completes_successfully(self, db, workload_type, input_size, workers):
        svc = BenchmarkService(db)
        run = svc.create(BenchmarkRunCreate(
            workload_type=workload_type,
            input_size=input_size,
            worker_count=workers,
            iterations=1,
        ))
        result = svc.execute(run.id)
        assert result.status == "completed", f"Failed: {result.error_message}"

    @pytest.mark.parametrize("workload_type,input_size", [
        ("image_processing", 64),
        ("parallel_sort", 10000),
    ])
    def test_execution_produces_positive_times(self, db, workload_type, input_size):
        svc = BenchmarkService(db)
        run = svc.create(BenchmarkRunCreate(
            workload_type=workload_type,
            input_size=input_size,
            worker_count=1,
            iterations=1,
        ))
        result = svc.execute(run.id)
        assert result.execution_time > 0
        assert result.sequential_time > 0

    def test_speedup_and_efficiency_are_derived(self, db):
        svc = BenchmarkService(db)
        run = svc.create(BenchmarkRunCreate(
            workload_type="image_processing",
            input_size=64,
            worker_count=2,
            iterations=1,
        ))
        result = svc.execute(run.id)
        assert result.speedup is not None
        assert result.speedup > 0
        assert result.efficiency is not None
        assert result.efficiency > 0

    def test_observability_data_populated(self, db):
        svc = BenchmarkService(db)
        run = svc.create(BenchmarkRunCreate(
            workload_type="image_processing",
            input_size=64,
            worker_count=1,
            iterations=1,
        ))
        result = svc.execute(run.id)
        obs = result.observability_data
        assert obs is not None
        assert obs["sample_count"] >= 0
        assert obs["duration_seconds"] > 0
        assert "timeline" in obs
        assert isinstance(obs["timeline"], list)

    def test_completed_at_set_after_execution(self, db):
        svc = BenchmarkService(db)
        run = svc.create(BenchmarkRunCreate(
            workload_type="parallel_sort",
            input_size=5000,
            worker_count=1,
            iterations=1,
        ))
        assert run.completed_at is None
        result = svc.execute(run.id)
        assert result.completed_at is not None


class TestParallelVsSequential:
    """
    Validates that parallel execution with 2 workers on sufficient workloads
    doesn't produce wildly incorrect metrics.
    """

    def test_single_worker_speedup_is_approx_one(self, db):
        svc = BenchmarkService(db)
        run = svc.create(BenchmarkRunCreate(
            workload_type="image_processing",
            input_size=128,
            worker_count=1,
            iterations=1,
        ))
        result = svc.execute(run.id)
        # With 1 worker, speedup = sequential / parallel ≈ 1
        assert 0.5 < result.speedup < 3.0, \
            f"Suspicious 1-worker speedup: {result.speedup}"

    def test_efficiency_between_0_and_200_percent(self, db):
        svc = BenchmarkService(db)
        for workers in [1, 2]:
            run = svc.create(BenchmarkRunCreate(
                workload_type="image_processing",
                input_size=128,
                worker_count=workers,
                iterations=1,
            ))
            result = svc.execute(run.id)
            assert 0 < result.efficiency <= 200, \
                f"Efficiency out of range for {workers} workers: {result.efficiency}"


class TestExperimentIntegration:
    """End-to-end experiment flow: create → add runs → compare."""

    def test_experiment_with_real_runs(self, db):
        from app.services.experiment_service import ExperimentService
        from app.schemas.experiment import ExperimentCreate

        bench_svc = BenchmarkService(db)
        exp_svc = ExperimentService(db)

        # Create and execute two benchmark runs
        run_ids = []
        for workers in (1, 2):
            run = bench_svc.create(BenchmarkRunCreate(
                workload_type="image_processing",
                input_size=64,
                worker_count=workers,
                iterations=1,
            ))
            result = bench_svc.execute(run.id)
            run_ids.append(result.id)

        # Create experiment and add runs
        exp = exp_svc.create(ExperimentCreate(name="Scaling Test"))
        exp_svc.add_runs(exp.id, run_ids)

        # Compare
        comparison = exp_svc.compare(exp.id)
        assert comparison["summary"]["completed_runs"] == 2
        assert comparison["summary"]["best_speedup"] > 0

    def test_scalability_prediction_from_real_runs(self, db):
        from app.ai.scalability_agent import predict_scalability

        bench_svc = BenchmarkService(db)
        data_points = []

        for workers in (1, 2, 4):
            run = bench_svc.create(BenchmarkRunCreate(
                workload_type="image_processing",
                input_size=128,
                worker_count=workers,
                iterations=1,
            ))
            result = bench_svc.execute(run.id)
            if result.speedup:
                data_points.append({"worker_count": workers, "speedup": result.speedup})

        # We have 3 real data points — should fit a model
        prediction = predict_scalability(data_points, [1, 2, 4, 8])
        assert prediction["data_points_used"] == 3
        # With real (possibly noisy) data, model_used may be amdahl or gustafson
        assert prediction["model_used"] in ("amdahl", "gustafson")
