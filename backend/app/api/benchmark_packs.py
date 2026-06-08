"""
Industry Benchmark Packs API
──────────────────────────────
Provides richer metadata for the five industry benchmark packs so the
frontend can render the pack selection UI without hard-coding anything.

Routes:
  GET  /api/benchmark-packs          — list all packs
  GET  /api/benchmark-packs/{id}     — get a single pack by id
"""

from fastapi import APIRouter, HTTPException

BENCHMARK_PACKS = [
    {
        "id": "ai_inference",
        "name": "AI Inference Pipeline",
        "subtitle": "Embedding · Feature Enrichment · Similarity Search · Reranking",
        "domain": "Representative of RAG systems and LLM serving applications",
        "domain_tag": "ML / AI",
        "workload_type": "ai_inference",
        "stages": [
            "Embedding Generation",
            "Feature Enrichment (12 passes)",
            "Vector Similarity Search",
            "Cross-Encoder Reranking",
        ],
        "expected_bottleneck": "cpu_bound",
        "expected_bottleneck_label": "CPU-Bound (Gaussian feature enrichment)",
        "scalability_grade": "A",
        "estimated_runtime_s": 1.2,
        "default_input_size": 200000,
        "input_label": "Documents",
        "size_presets": [50000, 200000, 500000, 1000000],
        "tags": ["ml", "nlp", "rag", "inference"],
        "color": "cyan",
    },
    {
        "id": "etl_pipeline",
        "name": "ETL Data Pipeline",
        "subtitle": "Ingest · Transform · Aggregate · Export",
        "domain": "Representative of analytics and data engineering workloads",
        "domain_tag": "Data Engineering",
        "workload_type": "etl_pipeline",
        "stages": [
            "Data Ingestion",
            "Transformation",
            "Aggregation",
            "Export",
        ],
        "expected_bottleneck": "memory_bound",
        "expected_bottleneck_label": "Memory-Bound (columnar throughput)",
        "scalability_grade": "B+",
        "estimated_runtime_s": 1.2,
        "default_input_size": 5000000,
        "input_label": "Records",
        "size_presets": [1000000, 3000000, 5000000, 10000000],
        "tags": ["etl", "analytics", "data-warehouse"],
        "color": "emerald",
    },
    {
        "id": "log_processing",
        "name": "Log Processing Pipeline",
        "subtitle": "Parse · Filter · Group · Aggregate",
        "domain": "Representative of observability and monitoring systems",
        "domain_tag": "Observability",
        "workload_type": "log_processing",
        "stages": [
            "Log Parsing",
            "Error Filtering",
            "Service Grouping",
            "Incident Ranking",
        ],
        "expected_bottleneck": "communication_bound",
        "expected_bottleneck_label": "Communication-Bound (dict merge overhead)",
        "scalability_grade": "B",
        "estimated_runtime_s": 1.3,
        "default_input_size": 2000000,
        "input_label": "Log lines",
        "size_presets": [500000, 1000000, 2000000, 5000000],
        "tags": ["observability", "logging", "sre"],
        "color": "amber",
    },
    {
        "id": "fraud_detection",
        "name": "Fraud Detection Pipeline",
        "subtitle": "Feature Enrichment · Risk Scoring · Ranking · Review Queue",
        "domain": "Representative of financial and risk-analysis platforms",
        "domain_tag": "FinTech / Risk",
        "workload_type": "fraud_detection",
        "stages": [
            "Feature Enrichment (8 passes)",
            "Risk Scoring",
            "Threshold Classification",
            "Top-K Review Queue",
        ],
        "expected_bottleneck": "cpu_bound",
        "expected_bottleneck_label": "CPU-Bound (Gaussian feature enrichment)",
        "scalability_grade": "A",
        "estimated_runtime_s": 1.2,
        "default_input_size": 1000000,
        "input_label": "Transactions",
        "size_presets": [200000, 500000, 1000000, 5000000],
        "tags": ["fintech", "risk", "fraud", "ml"],
        "color": "red",
    },
    {
        "id": "recommendation_engine",
        "name": "Recommendation Engine",
        "subtitle": "Feature Enrichment · Affinity Scoring · Ranking · MMR Diversity",
        "domain": "Representative of e-commerce and content recommendation systems",
        "domain_tag": "Personalization",
        "workload_type": "recommendation_engine",
        "stages": [
            "Feature Enrichment (12 passes)",
            "Affinity Scoring",
            "Multi-Factor Ranking",
            "MMR Re-Ranking",
        ],
        "expected_bottleneck": "cpu_bound",
        "expected_bottleneck_label": "CPU-Bound (Gaussian feature enrichment)",
        "scalability_grade": "A-",
        "estimated_runtime_s": 1.0,
        "default_input_size": 300000,
        "input_label": "Catalog items",
        "size_presets": [100000, 300000, 1000000, 3000000],
        "tags": ["ecommerce", "personalization", "recsys"],
        "color": "purple",
    },
]

# Build lookup dict for O(1) retrieval
_PACKS_BY_ID: dict[str, dict] = {p["id"]: p for p in BENCHMARK_PACKS}

router = APIRouter(prefix="/api/benchmark-packs", tags=["Benchmark Packs"])


@router.get("", summary="List all industry benchmark packs")
def list_packs() -> list[dict]:
    """Return the full list of benchmark pack metadata."""
    return BENCHMARK_PACKS


@router.get("/{pack_id}", summary="Get a single benchmark pack by ID")
def get_pack(pack_id: str) -> dict:
    """Return metadata for a single benchmark pack.

    Raises 404 if the pack_id is not recognised.
    """
    pack = _PACKS_BY_ID.get(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Benchmark pack '{pack_id}' not found.")
    return pack
