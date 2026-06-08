import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClusterNode(Base):
    """
    Represents a compute node in the cluster.
    The local node is auto-registered on startup (is_local=True).
    Remote nodes must call the /heartbeat endpoint periodically to stay 'online'.
    """

    __tablename__ = "cluster_nodes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu_count: Mapped[int] = mapped_column(Integer, default=1)
    cpu_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_memory_gb: Mapped[float] = mapped_column(Float, default=0.0)
    disk_total_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    os_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)

    # Runtime state
    status: Mapped[str] = mapped_column(String(16), default="online")  # online|offline|degraded
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_mem_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Arbitrary metadata (tags, labels, etc.)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    registered_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ClusterNode hostname={self.hostname!r} status={self.status!r} "
            f"cpus={self.cpu_count} mem={self.total_memory_gb:.1f}GB>"
        )
