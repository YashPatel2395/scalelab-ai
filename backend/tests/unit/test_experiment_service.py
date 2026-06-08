"""
Unit tests for ExperimentService.
"""
from __future__ import annotations

import pytest

from app.services.experiment_service import ExperimentService
from app.schemas.experiment import ExperimentCreate, ExperimentUpdate


class TestExperimentServiceCreate:
    def test_create_basic(self, db):
        svc = ExperimentService(db)
        exp = svc.create(ExperimentCreate(name="My Experiment"))
        assert exp.id is not None
        assert exp.name == "My Experiment"
        assert exp.run_ids == []
        assert exp.tags == []

    def test_create_with_tags(self, db):
        svc = ExperimentService(db)
        exp = svc.create(ExperimentCreate(name="Tagged", tags=["perf", "ci"]))
        assert "perf" in exp.tags
        assert "ci" in exp.tags

    def test_create_persists(self, db):
        svc = ExperimentService(db)
        exp = svc.create(ExperimentCreate(name="Persistent"))
        fetched = svc.get(exp.id)
        assert fetched is not None
        assert fetched.name == "Persistent"


class TestExperimentServiceList:
    def test_list_empty(self, db):
        svc = ExperimentService(db)
        assert svc.list() == []

    def test_list_multiple(self, db, make_experiment):
        make_experiment(name="A")
        make_experiment(name="B")
        svc = ExperimentService(db)
        exps = svc.list()
        assert len(exps) >= 2

    def test_list_limit(self, db, make_experiment):
        for i in range(5):
            make_experiment(name=f"Exp {i}")
        svc = ExperimentService(db)
        exps = svc.list(limit=2)
        assert len(exps) == 2


class TestExperimentServiceUpdate:
    def test_update_name(self, db, make_experiment):
        exp = make_experiment(name="Old Name")
        svc = ExperimentService(db)
        updated = svc.update(exp.id, ExperimentUpdate(name="New Name"))
        assert updated.name == "New Name"

    def test_update_tags(self, db, make_experiment):
        exp = make_experiment()
        svc = ExperimentService(db)
        updated = svc.update(exp.id, ExperimentUpdate(tags=["new-tag"]))
        assert "new-tag" in updated.tags

    def test_update_nonexistent_raises(self, db):
        svc = ExperimentService(db)
        with pytest.raises(KeyError):
            svc.update("ghost-id", ExperimentUpdate(name="x"))

    def test_partial_update_preserves_other_fields(self, db, make_experiment):
        exp = make_experiment(name="Keep Me")
        svc = ExperimentService(db)
        # Update only tags, name should not change
        updated = svc.update(exp.id, ExperimentUpdate(tags=["x"]))
        assert updated.name == "Keep Me"


class TestExperimentServiceAddRuns:
    def test_add_valid_run(self, db, make_experiment, make_benchmark_run):
        exp = make_experiment()
        run = make_benchmark_run()
        svc = ExperimentService(db)
        updated = svc.add_runs(exp.id, [run.id])
        assert run.id in updated.run_ids

    def test_add_duplicate_run_is_idempotent(self, db, make_experiment, make_benchmark_run):
        exp = make_experiment()
        run = make_benchmark_run()
        svc = ExperimentService(db)
        svc.add_runs(exp.id, [run.id])
        updated = svc.add_runs(exp.id, [run.id])
        assert updated.run_ids.count(run.id) == 1

    def test_add_nonexistent_run_raises(self, db, make_experiment):
        exp = make_experiment()
        svc = ExperimentService(db)
        with pytest.raises(KeyError, match="BenchmarkRun"):
            svc.add_runs(exp.id, ["ghost-run-id"])

    def test_add_multiple_runs(self, db, make_experiment, make_benchmark_run):
        exp = make_experiment()
        runs = [make_benchmark_run() for _ in range(3)]
        svc = ExperimentService(db)
        updated = svc.add_runs(exp.id, [r.id for r in runs])
        for r in runs:
            assert r.id in updated.run_ids


class TestExperimentServiceRemoveRun:
    def test_remove_run(self, db, make_experiment, make_benchmark_run):
        exp = make_experiment()
        run = make_benchmark_run()
        svc = ExperimentService(db)
        svc.add_runs(exp.id, [run.id])
        updated = svc.remove_run(exp.id, run.id)
        assert run.id not in updated.run_ids

    def test_remove_nonexistent_run_is_safe(self, db, make_experiment):
        exp = make_experiment()
        svc = ExperimentService(db)
        updated = svc.remove_run(exp.id, "not-there")
        assert updated.run_ids == []


class TestExperimentServiceDelete:
    def test_delete_existing(self, db, make_experiment):
        exp = make_experiment()
        svc = ExperimentService(db)
        assert svc.delete(exp.id) is True
        assert svc.get(exp.id) is None

    def test_delete_nonexistent_returns_false(self, db):
        svc = ExperimentService(db)
        assert svc.delete("ghost-id") is False


class TestExperimentServiceCompare:
    def test_compare_empty_experiment(self, db, make_experiment):
        exp = make_experiment()
        svc = ExperimentService(db)
        result = svc.compare(exp.id)
        assert result["runs"] == []
        assert result["summary"] == {}

    def test_compare_with_runs(self, db, make_experiment, make_benchmark_run):
        exp = make_experiment()
        r1 = make_benchmark_run(speedup=2.0, efficiency=100.0, worker_count=2)
        r2 = make_benchmark_run(speedup=3.5, efficiency=87.5, worker_count=4)
        svc = ExperimentService(db)
        svc.add_runs(exp.id, [r1.id, r2.id])
        result = svc.compare(exp.id)

        assert len(result["runs"]) == 2
        assert result["summary"]["completed_runs"] == 2
        assert abs(result["summary"]["best_speedup"] - 3.5) < 0.01
        assert abs(result["summary"]["avg_speedup"] - 2.75) < 0.01

    def test_compare_nonexistent_raises(self, db):
        svc = ExperimentService(db)
        with pytest.raises(KeyError):
            svc.compare("ghost")
