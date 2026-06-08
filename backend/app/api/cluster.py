from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.cluster import ClusterNodeResponse, ClusterSummaryResponse, NodeHeartbeat
from app.services.cluster_service import ClusterService

router = APIRouter(prefix="/api/cluster", tags=["cluster"])


@router.post("/heartbeat", response_model=ClusterNodeResponse)
def heartbeat(payload: NodeHeartbeat, db: Session = Depends(get_db)):
    """Remote node sends this to register or refresh its presence."""
    svc = ClusterService(db)
    return svc.heartbeat(payload)


@router.get("", response_model=ClusterSummaryResponse)
def get_cluster(db: Session = Depends(get_db)):
    svc = ClusterService(db)
    # Sweep stale nodes before returning summary
    stale = svc.mark_stale_nodes_offline()
    # Refresh local metrics
    svc.refresh_local_metrics()
    return svc.get_summary()


@router.get("/nodes", response_model=list[ClusterNodeResponse])
def list_nodes(db: Session = Depends(get_db)):
    svc = ClusterService(db)
    svc.mark_stale_nodes_offline()
    svc.refresh_local_metrics()
    return svc.list_nodes()


@router.get("/nodes/{node_id}", response_model=ClusterNodeResponse)
def get_node(node_id: str, db: Session = Depends(get_db)):
    svc = ClusterService(db)
    node = svc.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: str, db: Session = Depends(get_db)):
    svc = ClusterService(db)
    if not svc.delete_node(node_id):
        raise HTTPException(
            status_code=404, detail="Node not found or cannot delete local node"
        )
