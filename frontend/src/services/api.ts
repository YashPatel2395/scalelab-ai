import axios from 'axios'
import type {
  BenchmarkRun,
  BenchmarkRunCreate,
  BenchmarkRunSummary,
  AIAnalysis,
  WorkloadMeta,
  SummaryStats,
  Experiment,
  ExperimentCreate,
  ExperimentComparison,
  ClusterSummary,
  ScalabilityPrediction,
  RecommendationResult,
  BottleneckReport,
  MPITiming,
  CustomWorkload,
  CustomWorkloadRunRequest,
  ScalingStudyRequest,
  ScalingStudyResponse,
  DiagnosisResult,
  CertificationReport,
  BenchmarkPack,
} from '../types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const client = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    let message: string
    if (Array.isArray(detail)) {
      // FastAPI Pydantic validation errors: [{loc, msg, type}, ...]
      message = detail
        .map((d: { loc?: string[]; msg?: string }) =>
          d.loc ? `${d.loc.join('.')}: ${d.msg}` : d.msg ?? JSON.stringify(d)
        )
        .join('\n')
    } else {
      message =
        detail ||
        err.response?.data?.message ||
        err.message ||
        'Unknown error'
    }
    return Promise.reject(new Error(message))
  }
)

// ── Workloads ──────────────────────────────────────────────────────────────

export async function fetchWorkloads(): Promise<WorkloadMeta[]> {
  const res = await client.get<{ workloads: WorkloadMeta[] }>('/api/workloads')
  return res.data.workloads
}

// ── Benchmarks ─────────────────────────────────────────────────────────────

export async function submitBenchmark(payload: BenchmarkRunCreate): Promise<BenchmarkRun> {
  const res = await client.post<BenchmarkRun>('/api/benchmarks', payload)
  return res.data
}

export async function fetchBenchmarks(params?: {
  limit?: number
  offset?: number
  workload_type?: string
  status?: string
}): Promise<BenchmarkRunSummary[]> {
  const res = await client.get<BenchmarkRunSummary[]>('/api/benchmarks', { params })
  return res.data
}

export async function fetchBenchmark(id: string): Promise<BenchmarkRun> {
  const res = await client.get<BenchmarkRun>(`/api/benchmarks/${id}`)
  return res.data
}

export async function deleteBenchmark(id: string): Promise<void> {
  await client.delete(`/api/benchmarks/${id}`)
}

export async function fetchStats(): Promise<SummaryStats> {
  const res = await client.get<SummaryStats>('/api/benchmarks/stats')
  return res.data
}

// ── AI Analysis ────────────────────────────────────────────────────────────

export async function analyzeBottleneck(id: string): Promise<AIAnalysis> {
  const res = await client.post<{ benchmark_id: string; analysis: AIAnalysis }>(
    `/api/benchmarks/${id}/analyze`
  )
  return res.data.analysis
}

// ── Report ─────────────────────────────────────────────────────────────────

export async function fetchReport(id: string): Promise<Record<string, unknown>> {
  const res = await client.get(`/api/benchmarks/${id}/report`)
  return res.data
}

// ── Health ─────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<{ status: string; ai_provider: string }> {
  const res = await client.get('/health')
  return res.data
}

// ── Experiments ────────────────────────────────────────────────────────────

export async function fetchExperiments(): Promise<Experiment[]> {
  const res = await client.get<Experiment[]>('/api/experiments')
  return res.data
}

export async function createExperiment(payload: ExperimentCreate): Promise<Experiment> {
  const res = await client.post<Experiment>('/api/experiments', payload)
  return res.data
}

export async function fetchExperiment(id: string): Promise<Experiment> {
  const res = await client.get<Experiment>(`/api/experiments/${id}`)
  return res.data
}

export async function addRunsToExperiment(
  experimentId: string,
  runIds: string[]
): Promise<Experiment> {
  const res = await client.post<Experiment>(`/api/experiments/${experimentId}/runs`, {
    run_ids: runIds,
  })
  return res.data
}

export async function compareExperiment(id: string): Promise<ExperimentComparison> {
  const res = await client.get<ExperimentComparison>(`/api/experiments/${id}/compare`)
  return res.data
}

export async function deleteExperiment(id: string): Promise<void> {
  await client.delete(`/api/experiments/${id}`)
}

// ── Cluster ────────────────────────────────────────────────────────────────

export async function fetchCluster(): Promise<ClusterSummary> {
  const res = await client.get<ClusterSummary>('/api/cluster')
  return res.data
}

// ── Analytics ──────────────────────────────────────────────────────────────

