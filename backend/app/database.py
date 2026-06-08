from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.models import benchmark, experiment, cluster_node, custom_workload  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_missing_columns()


def _apply_missing_columns() -> None:
    """
    Forward-only schema migration for SQLite.

    SQLAlchemy's create_all() is a no-op on existing tables, so a stale
    database from an older release will be missing new columns.  Rather
    than crashing at runtime we detect missing columns and add them with
    ALTER TABLE … ADD COLUMN.  This is safe for SQLite (add-only) and
    produces a clear warning so developers know a migration happened.

    For PostgreSQL in production, use Alembic.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    added: list[str] = []

    # Map of table → {column_name: DEFAULT_DDL_fragment}
    # Only nullable / default-bearing columns are safe to add after the fact.
    EXPECTED: dict[str, dict[str, str]] = {
        "benchmark_runs": {
            "observability_data": "JSON",
            "ai_analysis": "JSON",
            "completed_at": "DATETIME",
            "peak_memory_mb": "FLOAT",
            "iterations": "INTEGER DEFAULT 1",
            "workload_name": "VARCHAR(255)",
            "profiling_data": "JSON",
            "flame_graph_svg": "TEXT",
            "quality_score": "VARCHAR(16)",
            "measurement_warning": "TEXT",
        },
    }

    with engine.begin() as conn:
        for table_name, columns in EXPECTED.items():
            if not inspector.has_table(table_name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table_name)}
            for col_name, col_type in columns.items():
                if col_name not in existing:
                    conn.execute(
                        text(
                            f'ALTER TABLE "{table_name}" '
                            f'ADD COLUMN "{col_name}" {col_type}'
                        )
                    )
                    added.append(f"{table_name}.{col_name}")

    if added:
        import logging
        logging.getLogger(__name__).warning(
            "Schema migration applied — added missing columns: %s. "
            "This indicates a stale database from an older release. "
            "For production use Alembic migrations.",
            ", ".join(added),
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
