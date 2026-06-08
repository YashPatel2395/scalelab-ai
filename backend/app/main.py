import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.logging_config import configure_logging, RequestIDMiddleware, get_logger

# Configure structured logging before anything else
configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_logs=os.getenv("JSON_LOGS", "").lower() in ("1", "true", "yes"),
)
logger = get_logger(__name__)

settings = get_settings()

app = FastAPI(
    title="ScaleLab AI",
    description="Parallel Performance Benchmarking and Scalability Analysis Platform – Backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logger.info("ScaleLab AI starting up…")
    init_db()
    logger.info("Database initialized. AI provider: %s", settings.ai_provider)

    # Auto-register the local machine as a cluster node
    try:
        from app.database import SessionLocal
        from app.services.cluster_service import ClusterService
        db = SessionLocal()
        try:
            svc = ClusterService(db)
            node = svc.auto_register_local()
            logger.info("Local cluster node registered: %s", node.hostname)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not register local cluster node: %s", exc)


# ── Routers ──────────────────────────────────────────────────────────────────
from app.api.health import router as health_router
from app.api.workloads import router as workloads_router
from app.api.benchmarks import router as benchmarks_router
from app.api.experiments import router as experiments_router
from app.api.cluster import router as cluster_router
from app.api.analytics import router as analytics_router
from app.api.custom_workloads import router as custom_workloads_router
from app.api.diagnosis import router as diagnosis_router
from app.api.profiling import router as profiling_router
from app.api.certification import router as certification_router
from app.api.benchmark_packs import router as benchmark_packs_router

app.include_router(health_router)
app.include_router(workloads_router)
app.include_router(benchmarks_router)
app.include_router(experiments_router)
app.include_router(cluster_router)
app.include_router(analytics_router)
app.include_router(custom_workloads_router)
app.include_router(diagnosis_router)
app.include_router(profiling_router)
app.include_router(certification_router)
app.include_router(benchmark_packs_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level="info",
    )
