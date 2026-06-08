from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    workload_type: str | None = None
    tags: list[str] | None = None


class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    workload_type: str | None = None
    tags: list[str] | None = None


class ExperimentAddRuns(BaseModel):
    run_ids: list[str] = Field(..., min_length=1)


class ExperimentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str | None
    workload_type: str | None
    tags: list[str] | None
    run_ids: list[str]
    created_at: datetime
    updated_at: datetime


class ExperimentComparisonResponse(BaseModel):
    experiment_id: str
    experiment_name: str
    runs: list[dict[str, Any]]
    summary: dict[str, Any]
