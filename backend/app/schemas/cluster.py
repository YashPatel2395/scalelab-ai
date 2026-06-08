from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NodeHeartbeat(BaseModel):
    """Payload sent by a remote node to register itself or refresh heartbeat."""
    hostname: str
    ip_address: str
    cpu_count: int = Field(default=1, ge=1)
    cpu_model: str | None = None
    total_memory_gb: float = Field(default=0.0, ge=0)
    disk_total_gb: float | None = None
    os_info: str | None = None
    current_cpu_pct: float | None = None
    current_mem_pct: float | None = None
    metadata_json: dict[str, Any] | None = None


class ClusterNodeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    hostname: str
    ip_address: str
    cpu_count: int
    cpu_model: str | None
    total_memory_gb: float
    disk_total_gb: float | None
    os_info: str | None
    is_local: bool
    status: str
    last_heartbeat: datetime | None
    current_cpu_pct: float | None
    current_mem_pct: float | None
    metadata_json: dict[str, Any] | None
    registered_at: datetime


class ClusterSummaryResponse(BaseModel):
    total_nodes: int
    online_nodes: int
    offline_nodes: int
    degraded_nodes: int
    total_cpu_cores: int
    total_memory_gb: float
    nodes: list[ClusterNodeResponse]
