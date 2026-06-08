export type BenchmarkStatus = 'pending' | 'running' | 'completed' | 'failed'

export type WorkloadType =
  | 'matrix_multiplication'
  | 'parallel_sort'
  | 'image_processing'
  | 'graph_bfs'
  | 'custom_python'

export interface BenchmarkRun {
  id: string
  workload_type: WorkloadType
  workload_name: string | null
  input_size: number
  worker_count: number
  iterations: number
  execution_time: number | null
  sequential_time: number | null
  speedup: number | null
  efficiency: number | null
  cpu_usage: number | null
  memory_usage: number | null
  peak_memory_mb: number | null
  quality_score: string | null
  measurement_warning: string | null
  status: BenchmarkStatus
  error_message: string | null
  ai_analysis: AIAnalysis | null
  observability_data: Record<string, unknown> | null
  profiling_data: Record<string, unknown> | null
  flame_graph_svg: string | null
  created_at: string
  completed_at: string | null
}

export interface BenchmarkRunSummary {
  id: string
  workload_type: WorkloadType
  workload_name: string | null
  input_size: number
  worker_count: number
  execution_time: number | null
  speedup: number | null
  efficiency: number | null
  cpu_usage: number | null
  memory_usage: number | null
  status: BenchmarkStatus
  created_at: string
}

export interface BenchmarkRunCreate {
  workload_type: WorkloadType
  input_size: number
  worker_count: number
  iterations: number
}

export interface AIAnalysis {
  bottleneck_type: 'cpu_bound' | 'memory_bound' | 'communication_bound' | 'well_balanced' | 'unknown'
  bottleneck_summary: string
  speedup_explanation: string
  bottleneck_details: string
  optimization_recommendations: string[]
  complexity_interpretation: string
  theoretical_max_speedup: number | null
  parallel_fraction_estimate: number | null
  confidence: 'high' | 'medium' | 'low'
  provider: string
  model: string
}

export interface WorkloadMeta {
  id: string
  name: string
  description: string
  input_label: string
  default_size: number
  size_presets: number[]
  complexity: string
  min_recommended_size?: number
  size_warning?: string
}

// ── Custom Workloads ────────────────────────────────────────────────────────

export type CustomWorkloadValidationStatus = 'pending' | 'passed' | 'failed'

export interface CustomWorkload {
  id: string
  name: string
  filename: string
  status: string
  validation_status: CustomWorkloadValidationStatus
  validation_errors: string[] | null
  validation_warnings: string[] | null
  created_at: string
}

export interface CustomWorkloadRunRequest {
  input_size: number
  worker_count: number
  iterations?: number
  timeout_seconds?: number
  enable_profiling?: boolean
}

export interface CustomWorkloadRunResult {
  custom_workload_id: string
  workload_name: string
  input_size: number
  worker_count: number
  success: boolean
  sequential_time: number | null
  execution_time: number | null
  speedup: number | null
  efficiency: number | null
  stdout: string | null
  error: string | null
  return_value: unknown
}

export interface ScalingStudyRequest {
  workload_type: string
  input_size: number
  worker_counts?: number[]
  iterations?: number
  experiment_name?: string
}

export interface ScalingStudyResponse {
  experiment_id: string
  experiment_name: string
  run_ids: string[]
  workload_type: string
  input_size: number
  worker_counts: number[]
  message: string
}

export interface SummaryStats {
  total_runs: number
  completed_runs: number
  failed_runs: number
  best_speedup: number
  average_efficiency: number
  most_expensive_workload: string | null
  most_expensive_time: number | null
}

export interface ChartPoint {
  worker_count: number
  speedup: number | null
  efficiency: number | null
  execution_time: number | null
  cpu_usage: number | null
  memory_usage: number | null
  workload_type: string
}

export interface ObservabilityData {
  cpu_avg: number
  cpu_peak: number
  cpu_per_core_avg: number[]
  memory_avg_pct: number
  memory_peak_pct: number
  memory_peak_mb: number
  disk_read_mb: number
  disk_write_mb: number
  net_sent_mb: number
  net_recv_mb: number
  sample_count: number
  duration_seconds: number
  timeline: Array<{ t: number; cpu: number; mem: number }>
}

// ── Experiment Tracking ─────────────────────────────────────────────────────

export interface Experiment {
  id: string
  name: string
  description: string | null
  workload_type: string | null
  tags: string[] | null
  run_ids: string[]
  created_at: string
  updated_at: string
}

export interface ExperimentCreate {
  name: string
  description?: string
  workload_type?: string
  tags?: string[]
}

