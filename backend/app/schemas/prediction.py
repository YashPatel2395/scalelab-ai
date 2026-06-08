from pydantic import BaseModel, Field


class ScalabilityPredictionRequest(BaseModel):
    workload_type: str
    input_size: int = Field(..., ge=1)
    target_worker_counts: list[int] = Field(
        default=[1, 2, 4, 8, 16],
        description="Worker counts to predict speedup for",
    )


class AmdahlPrediction(BaseModel):
    worker_count: int
    predicted_speedup: float
    predicted_efficiency: float
    confidence: float   # 0–1, based on fit R²


class ScalabilityPredictionResponse(BaseModel):
    workload_type: str
    input_size: int
    model_used: str                        # "amdahl" | "gustafson" | "insufficient_data"
    parallel_fraction: float | None        # fitted p for Amdahl
    serial_overhead: float | None          # fitted α for Gustafson
    r_squared: float | None                # goodness-of-fit
    data_points_used: int
    predictions: list[AmdahlPrediction]
    theoretical_max_speedup: float | None  # 1/(1-p) for Amdahl
    recommendation: str
