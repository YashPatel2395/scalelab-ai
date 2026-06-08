from app.workloads.base import WorkloadResult
from app.workloads.matrix_multiplication import MatrixMultiplicationWorkload
from app.workloads.parallel_sort import ParallelSortWorkload
from app.workloads.image_processing import ImageProcessingWorkload
from app.workloads.graph_bfs import GraphBFSWorkload
from app.workloads.ai_inference import AiInferenceWorkload
from app.workloads.etl_pipeline import EtlPipelineWorkload
from app.workloads.log_processing import LogProcessingWorkload
from app.workloads.fraud_detection import FraudDetectionWorkload
from app.workloads.recommendation_engine import RecommendationEngineWorkload

WORKLOAD_REGISTRY: dict[str, type] = {
    "matrix_multiplication": MatrixMultiplicationWorkload,
    "parallel_sort": ParallelSortWorkload,
    "image_processing": ImageProcessingWorkload,
    "graph_bfs": GraphBFSWorkload,
    "ai_inference": AiInferenceWorkload,
    "etl_pipeline": EtlPipelineWorkload,
    "log_processing": LogProcessingWorkload,
    "fraud_detection": FraudDetectionWorkload,
    "recommendation_engine": RecommendationEngineWorkload,
}

WORKLOAD_METADATA = {
    "matrix_multiplication": {
        "name": "Distributed Matrix Multiplication",
        "description": (
            "Row-partitioned parallel matrix multiply. Workers inherit matrix B via fork "
            "(zero IPC cost). Each worker computes its slab × B independently. "
            "Note: numpy BLAS is internally multi-threaded; process parallelism adds IPC overhead "
            "for result transfer. Best speedup at N ≥ 2048."
        ),
        "input_label": "Matrix dimension N (N×N)",
        "default_size": 2048,
        "size_presets": [512, 1024, 2048, 4096],
        "complexity": "O(N³) sequential, O(N³/P) parallel",
        "min_recommended_size": 2048,
        "size_warning": (
            "Input size too small for meaningful parallel scaling. "
            "Fork overhead (~12ms) dominates computation below N=2048. "
            "Use N ≥ 2048 for reliable speedup measurements."
        ),
    },
    "parallel_sort": {
        "name": "Parallel Sample Sort",
        "description": (
            "Partition-based parallel sort: sample quantiles to define P value-range partitions, "
            "each worker sorts its partition independently (no merge needed). "
            "Workers inherit the full array via fork. IPC cost = result bytes only. "
            "Best speedup at N ≥ 1M."
        ),
        "input_label": "Array length",
        "default_size": 5000000,
        "size_presets": [1000000, 5000000, 10000000, 50000000],
        "complexity": "O(N log N) sequential, O((N/P) log(N/P)) parallel + O(N) concatenate",
        "min_recommended_size": 1000000,
        "size_warning": (
            "Input size too small for meaningful parallel scaling. "
            "Partition overhead dominates below N=1,000,000. "
            "Use N ≥ 1,000,000 for reliable speedup measurements."
        ),
    },
    "image_processing": {
        "name": "Parallel Image Processing",
        "description": (
            "Strip-parallel Gaussian blur (σ=1.5) + Sobel edge detection. "
            "Workers inherit the image array via fork; each processes a horizontal strip. "
            "Memory-bandwidth bound – best speedup at N ≥ 2048 with P = 2–4."
        ),
        "input_label": "Image dimension (N×N pixels)",
        "default_size": 2048,
        "size_presets": [512, 1024, 2048, 4096],
        "complexity": "O(N²) sequential, O(N²/P) parallel",
        "min_recommended_size": 2048,
        "size_warning": (
            "Input size too small for meaningful parallel scaling. "
            "Fork overhead dominates computation below N=2048. "
            "Use N ≥ 2048 for reliable speedup measurements."
        ),
    },
    "graph_bfs": {
        "name": "Graph BFS Traversal",
        "description": (
            "Level-synchronous BFS on an Erdős–Rényi random graph. "
            "Workers inherit the adjacency list via fork and expand frontier partitions in parallel. "
            "Speedup bounded by graph diameter O(log N). "
            "Communication-bound for sparse graphs."
        ),
        "input_label": "Number of graph nodes",
        "default_size": 100000,
        "size_presets": [10000, 50000, 100000, 500000],
        "complexity": "O(V + E) sequential, O(diameter × V/P) parallel",
        "min_recommended_size": 100000,
        "size_warning": (
            "Input size too small for meaningful parallel scaling. "
            "BFS speedup is bounded by graph diameter O(log N); "
            "small graphs have too few BFS levels for parallelism. "
            "Use N ≥ 100,000 nodes for reliable measurements."
        ),
    },
}

