"""
Shared pytest fixtures for ScaleLab AI backend tests.

Uses an in-memory SQLite database per test session so tests are:
  - Isolated (no shared state between test runs)
  - Fast (no disk I/O)
  - Reproducible (fresh schema every run)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base, get_db
from app.main import app
from app.models import benchmark, experiment, cluster_node  # noqa: F401 – registers tables


# ── In-memory database ────────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Single engine for the entire test session."""
    eng = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def db(engine) -> Session:
    """
    Fresh transactional session per test.
    Rolls back after each test so data never leaks between tests.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestSession()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def client(db: Session) -> TestClient:
    """
    TestClient with the DB dependency overridden to use the test session.
    All API calls go through the real app stack against the in-memory DB.
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass  # managed by the `db` fixture

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Minimal benchmark factory ─────────────────────────────────────────────────

@pytest.fixture
def make_benchmark_run(db: Session):
    """Factory: creates a BenchmarkRun with sensible defaults. Returns the ORM object."""
    from app.models.benchmark import BenchmarkRun
    from datetime import datetime

    def _make(
        workload_type: str = "image_processing",
        input_size: int = 128,
        worker_count: int = 2,
        status: str = "completed",
        speedup: float = 1.8,
        efficiency: float = 90.0,
        execution_time: float = 0.5,
        sequential_time: float = 0.9,
        cpu_usage: float = 65.0,
        memory_usage: float = 40.0,
        peak_memory_mb: float = 128.0,
    ) -> BenchmarkRun:
        run = BenchmarkRun(
            workload_type=workload_type,
            input_size=input_size,
            worker_count=worker_count,
            iterations=1,
            status=status,
            speedup=speedup,
            efficiency=efficiency,
            execution_time=execution_time,
            sequential_time=sequential_time,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            peak_memory_mb=peak_memory_mb,
            completed_at=datetime.utcnow() if status == "completed" else None,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    return _make


@pytest.fixture
def completed_run(make_benchmark_run):
    """A ready-made completed benchmark run."""
    return make_benchmark_run()


@pytest.fixture
def make_experiment(db: Session):
    """Factory: creates an Experiment."""
    from app.models.experiment import Experiment
    from datetime import datetime

    def _make(name: str = "Test Experiment", tags: list | None = None) -> Experiment:
        exp = Experiment(
            name=name,
            tags=tags or [],
            run_ids=[],
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp

    return _make
