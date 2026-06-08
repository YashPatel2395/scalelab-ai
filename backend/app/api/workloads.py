from fastapi import APIRouter

from app.workloads import WORKLOAD_METADATA

router = APIRouter(prefix="/api/workloads", tags=["Workloads"])


@router.get("")
def list_workloads():
    """Return metadata for all supported workload types."""
    return {
        "workloads": [
            {"id": key, **meta}
            for key, meta in WORKLOAD_METADATA.items()
        ]
    }


@router.get("/{workload_id}")
def get_workload(workload_id: str):
    if workload_id not in WORKLOAD_METADATA:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Workload '{workload_id}' not found")
    return {"id": workload_id, **WORKLOAD_METADATA[workload_id]}
