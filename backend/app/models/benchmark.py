import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workload_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workload_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_size: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_count: Mapped[int] = mapped_column(Integer, nullable=False)
    iterations: Mapped[int] = mapped_column(Integer, default=1)

    # Timing
    execution_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    sequential_time: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Derived metrics
    speedup: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Resource utilization
    cpu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_memory_mb: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Benchmark quality assessment
    quality_score: Mapped[str | None] = mapped_column(String(16), nullable=True)
    measurement_warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status lifecycle
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI analysis (stored as JSON)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Observability time-series (from ResourceSampler)
    observability_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Profiling data (cProfile hotspots)
    profiling_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    flame_graph_svg: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BenchmarkRun id={self.id!r} workload={self.workload_type!r} "
            f"status={self.status!r}>"
        )
