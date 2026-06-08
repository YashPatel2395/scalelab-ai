"""
Unit tests for BenchmarkService.

Tests create/list/get/delete lifecycle and summary stats.
Workload execution is NOT invoked here — that belongs to integration tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.services.benchmark_service import BenchmarkService
from app.schemas.benchmark import BenchmarkRunCreate
from app.models.benchmark import BenchmarkRun


class TestBenchmarkServiceCreate:
    def test_create_returns_pending_run(self, db):
        svc = BenchmarkService(db)
        payload = BenchmarkRunCreate(
            workload_type="image_processing",
            input_size=128,
            worker_count=2,
            iterations=1,
        )
        run = svc.create(payload)

        assert run.id is not None
        assert run.status == "pending"
        assert run.workload_type == "image_processing"
        assert run.input_size == 128
        assert run.worker_count == 2
        assert run.speedup is None
        assert run.execution_time is None

    def test_create_invalid_workload_raises(self, db):
        svc = BenchmarkService(db)
        payload = BenchmarkRunCreate(
            workload_type="does_not_exist",
            input_size=128,
            worker_count=2,
            iterations=1,
        )
        with pytest.raises(ValueError, match="Unknown workload"):
            svc.create(payload)

    def test_create_persists_to_db(self, db):
        svc = BenchmarkService(db)
        payload = BenchmarkRunCreate(
            workload_type="parallel_sort",
            input_size=10000,
            worker_count=4,
            iterations=1,
        )
        run = svc.create(payload)
        fetched = db.query(BenchmarkRun).filter(BenchmarkRun.id == run.id).first()
        assert fetched is not None
        assert fetched.workload_type == "parallel_sort"


class TestBenchmarkServiceList:
    def test_list_returns_all(self, db, make_benchmark_run):
        make_benchmark_run(workload_type="image_processing")
        make_benchmark_run(workload_type="parallel_sort")
        svc = BenchmarkService(db)
        runs = svc.list()
        assert len(runs) >= 2

    def test_list_filters_by_workload_type(self, db, make_benchmark_run):
        make_benchmark_run(workload_type="image_processing")
        make_benchmark_run(workload_type="parallel_sort")
        svc = BenchmarkService(db)
        runs = svc.list(workload_type="image_processing")
        assert all(r.workload_type == "image_processing" for r in runs)

    def test_list_filters_by_status(self, db, make_benchmark_run):
        make_benchmark_run(status="completed")
        make_benchmark_run(status="failed")
        svc = BenchmarkService(db)
        completed = svc.list(status="completed")
        assert all(r.status == "completed" for r in completed)

    def test_list_respects_limit(self, db, make_benchmark_run):
        for _ in range(5):
            make_benchmark_run()
        svc = BenchmarkService(db)
        runs = svc.list(limit=3)
        assert len(runs) <= 3

    def test_list_sorted_by_created_at_desc(self, db, make_benchmark_run):
        r1 = make_benchmark_run()
        r2 = make_benchmark_run()
        svc = BenchmarkService(db)
        runs = svc.list()
        ids = [r.id for r in runs]
        # Most recent should be first
        assert ids.index(r2.id) < ids.index(r1.id)


class TestBenchmarkServiceGet:
    def test_get_existing(self, db, make_benchmark_run):
        run = make_benchmark_run()
        svc = BenchmarkService(db)
        fetched = svc.get(run.id)
        assert fetched is not None
        assert fetched.id == run.id

    def test_get_nonexistent_returns_none(self, db):
        svc = BenchmarkService(db)
        result = svc.get("non-existent-id-000")
        assert result is None


class TestBenchmarkServiceDelete:
    def test_delete_existing(self, db, make_benchmark_run):
        run = make_benchmark_run()
        svc = BenchmarkService(db)
        deleted = svc.delete(run.id)
        assert deleted is True
        assert svc.get(run.id) is None

    def test_delete_nonexistent_returns_false(self, db):
        svc = BenchmarkService(db)
        result = svc.delete("ghost-id-000")
        assert result is False


class TestBenchmarkServiceStats:
    def test_stats_empty(self, db):
        svc = BenchmarkService(db)
        stats = svc.get_summary_stats()
        assert stats["total_runs"] == 0
        assert stats["completed_runs"] == 0
        assert stats["best_speedup"] == 0.0

    def test_stats_with_completed_runs(self, db, make_benchmark_run):
        make_benchmark_run(speedup=2.5, efficiency=62.5)
        make_benchmark_run(speedup=3.1, efficiency=77.5)
        make_benchmark_run(status="failed")
        svc = BenchmarkService(db)
        stats = svc.get_summary_stats()
        assert stats["total_runs"] == 3
        assert stats["completed_runs"] == 2
        assert stats["failed_runs"] == 1
        assert abs(stats["best_speedup"] - 3.1) < 0.01

    def test_stats_average_efficiency(self, db, make_benchmark_run):
        make_benchmark_run(efficiency=80.0)
        make_benchmark_run(efficiency=60.0)
        svc = BenchmarkService(db)
        stats = svc.get_summary_stats()
        assert abs(stats["average_efficiency"] - 70.0) < 0.1


class TestBenchmarkServiceSaveAnalysis:
    def test_save_analysis_persists(self, db, make_benchmark_run):
        run = make_benchmark_run()
        svc = BenchmarkService(db)
        analysis = {"bottleneck_type": "cpu_bound", "speedup_explanation": "Test"}
        updated = svc.save_analysis(run.id, analysis)
        assert updated.ai_analysis["bottleneck_type"] == "cpu_bound"

    def test_save_analysis_nonexistent_raises(self, db):
        svc = BenchmarkService(db)
        with pytest.raises(KeyError):
            svc.save_analysis("ghost", {"key": "val"})


class TestBenchmarkServiceExecute:
    """
    Tests execute() with small workloads to validate the full execution path
    including ResourceSampler integration and status transitions.
    """

    def test_execute_image_processing_transitions_to_completed(self, db):
        """End-to-end: pending → running → completed with real workload."""
        svc = BenchmarkService(db)
        payload = BenchmarkRunCreate(
            workload_type="image_processing",
            input_size=64,   # tiny — fast
            worker_count=1,
            iterations=1,
        )
        run = svc.create(payload)
        assert run.status == "pending"

        result = svc.execute(run.id)

        assert result.status == "completed"
        assert result.execution_time is not None
        assert result.execution_time > 0
        assert result.speedup is not None
        assert result.speedup > 0
        assert result.completed_at is not None

    def test_execute_parallel_sort_metrics_sane(self, db):
        """Parallel sort with 2 workers: speedup > 0, efficiency 0–200%."""
        svc = BenchmarkService(db)
        payload = BenchmarkRunCreate(
            workload_type="parallel_sort",
            input_size=50000,
            worker_count=2,
            iterations=1,
        )
        run = svc.create(payload)
        result = svc.execute(run.id)

        assert result.status == "completed"
        assert 0 < result.speedup < 20   # physically plausible
        assert 0 < result.efficiency <= 200

    def test_execute_invalid_run_id_raises(self, db):
        svc = BenchmarkService(db)
        with pytest.raises(KeyError):
            svc.execute("does-not-exist")

    def test_execute_stores_observability_data(self, db):
        """ResourceSampler output should be stored in the run."""
        svc = BenchmarkService(db)
        payload = BenchmarkRunCreate(
            workload_type="image_processing",
            input_size=64,
            worker_count=1,
            iterations=1,
        )
        run = svc.create(payload)
        result = svc.execute(run.id)

        assert result.observability_data is not None
        assert "cpu_avg" in result.observability_data
        assert "duration_seconds" in result.observability_data
        assert result.observability_data["duration_seconds"] > 0
