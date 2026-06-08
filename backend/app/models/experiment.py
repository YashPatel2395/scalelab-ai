import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Experiment(Base):
    """
    An experiment groups a set of benchmark runs under a named study.
    Run IDs are stored as a JSON list to avoid migration complexity
    while maintaining referential awareness.
    """

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workload_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Flexible metadata
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list[str]
    run_ids: Mapped[list] = mapped_column(JSON, default=list)        # list[str] – FK logical

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Experiment id={self.id!r} name={self.name!r} runs={len(self.run_ids or [])}>"
