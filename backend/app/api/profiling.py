"""Profiling API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.profiling_service import ProfilingService

router = APIRouter(prefix="/api/profiling", tags=["Profiling"])
_dbg = logging.getLogger(__name__)


@router.post("/{run_id}")
def profile_run(run_id: str, db: Session = Depends(get_db)):
    """
    Profile a completed benchmark run using cProfile.
    Stores hotspot data and generates SVG flame chart.
    Only available for built-in workloads.
    """
    svc = ProfilingService(db)
    try:
        result = svc.profile_benchmark(run_id)
        return {"success": True, "run_id": run_id, "hotspot_count": len(result.get("top_hotspots", []))}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{run_id}")
def get_profile(run_id: str, db: Session = Depends(get_db)):
    """Get profiling data for a run."""
    svc = ProfilingService(db)
    try:
        data = svc.get_profile(run_id)
        _dbg.info(
            "[PROFILING_DEBUG] GET /api/profiling/%s → data_type=%s total_calls=%s",
            run_id, type(data).__name__,
            data.get("total_calls") if isinstance(data, dict) else "N/A",
        )
        if data is None:
            raise HTTPException(status_code=404, detail="No profiling data for this run. POST first.")
        return data
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{run_id}/flame-graph", response_class=Response)
def get_flame_graph(run_id: str, db: Session = Depends(get_db)):
    """Get SVG flame chart for a profiled run."""
    svc = ProfilingService(db)
    try:
        svg = svc.get_flame_graph_svg(run_id)
        if svg is None:
            raise HTTPException(status_code=404, detail="No flame graph for this run. POST first.")
        return Response(content=svg, media_type="image/svg+xml")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
