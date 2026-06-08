from datetime import datetime

from pydantic import BaseModel, Field


class CustomWorkloadResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    filename: str
    status: str
    validation_status: str
    validation_errors: list[str] | None
    validation_warnings: list[str] | None
    created_at: datetime


class CustomWorkloadRunRequest(BaseModel):
    input_size: int = Field(..., ge=1, description="Problem size passed to run()")
    worker_count: int = Field(..., ge=1, le=32, description="Worker count passed to run()")
    iterations: int = Field(default=1, ge=1, le=10, description="Number of timed iterations")
    timeout_seconds: int = Field(default=60, ge=5, le=300, description="Subprocess timeout")
    enable_profiling: bool = Field(
        default=False,
        description=(
            "If true, the workload is profiled with cProfile during the parallel run. "
            "Profiling data (top functions, call counts, timings) is stored on the "
            "benchmark record and accessible via GET /api/profiling/{run_id}."
        ),
    )


class CustomWorkloadRunResponse(BaseModel):
    custom_workload_id: str
    workload_name: str
    input_size: int
    worker_count: int
    success: bool
    sequential_time: float | None
    execution_time: float | None
    speedup: float | None
    efficiency: float | None
    stdout: str | None
    error: str | None
    return_value: object | None


class ScalingStudyRequest(BaseModel):
    workload_type: str = Field(..., description="Built-in workload type")
    input_size: int = Field(..., ge=1, description="Input size — use same value for all runs")
    worker_counts: list[int] = Field(
        default=[1, 2, 4, 8],
        description="Worker counts to benchmark. Include 1 for baseline.",
    )
    iterations: int = Field(default=1, ge=1, le=5)
    experiment_name: str | None = Field(
        default=None, description="Name for the experiment group. Auto-generated if omitted."
    )


class ScalingStudyResponse(BaseModel):
    experiment_id: str
    experiment_name: str
    run_ids: list[str]
    workload_type: str
    input_size: int
    worker_counts: list[int]
    message: str
