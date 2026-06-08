<div align="center">

# ScaleLab AI

### Distributed Performance Intelligence Platform

**Understand why parallel workloads fail to scale.**

Run benchmarks. Diagnose bottlenecks. Profile execution.  
Forecast scalability limits. Generate optimization recommendations.

*Built for engineers who need to understand **why** systems stop scaling — not just see a speedup number.*

---

[Quick Start](#getting-started) · [Benchmark Packs](#benchmark-packs) · [How It Works](#how-parallelism-works-internally) · [API Reference](#api-reference) · [Architecture](#architecture)

</div>

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Features](#features)
- [Benchmark Packs](#benchmark-packs)
- [Benchmark Quality Scoring](#benchmark-quality-scoring)
- [AI Analysis Engine](#ai-analysis-engine)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [How Parallelism Works Internally](#how-parallelism-works-internally)
- [Running Tests](#running-tests)
- [License](#license)

---

## What It Does

ScaleLab AI answers one question precisely: **how does your code scale, and why?**

You pick a workload, choose an input size and worker count, and the platform:

1. Runs a **sequential baseline** (single worker, same data, same process) to establish ground truth
2. Runs the **same workload across N parallel processes** using fork-based multiprocessing
3. Computes **speedup** (sequential ÷ parallel time), **efficiency** (speedup ÷ workers), and a **benchmark quality score**
4. Samples CPU, memory, disk I/O, and network every 500 ms throughout the entire run
5. Classifies the **performance bottleneck** (CPU-bound, memory-bound, communication-bound, etc.) using a nine-classifier diagnostic engine — no API key required
6. Optionally generates **LLM-powered analysis** explaining results in plain language with ranked optimization recommendations

All metrics are derived from real execution. No hardcoded values. No synthetic results.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Frontend  (React / TypeScript)               │
│                                                                    │
│  BenchmarkPacks   Dashboard   BenchmarkDetail   ResearchMode      │
│  SpeedupChart     EfficiencyChart   ResourceChart                 │
│  AIAnalysisPanel  ExperimentTracker  CustomWorkloads              │
└─────────────────────────────┬────────────────────────────────────┘
                              │  REST / JSON
┌─────────────────────────────▼────────────────────────────────────┐
│                      Backend  (FastAPI / Python)                   │
│                                                                    │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────┐  │
│  │   API Routers    │   │    Services       │   │ AI Providers │  │
│  │  /benchmarks     │   │  BenchmarkSvc     │   │ Mock (local) │  │
│  │  /experiments    │   │  ExperimentSvc    │   │ OpenAI GPT-4 │  │
│  │  /analytics      │   │  AnalyticsSvc     │   │ Anthropic    │  │
│  │  /diagnosis      │   │  CertSvc          │   └──────────────┘  │
│  │  /profiling      │   │  ReportSvc        │                      │
│  │  /certification  │   │  ClusterSvc       │                      │
│  │  /cluster        │   └──────────────────┘                      │
│  │  /benchmark-packs│                                              │
│  │  /custom-workloads│  ┌──────────────────────────────────────┐  │
│  └──────────────────┘  │       Workload Engine                 │  │
│                         │  multiprocessing.Pool (fork context) │  │
│                         │  Module-level shared arrays          │  │
│                         │  Copy-on-write via fork (zero IPC)   │  │
│                         │  Sequential baseline + parallel run  │  │
│                         └──────────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────┐   ┌──────────────────┐   ┌────────────────┐   │
│  │  SQLite / PG   │   │  ResourceSampler  │   │ DiagnosisEngine│   │
│  │  (SQLAlchemy)  │   │  0.5s daemon      │   │ 9 classifiers  │   │
│  └────────────────┘   └──────────────────┘   └────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

**Fork-based multiprocessing** — On macOS and Linux, `multiprocessing.get_context("fork")` is used instead of `spawn`. Fork starts a worker process in ~5 ms vs ~500 ms for spawn. Large input arrays are set as module-level globals before the pool is created; forked workers inherit them via copy-on-write with zero IPC cost.

**Sequential baseline is honest** — The sequential time is measured in the same process, same environment, same data as the parallel run — not a theoretical estimate. The minimum time across iterations is reported to reduce OS scheduling noise.

**Async execution pattern** — Benchmark runs are submitted via `POST /api/benchmarks` (returns 202 immediately) and executed in a background thread. The frontend polls `GET /api/benchmarks/{id}` every 2.5 seconds until `status` becomes `completed` or `failed`.

**Concurrency limit** — A semaphore caps concurrent executions at 4. A run submitted when the semaphore is exhausted fails immediately with a clear error rather than queuing unbounded workers.

**Forward-only schema migration** — The SQLite database auto-migrates on startup via `ALTER TABLE ... ADD COLUMN` for any new columns. No Alembic, no manual steps required for development.

---

## Features

### Benchmark Execution
- Submit any workload with configurable input size, worker count (1–32), and best-of-N iterations
- Background execution with real-time status polling
- Microsecond-precision timing via `time.perf_counter()`
- Results include sequential time, parallel time, speedup, efficiency, peak memory, and CPU usage

### Benchmark Quality Scoring
Every completed run is automatically classified:

| Score | Sequential Runtime | What It Means |
|---|---|---|
| ✅ **Reliable** | ≥ 500 ms | Fork overhead is < 1% of total runtime. Results are trustworthy. |
| ⚠️ **Marginal** | 50–500 ms | Results are directionally correct but may be skewed by fork and cache effects. |
| ❌ **Invalid** | < 50 ms | Fork overhead dominates computation. Speedup figures are meaningless at this size. |

The quality badge and warning appear inline in both the run modal and the detail view. The warning message includes the exact measured runtime in µs or ms so you know precisely how far from threshold you are.

### Resource Observability
- CPU usage sampled system-wide + per-core every 500 ms via a psutil daemon thread
- Memory tracked as both `%` and `MB` peak via `tracemalloc`
- Disk I/O and network I/O delta captured over the run duration
- Full timeline stored for chart rendering (up to 60 data points per run)

### AI Bottleneck Analysis
- Nine-classifier algorithmic diagnosis engine runs against measured metrics without any API key
- Optional deep analysis via OpenAI GPT-4o or Anthropic Claude
- Outputs: bottleneck type, plain-language explanation, `parallel_fraction_estimate`, `theoretical_max_speedup` (Amdahl ceiling), and ranked optimization recommendations
- Confidence level (high / medium / low) reported for every analysis

### Experiment Tracking
- Group related runs into named experiments for systematic comparison
- Scaling study tool: submit one run per worker count `[1, 2, 4, 8]` in a single API call
- Charts: speedup curve, efficiency curve, execution time comparison, resource utilization over time

### Scalability Prediction
- Fits Amdahl or Gustafson models to collected data points using `scipy.optimize.curve_fit`
- R² selects the best-fitting model automatically
- Predicts speedup at untested worker counts with confidence scores
- Knee-detection algorithm identifies the last worker count where marginal speedup gain ≥ 10%

### Scalability Certification
- Issues a structured certification report (grade A–D) for any experiment
- Includes parallel fraction, serial fraction, R², Amdahl ceiling, and best observed speedup
- Exports to Markdown and HTML

### cProfile Flame Graphs
- Optional profiling mode captures `cProfile` hotspots per run
- SVG flame graph generated for visual call-stack analysis

### Custom Workload Support
- Upload arbitrary Python scripts via the UI
- AST-validated before execution (prevents `import os`, `subprocess`, `open`, etc.)
- Must expose a `run(input_size, worker_count)` function
- Supports `multiprocessing`, `concurrent.futures`, `numpy`, and pure Python

### Cluster Monitoring
- Local machine auto-registers as a cluster node on startup
- Tracks CPU model, core count, memory, OS, disk, and heartbeat status
- Foundation for future distributed multi-node execution

---

## Benchmark Packs

Five industry-representative workloads ship out of the box. Each is designed so the dominant CPU cost scales linearly with input size, making parallel speedup clearly observable at the recommended default sizes.

---

### AI Inference Pipeline
**Domain:** ML / AI — RAG systems, LLM serving  
**Bottleneck:** CPU-bound (Gaussian feature enrichment)  
**Scalability Grade:** A

Simulates a four-stage retrieval-augmented generation pipeline:

1. **Embedding Generation** — Parent process generates N × 128-dimensional float32 unit-normalized embedding vectors using a seeded numpy RNG.

2. **Feature Enrichment** — Each worker applies 12 passes of `scipy.ndimage.gaussian_filter1d(σ=1.5)` along the feature axis followed by per-row L2 normalization to its assigned chunk. This simulates transformer attention and layer-norm passes. Dominant cost: **O(N × D × 12)** where D = 128.

3. **Vector Similarity Search** — Enriched embeddings are multiplied by the query vector (`chunk @ query`). Each worker finds its top-50 candidates via `np.argpartition` and returns serialized (indices, scores) bytes.

4. **Cross-Encoder Reranking** — Parent merges candidates from all workers, selects global top-50, re-enriches only those 50 vectors for cross-encoder scoring, and assembles a weighted top-10 response vector.

**Parallelism mechanism:** `_AI_EMBEDDINGS` and `_AI_QUERY` are module-level globals set in the parent before the pool is forked. Workers inherit both arrays via copy-on-write — there is zero IPC cost on the read-only input. Each worker receives only a `(start, end)` index tuple.

| Preset | Sequential Time | Quality |
|---|---|---|
| 50K docs | ~315 ms | Marginal |
| **200K docs (default)** | **~1.2 s** | **Reliable** |
| 500K docs | ~3.0 s | Reliable |
| 1M docs | ~6.0 s | Reliable (large) |

---

### ETL Data Pipeline
**Domain:** Data Engineering — analytics, data warehouses  
**Bottleneck:** Memory-bound (columnar throughput + Python-loop aggregation)  
**Scalability Grade:** B+

Simulates a data-warehouse ETL job over N columnar float32 records (8 fields: amount, quantity, unit_price, discount, tax, user_id, category_id, timestamp_bucket):

1. **Ingestion** — Records are pre-generated in memory using seeded numpy with realistic field ranges.
2. **Transformation** — Revenue computation `(amount × quantity × unit_price) × (1 - discount) × (1 + tax)`, tier classification (low/mid/high), amount normalization within each chunk.
3. **Aggregation** — Group by `(category_id % 20, timestamp_bucket % 24)` → 480 buckets. Per-bucket: count, sum_revenue, mean_revenue, max_revenue. The aggregation inner loop is pure Python dict for realistic memory pressure.
4. **Export** — Serialize group stats to dicts (simulates a write stage).

**Parallelism mechanism:** Each worker processes a row slice and returns `(revenue_bytes, aggregation_json)`. Parent JSON-decodes and merges partial dicts by summing counts and revenues, taking max values.

| Preset | Notes |
|---|---|
| 1M records | Minimum reliable |
| 3M records | Fast default |
| **5M records (default)** | **Reliable** |
| 10M records | Large |

---

### Log Processing Pipeline
**Domain:** Observability / SRE — monitoring, alerting  
**Bottleneck:** Communication-bound (dict merge overhead)  
**Scalability Grade:** B

Simulates high-throughput log analytics over N structured log records (service_id, endpoint_id, status_code, latency_ms, unix_timestamp). Status codes weighted 60% 200, 10% 301, 30% errors.

1. **Parse / Filter** — Identify error records (status ≥ 400) and compute `hour_bucket = timestamp // 3600`.
2. **Group** — By `(service_id, endpoint_id, hour_bucket)` across 16 services × 64 endpoints × 24 hours = up to 24,576 groups.
3. **Aggregate** — Per-group: count, error_count, sum_latency, max_latency, sum_latency_squared (enables P95 approximation via `mean + 2σ` without returning raw arrays).
4. **Incident Ranking** — Top-20 worst endpoints by error rate descending.

**Parallelism mechanism:** Workers return JSON-encoded group aggregation dicts. Parent merges them — this dict merge is the measurable communication cost, which grows with the number of distinct groups. Makes communication-bound behavior visible and educational.

| Preset | Notes |
|---|---|
| 500K lines | Marginal |
| 1M lines | Reliable |
| **2M lines (default)** | **Reliable** |
| 5M lines | Large |

---

### Fraud Detection Pipeline
**Domain:** FinTech / Risk — real-time transaction scoring  
**Bottleneck:** CPU-bound (Gaussian feature enrichment)  
**Scalability Grade:** A

Simulates a financial fraud scoring engine over N transactions (20 features: amount, velocity, geo_dist, merchant_risk, card_age, device score, IP risk, address mismatch flags, etc.):

1. **Feature Enrichment** — 8 passes of `gaussian_filter1d(σ=1.5)` + L2 normalization, simulating preprocessing layers. Dominant cost: **O(N × 30 × 8)**.
2. **Risk Scoring** — 10 pairwise interaction terms computed (e.g., `amount × velocity_1h`, `merchant_risk × ip_risk`), concatenated to form a 30-feature vector, multiplied by pre-trained weights, passed through sigmoid.
3. **Threshold Classification** — Transactions classified as low (< 0.30), medium (0.30–0.70), or high (> 0.70) risk.
4. **Top-K Review Queue** — Global top-100 highest-risk transactions assembled for analyst review.

**Parallelism mechanism:** Workers inherit `_FRAUD_FEATURES` and `_FRAUD_WEIGHTS` via fork. Each enriches and scores its chunk, returns serialized (indices, scores) bytes. Parent assembles global top-100.

| Preset | Notes |
|---|---|
| 200K transactions | Marginal |
| 500K transactions | Reliable |
| **1M transactions (default)** | **Reliable** |
| 5M transactions | Large |

---

### Recommendation Engine
**Domain:** E-Commerce / Personalization — collaborative filtering  
**Bottleneck:** CPU-bound (Gaussian feature enrichment)  
**Scalability Grade:** A-

Simulates a collaborative-filtering recommendation service over N catalog items (64 latent factors each):

1. **Feature Enrichment** — 12 passes of `gaussian_filter1d(σ=1.5)` + L2 normalization on item latent factors, simulating learned feature mixing in embedding layers. Dominant cost: **O(N × D × 12)** where D = 64.
2. **Affinity Scoring** — Enriched item vectors dotted with user profile vector. Multi-factor score: `0.6 × affinity + 0.25 × popularity + 0.15 × recency` where recency = `1 / (1 + log1p(item_age_days))`.
3. **Multi-Factor Ranking** — Workers return top-200 candidates (indices, scores) from their chunk.
4. **MMR Diversity Re-ranking** — Parent merges to global top-200, then applies greedy Maximal Marginal Relevance (λ=0.7) to balance relevance and diversity. Outputs final top-20. This is fast: only 200 × 64 × 12 operations for re-enrichment.

**Parallelism mechanism:** Workers inherit `_RECO_ITEMS`, `_RECO_USER`, `_RECO_POPULARITY`, and `_RECO_RECENCY` via fork. MMR runs in the parent after merge.

| Preset | Notes |
|---|---|
| 100K items | Marginal |
| **300K items (default)** | **Reliable** |
| 1M items | Reliable |
| 3M items | Large |

---

### Classic Workloads (available via Dashboard)

| Workload | Algorithm | Parallelism Strategy | Default Size |
|---|---|---|---|
| **Matrix Multiplication** | Dense matrix multiply A × B | Row-partition A; workers compute slab × B (inherited via fork) | 2048 × 2048 |
| **Parallel Sort** | Sample sort | Quantile-based range partitioning; each worker sorts its range (no merge step) | 5M elements |
| **Image Processing** | Gaussian blur + Sobel edge detection | Horizontal strip decomposition; each worker processes contiguous rows | 2048 × 2048 px |
| **Graph BFS** | Level-synchronous BFS on Erdős–Rényi graph | Frontier expansion parallelized per BFS level; bounded by diameter O(log N) | 100K nodes |

---

## Benchmark Quality Scoring

One of the most common mistakes in parallel benchmarking is running workloads that are too small. When the computation finishes in microseconds but forking processes takes 5–20 ms each, the measured "parallel time" is almost entirely process creation overhead — not real parallel work. The result looks like a speedup of 0.02×, which is not a meaningful measurement.

**Example of the problem:**
```
AI Inference Pipeline — N=1,000 documents
  Sequential:  5,845 µs   ← overhead-dominated
  Parallel:   24,178 µs   ← mostly fork startup cost
  Speedup:     0.24×      ← meaningless
  Quality:  ❌ Invalid
```

**At the correct size:**
```
AI Inference Pipeline — N=200,000 documents
  Sequential:  1.202 s    ← real computation
  Parallel:    0.527 s    ← real speedup
  Speedup:     2.28×      ← trustworthy
  Quality:  ✅ Reliable
```

### Quality Thresholds

```
Sequential Runtime    Score          Badge Color
─────────────────     ─────────      ───────────
≥ 500 ms              Reliable       Green
50 ms – 500 ms        Marginal       Amber
< 50 ms               Invalid        Red
```

The `Marginal` warning message includes the exact sequential runtime: *"Sequential runtime is 315.4 ms — below the 500 ms reliability threshold. Speedup and efficiency figures may be skewed by process-fork overhead and CPU cache warm-up effects."*

The `Invalid` warning tells you exactly what to do: *"Workload too small for reliable scalability analysis. Sequential runtime is 5845 µs — process-fork overhead dominates computation at this size. Increase input size until sequential runtime exceeds 500 ms."*

---

## AI Analysis Engine

### Algorithmic Diagnosis (no API key required)

The built-in diagnosis engine scores nine bottleneck classifiers against measured metrics and produces a primary + optional secondary classification:

| Classifier | Primary Signal |
|---|---|
| `cpu_bound` | CPU utilization > 85% or high efficiency at high CPU |
| `memory_bound` | Memory utilization > 75% or negative scaling pattern |
| `synchronization_bound` | Amdahl serial fraction > 35% and low efficiency |
| `communication_bound` | Net I/O > 20 MB/s or IPC cost visible in serial fraction |
| `load_imbalance` | Per-core CPU variance > 25pp or non-monotone speedup curve |
| `ipc_overhead` | Workers > 4, speedup < 0.5×, low CPU |
| `worker_oversubscription` | Workers > logical CPU count |
| `serialization_bottleneck` | Custom workload with IPC overhead indicators |
| `io_bound` | Disk I/O rate > 20 MB/s |

**Diagnostic strength** = `primary_score − secondary_score`. A value near 1 means unambiguous diagnosis. A value near 0 means two classifiers are tied (co-bottleneck reported).

### Mock AI Provider (default — works offline)

The built-in mock provider uses Amdahl's Law, per-workload parallel fraction estimates, and a curated knowledge base to produce:
- Bottleneck type and plain-language summary
- Speedup explanation with `theoretical_max_speedup` (Amdahl ceiling)
- `parallel_fraction_estimate` derived from measured speedup data
- 3–5 ranked optimization recommendations

No API key. No network request. Works in CI and air-gapped environments.

### OpenAI / Anthropic Integration

Set `AI_PROVIDER=openai` or `AI_PROVIDER=anthropic` in your `.env` to get LLM-generated analysis with richer natural language and deeper architectural insights. The same structured response schema is returned regardless of provider — the frontend does not need to know which provider is active.

---

## Tech Stack

### Backend

| Component | Technology | Version |
|---|---|---|
| Web framework | FastAPI | 0.115 |
| ASGI server | Uvicorn | 0.32 |
| ORM + DB | SQLAlchemy + SQLite | 2.0 |
| Parallelism | Python `multiprocessing` (fork) | stdlib |
| Numerical compute | NumPy | 2.2 |
| Signal processing | SciPy (`gaussian_filter1d`, `curve_fit`) | 1.14 |
| Graph algorithms | NetworkX | 3.4 |
| System metrics | psutil | 6.1 |
| Validation | Pydantic + pydantic-settings | 2.10 |
| AI — Anthropic | anthropic SDK | 0.40 |
| AI — OpenAI | openai SDK | 1.58 |

### Frontend

| Component | Technology | Version |
|---|---|---|
| UI framework | React | 18.3 |
| Language | TypeScript | 5.6 |
| Build tool | Vite | 5.4 |
| Styling | Tailwind CSS | 3.4 |
| Routing | React Router | 6.28 |
| Charts | Recharts | 2.13 |
| Icons | Lucide React | 0.460 |
| HTTP client | Axios | 1.7 |

---

## Project Structure

```
scalelab-ai/
│
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── base.py                  # BaseAIProvider abstract interface
│   │   │   ├── mock_provider.py         # Amdahl's Law local analysis (no API key)
│   │   │   ├── openai_provider.py       # GPT-4o integration
│   │   │   ├── anthropic_provider.py    # Claude integration
│   │   │   ├── scalability_agent.py     # Fits Amdahl/Gustafson models
│   │   │   └── bottleneck_agent.py      # Per-workload bottleneck prompts
│   │   │
│   │   ├── api/
│   │   │   ├── benchmarks.py            # Core CRUD + async execution
│   │   │   ├── benchmark_packs.py       # 5 industry pack metadata
│   │   │   ├── workloads.py             # Workload metadata registry
│   │   │   ├── experiments.py           # Experiment grouping
│   │   │   ├── analytics.py             # Scaling prediction + recommendations
│   │   │   ├── diagnosis.py             # Bottleneck classification
│   │   │   ├── profiling.py             # cProfile + flame graphs
│   │   │   ├── certification.py         # Scalability grade reports
│   │   │   ├── cluster.py               # Node registration + heartbeat
│   │   │   ├── custom_workloads.py      # Upload + execute user Python
│   │   │   └── health.py                # Health check
│   │   │
│   │   ├── diagnosis/
│   │   │   └── engine.py                # 9-classifier bottleneck engine
│   │   │
│   │   ├── models/                      # SQLAlchemy ORM models
│   │   │   ├── benchmark.py             # BenchmarkRun (timing, quality, resources)
│   │   │   ├── experiment.py            # Experiment grouping
│   │   │   ├── cluster_node.py          # Registered compute nodes
│   │   │   └── custom_workload.py       # Uploaded workload metadata
│   │   │
│   │   ├── observability/
│   │   │   └── sampler.py               # Daemon thread CPU/mem/IO sampler
│   │   │
│   │   ├── profiling/
│   │   │   ├── profiler.py              # cProfile integration
│   │   │   └── flame_graph.py           # SVG flame graph generator
│   │   │
│   │   ├── schemas/                     # Pydantic request/response schemas
│   │   │
│   │   ├── services/
│   │   │   ├── benchmark_service.py     # Run lifecycle: create → execute → persist
│   │   │   ├── experiment_service.py    # Experiment CRUD + comparison summaries
│   │   │   ├── ai_analysis_service.py   # Provider dispatch + caching
│   │   │   ├── certification_service.py # Scalability grade computation
│   │   │   ├── recommendation_service.py# Optimal worker count recommendation
│   │   │   ├── report_service.py        # Structured run report generation
│   │   │   └── cluster_service.py       # Node registration + stale detection
│   │   │
│   │   ├── workloads/
│   │   │   ├── base.py                  # BaseWorkload + WorkloadResult + quality scoring
│   │   │   ├── _pool.py                 # fork (Unix) / spawn (Windows) selector
│   │   │   ├── __init__.py              # WORKLOAD_REGISTRY + WORKLOAD_METADATA
│   │   │   ├── ai_inference.py          # RAG pipeline (N × 128-dim, 12 passes)
│   │   │   ├── etl_pipeline.py          # ETL (N × 8 columns, Python-loop aggregation)
│   │   │   ├── log_processing.py        # Log analytics (N records, group-by)
│   │   │   ├── fraud_detection.py       # Fraud scoring (N × 20 features, 8 passes)
│   │   │   ├── recommendation_engine.py # Rec engine (N × 64 factors, 12 passes + MMR)
│   │   │   ├── matrix_multiplication.py # Row-partitioned A × B
│   │   │   ├── parallel_sort.py         # Sample sort (quantile partitioning)
│   │   │   ├── image_processing.py      # Gaussian blur + Sobel (strip decomposition)
│   │   │   └── graph_bfs.py             # Level-synchronous BFS
│   │   │
│   │   ├── config.py                    # Settings via pydantic-settings + .env
│   │   ├── database.py                  # Engine + SessionLocal + auto-migration
│   │   ├── logging_config.py            # Structured JSON logging + request_id propagation
│   │   └── main.py                      # App factory + router registration + startup
│   │
│   ├── tests/
│   │   ├── api/                         # FastAPI TestClient endpoint tests
│   │   ├── unit/                        # Service and workload unit tests
│   │   ├── integration/                 # Real workload execution + chaos tests
│   │   └── validation/                  # Amdahl's Law math + speedup property tests
│   │
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx            # Run form + results table + KPI cards
│       │   ├── BenchmarkPacks.tsx       # 5 pack cards + run modal + comparison mode
│       │   ├── BenchmarkDetail.tsx      # Full result: timing, quality, resources, AI
│       │   ├── ResearchMode.tsx         # Scaling study + experiment charts
│       │   └── CustomWorkloads.tsx      # Upload + validate + run custom Python
│       │
│       ├── components/
│       │   ├── RunForm.tsx              # Workload selector + size presets + submit
│       │   ├── BenchmarkTable.tsx       # Sortable history table
│       │   ├── AIAnalysisPanel.tsx      # Trigger + display AI bottleneck analysis
│       │   ├── RunAnalysisModal.tsx     # Quick analysis overlay from table row
│       │   ├── MetricCard.tsx           # KPI card (speedup, efficiency, time)
│       │   └── StatusBadge.tsx          # pending / running / completed / failed
│       │
│       ├── charts/
│       │   ├── SpeedupChart.tsx         # Speedup vs worker count (+ Amdahl ideal)
│       │   ├── EfficiencyChart.tsx      # Efficiency % vs worker count
│       │   ├── ExecutionTimeChart.tsx   # Parallel vs sequential time comparison
│       │   └── ResourceChart.tsx        # CPU + memory timeline
│       │
│       ├── services/
│       │   └── api.ts                   # Fully typed API client (Axios)
│       │
│       └── types/
│           └── index.ts                 # All TypeScript interfaces
│
└── LICENSE                              # MIT
```

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- `pip`

### 1. Clone

```bash
git clone https://github.com/YashPatel2395/scalelab-ai.git
cd scalelab-ai
```

### 2. Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Optional: configure AI provider (mock works with no API key)
cp .env.example .env

# Start the API server
uvicorn app.main:app --reload --port 8000
```

Backend is live at `http://localhost:8000`  
Interactive API docs: `http://localhost:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend is live at `http://localhost:5173`

### 4. Run your first benchmark

1. Open `http://localhost:5173`
2. Navigate to **Benchmark Packs** in the header
3. Click **Run Benchmark** on **AI Inference Pipeline**
4. Leave the default size (200K) and 4 workers selected
5. Click **Run Benchmark**

Expected output on a modern laptop with 4 workers:

```
Sequential time:  1.202 s
Parallel time:    0.527 s
Speedup:          2.28×
Efficiency:       57.0%
Quality:          ✅ Reliable
```

---

## Configuration

All settings are read from `backend/.env`. Every variable has a sensible default — the platform works fully with an empty `.env` file.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./scalelab.db` | Change to `postgresql://user:pass@host/db` for production |
| `AI_PROVIDER` | `mock` | `mock` · `openai` · `anthropic` |
| `OPENAI_API_KEY` | — | Required only if `AI_PROVIDER=openai` |
| `ANTHROPIC_API_KEY` | — | Required only if `AI_PROVIDER=anthropic` |
| `BACKEND_HOST` | `0.0.0.0` | Bind address |
| `BACKEND_PORT` | `8000` | Port |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `JSON_LOGS` | `false` | Set `true` for structured JSON output in production |

---

## API Reference

All endpoints are documented interactively at `http://localhost:8000/docs`.

### Benchmarks

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/benchmarks` | Submit a run (202, executes in background) |
| `GET` | `/api/benchmarks` | List all runs (`?workload_type=` · `?status=`) |
| `GET` | `/api/benchmarks/{id}` | Full result with quality score and warning |
| `DELETE` | `/api/benchmarks/{id}` | Delete a run |
| `GET` | `/api/benchmarks/stats` | Aggregate stats across all completed runs |
| `POST` | `/api/benchmarks/{id}/analyze` | Trigger AI analysis for a completed run |
| `GET` | `/api/benchmarks/{id}/report` | Structured JSON report |
| `POST` | `/api/benchmarks/scaling-study` | Submit one run per worker count in one call |

**Submit and poll:**

```bash
# Submit
curl -X POST http://localhost:8000/api/benchmarks \
  -H "Content-Type: application/json" \
  -d '{"workload_type":"ai_inference","input_size":200000,"worker_count":4,"iterations":1}'

# Poll (replace <id> with the returned id)
curl http://localhost:8000/api/benchmarks/<id>
```

**Response shape (completed):**
```json
{
  "id": "7bd384df-...",
  "workload_type": "ai_inference",
  "input_size": 200000,
  "worker_count": 4,
  "execution_time": 0.527340,
  "sequential_time": 1.202110,
  "speedup": 2.2796,
  "efficiency": 56.99,
  "quality_score": "Reliable",
  "measurement_warning": null,
  "cpu_usage": 78.3,
  "memory_usage": 61.2,
  "peak_memory_mb": 312.4,
  "status": "completed"
}
```

### Benchmark Packs

```bash
GET /api/benchmark-packs            # list all 5 packs
GET /api/benchmark-packs/ai_inference
```

### Experiments & Scaling Studies

```bash
POST /api/benchmarks/scaling-study
{
  "workload_type": "ai_inference",
  "input_size": 200000,
  "worker_counts": [1, 2, 4, 8],
  "iterations": 1,
  "experiment_name": "AI Inference Scaling"
}
```

### Analytics

```bash
GET /api/analytics/scaling-prediction?workload_type=ai_inference&input_size=200000
GET /api/analytics/recommendation?workload_type=ai_inference&input_size=200000
GET /api/analytics/chart-data?workload_type=ai_inference
```

### Diagnosis

```bash
POST /api/diagnosis/<benchmark_id>
```

---

## How Parallelism Works Internally

Every workload follows the same three-phase execution pattern:

### Phase 1 — Data Generation (parent process)

The parent generates the full input dataset as numpy arrays and assigns them to module-level globals:

```python
# ai_inference.py
_AI_EMBEDDINGS = None   # set before fork
_AI_QUERY = None

# In run():
_AI_EMBEDDINGS = embeddings   # (N, 128) float32 — ~100 MB at N=200K
_AI_QUERY = query             # (128,) float32
```

### Phase 2 — Sequential Baseline (parent process)

```python
seq_times = []
for _ in range(iterations):
    t0 = time.perf_counter()
    _sequential_inference(embeddings, query, N_FEATURE_PASSES)
    seq_times.append(time.perf_counter() - t0)
sequential_time = min(seq_times)   # best-of-N removes scheduling noise
```

### Phase 3 — Parallel Execution (worker pool)

```python
ctx = get_mp_context()   # fork on macOS/Linux, spawn on Windows
tasks = [(start, end, TOP_K, N_PASSES) for start, end in chunks]

with ctx.Pool(processes=worker_count) as pool:
    results = pool.map(_ai_worker, tasks)

parallel_time = min(par_times)
```

Workers inherit `_AI_EMBEDDINGS` and `_AI_QUERY` via copy-on-write. There is no pickling of the input data. Each task tuple is tiny (~32 bytes). Each result is a small byte string (top-K indices + scores).

### Why fork and not spawn?

|  | fork | spawn |
|---|---|---|
| Process startup | ~5 ms | ~500 ms |
| Input data transfer | Zero (copy-on-write) | Full pickle serialization |
| 100 MB array, 4 workers | 0 MB transferred | 400 MB transferred |
| macOS / Linux | Default | Available |
| Windows | Not available | Required |

### Quality Classification

After both timings are recorded, `WorkloadResult.compute_derived()` classifies the result:

```python
if sequential_time < 0.050:      # < 50 ms
    quality_score = "Invalid"
elif sequential_time < 0.500:    # 50–500 ms
    quality_score = "Marginal"
else:                             # ≥ 500 ms
    quality_score = "Reliable"
```

---

## Running Tests

```bash
cd backend
source .venv/bin/activate

# All tests
pytest tests/ -v

# By category
pytest tests/unit/         # pure unit tests — no network, no real workload execution
pytest tests/api/          # FastAPI TestClient with in-memory SQLite
pytest tests/integration/  # real workload execution (small input sizes for speed)
pytest tests/validation/   # mathematical property tests (Amdahl ceiling, speedup monotonicity)

# With coverage
pytest tests/ --cov=app --cov-report=term-missing
```

The test suite uses a session-scoped in-memory SQLite engine and function-scoped transactional sessions that roll back after each test — no state leakage between tests. API tests override the `get_db` dependency via FastAPI's dependency injection.

---

## License

MIT License — see [LICENSE](LICENSE) for full text.

Copyright (c) 2026 Yash Patel
