from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BenchmarkRunCreate(BaseModel):
    workload_type: str = Field(
        ...,
        description="One of: matrix_multiplication, parallel_sort, image_processing, graph_bfs",
    )
    input_size: int = Field(..., ge=1, description="Problem size (N for N×N matrix, etc.)")
    worker_count: int = Field(..., ge=1, le=32, description="Parallel worker / process count")
    iterations: int = Field(default=1, ge=1, le=10, description="Number of benchmark iterations")


class BenchmarkRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    workload_type: str
    workload_name: str | None
    input_size: int
    worker_count: int
    iterations: int

    execution_time: float | None
    sequential_time: float | None
    speedup: float | None
    efficiency: float | None
    cpu_usage: float | None
    memory_usage: float | None
    peak_memory_mb: float | None

    quality_score: str | None
    measurement_warning: str | None

    status: str
    error_message: str | None
    ai_analysis: dict[str, Any] | None
    observability_data: dict[str, Any] | None
    profiling_data: dict[str, Any] | None
    flame_graph_svg: str | None

    created_at: datetime
    completed_at: datetime | None


class BenchmarkRunSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    workload_type: str
    workload_name: str | None
    input_size: int
    worker_count: int
    execution_time: float | None
    speedup: float | None
    efficiency: float | None
    cpu_usage: float | None
    memory_usage: float | None
    status: str
    created_at: datetime


class AIAnalysisResponse(BaseModel):
    benchmark_id: str
    analysis: dict[str, Any]


class ReportResponse(BaseModel):
    benchmark_id: str
    workload_type: str
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    analysis: dict[str, Any] | None
    generated_at: datetime
