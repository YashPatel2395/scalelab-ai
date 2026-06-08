"""
ExperimentService
─────────────────
CRUD + comparison logic for Experiment records.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.benchmark import BenchmarkRun
from app.models.experiment import Experiment
from app.schemas.experiment import ExperimentCreate, ExperimentUpdate

logger = logging.getLogger(__name__)


class ExperimentService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: ExperimentCreate) -> Experiment:
        exp = Experiment(
            name=payload.name,
            description=payload.description,
            workload_type=payload.workload_type,
            tags=payload.tags or [],
            run_ids=[],
        )
        self.db.add(exp)
        self.db.commit()
        self.db.refresh(exp)
        return exp

    def get(self, experiment_id: str) -> Experiment | None:
        return self.db.query(Experiment).filter(Experiment.id == experiment_id).first()

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        workload_type: str | None = None,
    ) -> list[Experiment]:
        q = self.db.query(Experiment)
        if workload_type:
            q = q.filter(Experiment.workload_type == workload_type)
        return q.order_by(Experiment.created_at.desc()).offset(offset).limit(limit).all()

    def update(self, experiment_id: str, payload: ExperimentUpdate) -> Experiment:
        exp = self._get_or_raise(experiment_id)
        if payload.name is not None:
            exp.name = payload.name
        if payload.description is not None:
            exp.description = payload.description
        if payload.workload_type is not None:
            exp.workload_type = payload.workload_type
        if payload.tags is not None:
            exp.tags = payload.tags
        exp.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(exp)
        return exp

    def add_runs(self, experiment_id: str, run_ids: list[str]) -> Experiment:
        exp = self._get_or_raise(experiment_id)
        existing = set(exp.run_ids or [])
        # Validate that runs exist
        for rid in run_ids:
            run = self.db.query(BenchmarkRun).filter(BenchmarkRun.id == rid).first()
            if not run:
                raise KeyError(f"BenchmarkRun '{rid}' not found")
            existing.add(rid)
        exp.run_ids = sorted(existing)
        exp.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(exp)
        return exp

    def remove_run(self, experiment_id: str, run_id: str) -> Experiment:
        exp = self._get_or_raise(experiment_id)
        exp.run_ids = [r for r in (exp.run_ids or []) if r != run_id]
        exp.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(exp)
        return exp

    def delete(self, experiment_id: str) -> bool:
        exp = self.get(experiment_id)
        if not exp:
            return False
        self.db.delete(exp)
        self.db.commit()
        return True

    def compare(self, experiment_id: str) -> dict[str, Any]:
        exp = self._get_or_raise(experiment_id)
        run_ids = exp.run_ids or []
        if not run_ids:
            return {
                "experiment_id": experiment_id,
                "experiment_name": exp.name,
                "runs": [],
                "summary": {},
            }

        runs = (
            self.db.query(BenchmarkRun)
            .filter(BenchmarkRun.id.in_(run_ids))
            .order_by(BenchmarkRun.created_at.asc())
            .all()
        )

        run_dicts = []
        for r in runs:
            run_dicts.append({
                "id": r.id,
                "workload_type": r.workload_type,
                "input_size": r.input_size,
                "worker_count": r.worker_count,
                "execution_time": r.execution_time,
                "sequential_time": r.sequential_time,
                "speedup": r.speedup,
                "efficiency": r.efficiency,
                "cpu_usage": r.cpu_usage,
                "memory_usage": r.memory_usage,
                "peak_memory_mb": r.peak_memory_mb,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        completed = [r for r in runs if r.status == "completed"]

        summary: dict[str, Any] = {
            "total_runs": len(runs),
            "completed_runs": len(completed),
        }
        if completed:
            speedups = [r.speedup or 0.0 for r in completed]
            efficiencies = [r.efficiency or 0.0 for r in completed]
            summary["best_speedup"] = round(max(speedups), 4)
            summary["avg_speedup"] = round(sum(speedups) / len(speedups), 4)
            summary["avg_efficiency"] = round(sum(efficiencies) / len(efficiencies), 2)
            best = max(completed, key=lambda r: r.speedup or 0.0)
            summary["best_run_id"] = best.id
            summary["best_run_workers"] = best.worker_count

        return {
            "experiment_id": experiment_id,
            "experiment_name": exp.name,
            "runs": run_dicts,
            "summary": summary,
        }

    def _get_or_raise(self, experiment_id: str) -> Experiment:
        exp = self.get(experiment_id)
        if not exp:
            raise KeyError(f"Experiment '{experiment_id}' not found")
        return exp