export async function predictScalability(
  workload_type: string,
  input_size: number,
  target_worker_counts?: number[]
): Promise<ScalabilityPrediction> {
  const res = await client.post<ScalabilityPrediction>('/api/analytics/predict', {
    workload_type,
    input_size,
    target_worker_counts: target_worker_counts ?? [1, 2, 4, 8, 16],
  })
  return res.data
}

export async function recommendWorkers(
  workload_type: string,
  input_size: number,
  available_workers?: number
): Promise<RecommendationResult> {
  const res = await client.post<RecommendationResult>('/api/analytics/recommend', {
    workload_type,
    input_size,
    available_workers: available_workers ?? 32,
  })
  return res.data
}

export async function fetchBottleneckReport(benchmarkId: string): Promise<BottleneckReport> {
  const res = await client.get<BottleneckReport>(`/api/analytics/bottleneck/${benchmarkId}`)
  return res.data
}

export async function fetchMPITiming(
  n_processes: number,
  matrix_size: number
): Promise<MPITiming> {
  const res = await client.get<MPITiming>('/api/analytics/mpi', {
    params: { n_processes, matrix_size },
  })
  return res.data
}

// ── Custom Workloads ────────────────────────────────────────────────────────

export async function uploadCustomWorkload(
  name: string,
  file: File
): Promise<CustomWorkload> {
  const form = new FormData()
  form.append('name', name)
  form.append('file', file)
  // Do NOT set Content-Type manually. The axios client defaults to
  // 'application/json', which would send multipart without a boundary.
  // Setting it to undefined removes the default so that the browser's
  // XMLHttpRequest sets 'multipart/form-data; boundary=----...' correctly.
  const res = await client.post<CustomWorkload>('/api/custom-workloads/upload', form, {
    headers: { 'Content-Type': undefined },
  })
  return res.data
}

export async function fetchCustomWorkloads(): Promise<CustomWorkload[]> {
  const res = await client.get<CustomWorkload[]>('/api/custom-workloads')
  return res.data
}

export async function fetchCustomWorkload(id: string): Promise<CustomWorkload> {
  const res = await client.get<CustomWorkload>(`/api/custom-workloads/${id}`)
  return res.data
}

export async function runCustomWorkload(
  id: string,
  payload: CustomWorkloadRunRequest
): Promise<BenchmarkRun> {
  const res = await client.post<BenchmarkRun>(
    `/api/custom-workloads/${id}/run`,
    payload,
    { timeout: 10_000 }  // just waits for the 202, not for execution
  )
  return res.data
}

export async function deleteCustomWorkload(id: string): Promise<void> {
  await client.delete(`/api/custom-workloads/${id}`)
}

// ── Scaling Study ───────────────────────────────────────────────────────────

export async function createScalingStudy(
  payload: ScalingStudyRequest
): Promise<ScalingStudyResponse> {
  const res = await client.post<ScalingStudyResponse>(
    '/api/benchmarks/scaling-study',
    payload
  )
  return res.data
}

// ── Diagnosis ───────────────────────────────────────────────────────────────

export async function getDiagnosis(runId: string): Promise<DiagnosisResult> {
  const res = await client.get<DiagnosisResult>(`/api/diagnosis/${runId}`)
  return res.data
}

// ── Profiling ────────────────────────────────────────────────────────────────

export async function profileRun(runId: string): Promise<{ success: boolean; hotspot_count: number }> {
  const res = await client.post(`/api/profiling/${runId}`)
  return res.data
}

export async function getProfile(runId: string): Promise<Record<string, unknown>> {
  const res = await client.get(`/api/profiling/${runId}`)
  return res.data
}

export async function getFlameGraph(runId: string): Promise<string> {
  const res = await client.get<string>(`/api/profiling/${runId}/flame-graph`, {
    responseType: 'text',
    headers: { Accept: 'image/svg+xml' },
    transformResponse: [(data: string) => data],
  })
  return res.data
}

// ── Benchmark Packs ───────────────────────────────────────────────────────────

export async function fetchBenchmarkPacks(): Promise<BenchmarkPack[]> {
  const res = await client.get<BenchmarkPack[]>('/api/benchmark-packs')
  return res.data
}

export async function getBenchmarkPack(id: string): Promise<BenchmarkPack> {
  const res = await client.get<BenchmarkPack>(`/api/benchmark-packs/${id}`)
  return res.data
}

// ── Certification ─────────────────────────────────────────────────────────────

export async function generateCertification(
  runIds: string[],
  workloadDisplayName?: string
): Promise<CertificationReport> {
  const res = await client.post<CertificationReport>('/api/certification', {
    run_ids: runIds,
    workload_display_name: workloadDisplayName,
  })
  return res.data
}