WORKLOAD_METADATA["ai_inference"] = {
    "name": "AI Inference Pipeline",
    "description": (
        "Simulates a RAG/LLM serving pipeline: embedding generation, 12-pass feature "
        "enrichment (Gaussian smoothing + L2 norm, simulating transformer layers), "
        "vector similarity search, cross-encoder reranking, and response assembly. "
        "Dominant cost: O(N·D·P) enrichment — P=12 passes, D=128 dims."
    ),
    "input_label": "Documents in corpus",
    "default_size": 200000,
    "size_presets": [50000, 200000, 500000, 1000000],
    "complexity": "O(N·D·P) enrichment + O(N·D) similarity — D=128, P=12 passes",
    "min_recommended_size": 50000,
    "size_warning": "Use ≥ 50,000 documents for measurable parallel scaling.",
}

WORKLOAD_METADATA["etl_pipeline"] = {
    "name": "ETL Data Pipeline",
    "description": (
        "Simulates an analytics ETL pipeline: columnar data ingestion, multi-field transformation "
        "(revenue computation, tiering, normalization), categorical aggregation, and export "
        "serialization. Dominant cost: Python-loop aggregation over N records."
    ),
    "input_label": "Records",
    "default_size": 5000000,
    "size_presets": [1000000, 3000000, 5000000, 10000000],
    "complexity": "O(N) transform, O(N·G) aggregation — G=480 group buckets",
    "min_recommended_size": 1000000,
    "size_warning": "Use ≥ 1,000,000 records for meaningful ETL scaling.",
}

WORKLOAD_METADATA["log_processing"] = {
    "name": "Log Processing Pipeline",
    "description": (
        "Simulates an observability platform log analytics job: structured log ingestion, "
        "error/latency filtering, service-level grouping, statistical aggregation "
        "(latency percentiles, availability, error rates), and incident ranking. "
        "Dominant cost: Python-loop group-by aggregation over N records."
    ),
    "input_label": "Log lines",
    "default_size": 2000000,
    "size_presets": [500000, 1000000, 2000000, 5000000],
    "complexity": "O(N) parse+filter, O(N) group-by, O(G·log G) rank — G=group count",
    "min_recommended_size": 500000,
    "size_warning": "Use ≥ 500,000 log lines for meaningful scaling.",
}

WORKLOAD_METADATA["fraud_detection"] = {
    "name": "Fraud Detection Pipeline",
    "description": (
        "Simulates a financial fraud detection engine: 8-pass feature enrichment "
        "(Gaussian smoothing + L2 norm), 20-feature transaction scoring, "
        "interaction term computation, sigmoid risk normalization, multi-tier risk "
        "classification, and top-K review queue assembly."
    ),
    "input_label": "Transactions",
    "default_size": 1000000,
    "size_presets": [200000, 500000, 1000000, 5000000],
    "complexity": "O(N·D·P) enrichment + O(N·F) scoring — D=30, P=8 passes, F=20+10",
    "min_recommended_size": 200000,
    "size_warning": "Use ≥ 200,000 transactions for reliable fraud detection scaling.",
}

WORKLOAD_METADATA["recommendation_engine"] = {
    "name": "Recommendation Engine",
    "description": (
        "Simulates a collaborative-filtering recommendation service: 12-pass item feature "
        "enrichment (Gaussian smoothing + L2 norm), latent-factor affinity scoring, "
        "multi-signal ranking (affinity + popularity + recency), and Maximal Marginal "
        "Relevance diversity re-ranking. D=64 latent factors."
    ),
    "input_label": "Items in catalog",
    "default_size": 300000,
    "size_presets": [100000, 300000, 1000000, 3000000],
    "complexity": "O(N·D·P) enrichment + O(N·D) scoring + O(K²·D) MMR — D=64, P=12",
    "min_recommended_size": 100000,
    "size_warning": "Use ≥ 100,000 catalog items for meaningful recommendation scaling.",
}

WORKLOAD_METADATA["custom_python"] = {
    "name": "Custom Python Workload",
    "description": (
        "User-uploaded Python workload executed via subprocess harness. "
        "Must expose run(input_size, worker_count). "
        "Supports multiprocessing, concurrent.futures, numpy, and pure Python parallelism. "
        "AST-validated before execution — see security warning for limitations."
    ),
    "input_label": "Input size (passed to run())",
    "default_size": 10000,
    "size_presets": [1000, 10000, 100000, 1000000],
    "complexity": "User-defined",
}

__all__ = [
    "WorkloadResult",
    "WORKLOAD_REGISTRY",
    "WORKLOAD_METADATA",
    "MatrixMultiplicationWorkload",
    "ParallelSortWorkload",
    "ImageProcessingWorkload",
    "GraphBFSWorkload",
    "AiInferenceWorkload",
    "EtlPipelineWorkload",
    "LogProcessingWorkload",
    "FraudDetectionWorkload",
    "RecommendationEngineWorkload",
]