export interface ExperimentComparison {
  experiment_id: string
  experiment_name: string
  runs: Array<{
    id: string
    workload_type: string
    input_size: number
    worker_count: number
    execution_time: number | null
    sequential_time: number | null
    speedup: number | null
    efficiency: number | null
    cpu_usage: number | null
    memory_usage: number | null
    peak_memory_mb: number | null
    status: string
    created_at: string
  }>
  summary: {
    total_runs: number
    completed_runs: number
    best_speedup?: number
    avg_speedup?: number
    avg_efficiency?: number
    best_run_id?: string
    best_run_workers?: number
  }
}

// ── Cluster ─────────────────────────────────────────────────────────────────

export interface ClusterNode {
  id: string
  hostname: string
  ip_address: string
  cpu_count: number
  cpu_model: string | null
  total_memory_gb: number
  disk_total_gb: number | null
  os_info: string | null
  is_local: boolean
  status: 'online' | 'offline' | 'degraded'
  last_heartbeat: string | null
  current_cpu_pct: number | null
  current_mem_pct: number | null
  metadata_json: Record<string, unknown> | null
  registered_at: string
}

export interface ClusterSummary {
  total_nodes: number
  online_nodes: number
  offline_nodes: number
  degraded_nodes: number
  total_cpu_cores: number
  total_memory_gb: number
  nodes: ClusterNode[]
}

// ── Scalability Prediction ──────────────────────────────────────────────────

export interface ScalabilityPrediction {
  workload_type: string
  input_size: number
  model_used: 'amdahl' | 'gustafson' | 'insufficient_data'
  parallel_fraction: number | null
  serial_overhead: number | null
  r_squared: number | null
  data_points_used: number
  predictions: Array<{
    worker_count: number
    predicted_speedup: number
    predicted_efficiency: number
    confidence: number
  }>
  theoretical_max_speedup: number | null
  recommendation: string
}

// ── Recommendation ──────────────────────────────────────────────────────────

export interface RecommendationResult {
  workload_type: string
  input_size: number
  optimal_worker_count: number
  expected_speedup: number
  expected_efficiency: number
  reasoning: string
  alternative_counts: Array<{
    workers: number
    speedup: number
    efficiency: number
  }>
  data_points_used: number
}

// ── Bottleneck Report ───────────────────────────────────────────────────────

export interface BottleneckReport {
  benchmark_id: string
  bottleneck_type: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  severity_score: number
  root_cause: string
  evidence: string[]
  recommendations: string[]
  estimated_max_improvement: number
}

// ── MPI Timing ──────────────────────────────────────────────────────────────

export interface MPITiming {
  n_processes: number
  matrix_size: number
  computation_time: number
  communication_time: number
  synchronization_time: number
  total_time: number
  mpi_available: boolean
  breakdown_pct: {
    computation: number
    communication: number
    synchronization: number
  }
}

// ── Diagnosis ───────────────────────────────────────────────────────────────

export interface DiagnosisResult {
  primary_bottleneck: string
  diagnostic_strength: number          // absolute margin between primary and secondary score [0,1]
  evidence: Array<{ metric: string; value: string }>
  secondary_bottleneck: string | null
  secondary_evidence_strength: number | null   // raw score of secondary classifier [0,1]
  all_scores: Record<string, number>
  optimization_opportunities: string[]
  expected_improvement_pct: number
  risk_assessment: string
  executive_summary: string
}

// ── Benchmark Packs ──────────────────────────────────────────────────────────

export interface BenchmarkPack {
  id: string
  name: string
  subtitle: string
  domain: string
  domain_tag: string
  workload_type: string
  stages: string[]
  expected_bottleneck: string
  expected_bottleneck_label: string
  scalability_grade: string
  estimated_runtime_s: number
  default_input_size: number
  input_label: string
  size_presets: number[]
  tags: string[]
  color: string
}

// ── Certification ────────────────────────────────────────────────────────────

export interface CertificationReport {
  workload_name: string
  workload_type: string
  input_size: number
  benchmark_date: string
  generated_at: string
  run_ids: string[]
  worker_counts_tested: number[]
  scaling_data: Array<{
    worker_count: number
    execution_time_s: number
    speedup: number
    efficiency_pct: number
    benchmark_id: string
  }>
  analysis: {
    parallel_fraction: number | null
    serial_fraction: number | null
    best_speedup: number
    best_efficiency_pct: number
    theoretical_ceiling: number | null
    amdahl_ceiling_note: string
    model_fit: string | null
    r_squared: number | null
    speedup_degraded: boolean
  }
  diagnosis: {
    primary_bottleneck: string
    diagnostic_strength_pct: number
    secondary_bottleneck: string | null
    evidence: Array<{ metric: string; value: string }>
    executive_summary: string
  }
  certification: {
    grade: string
    rationale: string
    grade_description: string
  }
  recommendations: {
    optimal_worker_count: number
    max_useful_worker_count: number | null
    expected_scaling_limit: string
    optimization_priorities: string[]
    expected_improvement_pct: number
  }
  export_markdown: string
  export_html: string
}
