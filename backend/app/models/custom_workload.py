import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CustomWorkload(Base):
    __tablename__ = "custom_workloads"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)

    # Status of the workload record
    status: Mapped[str] = mapped_column(String(16), default="available")

    # AST validation results
    validation_status: Mapped[str] = mapped_column(String(16), default="pending")
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    validation_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CustomWorkload id={self.id!r} name={self.name!r} "
            f"validation={self.validation_status!r}>"
        )
