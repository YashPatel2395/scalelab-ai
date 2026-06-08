from pydantic import BaseModel


class RecommendationRequest(BaseModel):
    workload_type: str
    input_size: int
    available_workers: int = 32   # upper bound on cluster capacity


class BottleneckReport(BaseModel):
    benchmark_id: str
    bottleneck_type: str          # cpu_bound | memory_bound | io_bound | communication_bound | balanced
    severity: str                 # critical | high | medium | low
    severity_score: float         # 0.0 – 1.0
    root_cause: str
    evidence: list[str]
    recommendations: list[str]
    estimated_max_improvement: float  # % improvement achievable


class RecommendationResponse(BaseModel):
    workload_type: str
    input_size: int
    optimal_worker_count: int
    expected_speedup: float
    expected_efficiency: float
    reasoning: str
    alternative_counts: list[dict]   # [{"workers": N, "speedup": X, "efficiency": Y}]
    data_points_used: int
