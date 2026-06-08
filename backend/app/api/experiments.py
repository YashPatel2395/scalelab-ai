from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.experiment import (
    ExperimentAddRuns,
    ExperimentComparisonResponse,
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
)
from app.services.experiment_service import ExperimentService

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    svc = ExperimentService(db)
    return svc.create(payload)


@router.get("", response_model=list[ExperimentResponse])
def list_experiments(
    limit: int = 100,
    offset: int = 0,
    workload_type: str | None = None,
    db: Session = Depends(get_db),
):
    svc = ExperimentService(db)
    return svc.list(limit=limit, offset=offset, workload_type=workload_type)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: str, db: Session = Depends(get_db)):
    svc = ExperimentService(db)
    exp = svc.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    db: Session = Depends(get_db),
):
    svc = ExperimentService(db)
    try:
        return svc.update(experiment_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Experiment not found")


@router.post("/{experiment_id}/runs", response_model=ExperimentResponse)
def add_runs(
    experiment_id: str,
    payload: ExperimentAddRuns,
    db: Session = Depends(get_db),
):
    svc = ExperimentService(db)
    try:
        return svc.add_runs(experiment_id, payload.run_ids)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{experiment_id}/runs/{run_id}", response_model=ExperimentResponse)
def remove_run(experiment_id: str, run_id: str, db: Session = Depends(get_db)):
    svc = ExperimentService(db)
    try:
        return svc.remove_run(experiment_id, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Experiment not found")


@router.get("/{experiment_id}/compare", response_model=ExperimentComparisonResponse)
def compare_experiment(experiment_id: str, db: Session = Depends(get_db)):
    svc = ExperimentService(db)
    try:
        return svc.compare(experiment_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Experiment not found")


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experiment(experiment_id: str, db: Session = Depends(get_db)):
    svc = ExperimentService(db)
    if not svc.delete(experiment_id):
        raise HTTPException(status_code=404, detail="Experiment not found")
