"""Scalability Certification Report endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.certification_service import CertificationService

router = APIRouter(prefix="/api/certification", tags=["Certification"])


class CertificationRequest(BaseModel):
    run_ids: list[str] = Field(..., description="IDs of completed BenchmarkRun records (one per worker count)")
    workload_display_name: str | None = Field(default=None, description="Human-readable workload name")


@router.post("")
def generate_certification(payload: CertificationRequest, db: Session = Depends(get_db)):
    """
    Generate a Scalability Certification Report from a set of benchmark runs.
    Returns JSON with embedded Markdown and HTML exports.
    """
    svc = CertificationService(db)
    try:
        report = svc.generate(
            run_ids=payload.run_ids,
            workload_display_name=payload.workload_display_name,
        )
        return report
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/markdown")
def get_certification_markdown(payload: CertificationRequest, db: Session = Depends(get_db)):
    """Generate certification report and return as Markdown text."""
    svc = CertificationService(db)
    try:
        report = svc.generate(run_ids=payload.run_ids, workload_display_name=payload.workload_display_name)
        return Response(content=report["export_markdown"], media_type="text/markdown")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/html")
def get_certification_html(payload: CertificationRequest, db: Session = Depends(get_db)):
    """Generate certification report and return as print-ready HTML."""
    svc = CertificationService(db)
    try:
        report = svc.generate(run_ids=payload.run_ids, workload_display_name=payload.workload_display_name)
        return Response(content=report["export_html"], media_type="text/html")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
