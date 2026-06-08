import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Activity,
  FileText, Loader2, AlertTriangle, ShieldCheck, ShieldAlert, ShieldX,
} from 'lucide-react'
import Header from '../components/Header'
import StatusBadge from '../components/StatusBadge'
import AIAnalysisPanel from '../components/AIAnalysisPanel'
import RunAnalysisModal from '../components/RunAnalysisModal'
import { fetchBenchmark, fetchReport } from '../services/api'
import type { BenchmarkRun, AIAnalysis, BenchmarkRunSummary } from '../types'

const WORKLOAD_LABELS: Record<string, string> = {
  matrix_multiplication: 'Distributed Matrix Multiplication',
  parallel_sort: 'Parallel Chunk Sort',
  image_processing: 'Parallel Image Processing',
  graph_bfs: 'Graph BFS Traversal',
}

function getDisplayName(run: BenchmarkRun): string {
  if (run.workload_name && run.workload_type === 'custom_python') return run.workload_name
  if (run.workload_name) return run.workload_name
  return WORKLOAD_LABELS[run.workload_type] ?? run.workload_type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function MetricRow({ label, value, unit, mono = false }: {
  label: string; value: React.ReactNode; unit?: string; mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-slate-800">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-sm text-slate-200 ${mono ? 'font-mono' : ''}`}>
        {value}{unit && <span className="text-slate-500 text-xs ml-1">{unit}</span>}
      </span>
    </div>
  )
}

const POLL_MS = 2500

export default function BenchmarkDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [run, setRun] = useState<BenchmarkRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [analysisModalOpen, setAnalysisModalOpen] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    try {
      const data = await fetchBenchmark(id)
      setRun(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load benchmark')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // Poll while running/pending
  useEffect(() => {
    if (!run || run.status === 'completed' || run.status === 'failed') return
    const t = setInterval(() => load(), POLL_MS)
    return () => clearInterval(t)
  }, [run, load])

  const handleAnalysisComplete = (analysis: AIAnalysis) => {
    setRun((prev) => prev ? { ...prev, ai_analysis: analysis } : prev)
  }

  const loadReport = async () => {
    if (!id) return
    setReportLoading(true)
    try {
      const r = await fetchReport(id)
      setReport(r)
      setReportOpen(true)
    } catch { /* ignore */ } finally {
      setReportLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#030712]">
        <Header />
        <div className="flex items-center justify-center pt-32">
          <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
        </div>
      </div>
    )
  }

  if (error || !run) {
    return (
      <div className="min-h-screen bg-[#030712]">
        <Header />
        <div className="max-w-3xl mx-auto px-6 pt-16 text-center">
          <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-3" />
          <p className="text-slate-300 text-sm">{error ?? 'Benchmark not found'}</p>
          <button onClick={() => navigate('/')} className="btn-secondary mt-4">
            <ArrowLeft className="w-4 h-4" /> Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  const effColor =
    run.efficiency == null
      ? 'text-slate-600'
      : run.efficiency >= 80
      ? 'text-emerald-400'
      : run.efficiency >= 50
      ? 'text-amber-400'
      : 'text-red-400'

  const qualityIcon =
    run.quality_score === 'Reliable' ? <ShieldCheck className="w-3.5 h-3.5" /> :
    run.quality_score === 'Marginal' ? <ShieldAlert className="w-3.5 h-3.5" /> :
    run.quality_score === 'Invalid'  ? <ShieldX className="w-3.5 h-3.5" /> :
    null

  const qualityColor =
    run.quality_score === 'Reliable' ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' :
    run.quality_score === 'Marginal' ? 'text-amber-400 bg-amber-500/10 border-amber-500/30' :
    run.quality_score === 'Invalid'  ? 'text-red-400 bg-red-500/10 border-red-500/30' :
    'text-slate-500 bg-slate-800 border-slate-700'

  function fmtTime(s: number): string {
    const ms = s * 1000
    if (ms >= 1000) return `${(ms / 1000).toFixed(3)}s`
    if (ms >= 1) return `${ms.toFixed(3)}ms`
    const us = s * 1_000_000
    if (us >= 1) return `${us.toFixed(1)}µs`
    return '< 1µs'
  }

  return (
    <div className="min-h-screen bg-[#030712]">
      <Header />

      <main className="max-w-screen-xl mx-auto px-6 py-8 space-y-6">
        {/* Back + heading */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="btn-secondary py-1.5 px-3"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Dashboard
          </button>
          <div>
            <h1 className="text-slate-100 font-bold text-lg">
              {getDisplayName(run)}
            </h1>
            <p className="text-slate-500 text-xs font-mono">{run.id}</p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <StatusBadge status={run.status} size="md" />
            {run.status === 'completed' && (
              <button
                onClick={() => setAnalysisModalOpen(true)}
                className="btn-primary py-1.5 px-3 text-xs"
              >
                <Activity className="w-3.5 h-3.5" />
                View Analysis
              </button>
            )}
            {run.status === 'completed' && (
              <button
                onClick={loadReport}
                disabled={reportLoading}
                className="btn-secondary py-1.5 px-3 text-xs"
              >
                {reportLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <FileText className="w-3.5 h-3.5" />
                )}
                Report
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Left: metrics */}
          <div className="xl:col-span-1 space-y-4">
            {/* Configuration */}
            <div className="card p-5">
              <h2 className="text-slate-100 text-sm font-semibold mb-3">Configuration</h2>
              <MetricRow label="Workload" value={getDisplayName(run)} />
              <MetricRow label="Input Size" value={run.input_size.toLocaleString()} mono />
              <MetricRow label="Worker Count" value={run.worker_count} mono />
              <MetricRow label="Iterations" value={run.iterations} mono />
              <MetricRow
                label="Submitted"
                value={new Date(run.created_at).toLocaleString()}
                mono
              />
              {run.completed_at && (
                <MetricRow
                  label="Completed"
                  value={new Date(run.completed_at).toLocaleString()}
                  mono
                />
              )}
            </div>

            {/* Performance */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-slate-100 text-sm font-semibold">Performance Metrics</h2>
                {run.quality_score && run.quality_score !== 'Unknown' && (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium ${qualityColor}`}>
                    {qualityIcon}
                    {run.quality_score}
                  </span>
                )}
              </div>
              {run.measurement_warning && (
                <div className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-xs mb-3 ${
                  run.quality_score === 'Invalid'
                    ? 'bg-red-950/40 border-red-500/30 text-red-400'
                    : 'bg-amber-950/40 border-amber-500/30 text-amber-400'
                }`}>
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  {run.measurement_warning}
                </div>
              )}
              <MetricRow
                label="Parallel Time"
                value={run.execution_time != null ? fmtTime(run.execution_time) : '—'}
                mono
              />
              <MetricRow
                label="Sequential Baseline"
                value={run.sequential_time != null ? fmtTime(run.sequential_time) : '—'}
                mono
              />
              <MetricRow
                label="Speedup"
                value={
                  run.speedup != null ? (
                    <span className="text-cyan-400 font-mono">{run.speedup.toFixed(3)}×</span>
                  ) : '—'
                }
              />
              <MetricRow
                label="Efficiency"
                value={
                  run.efficiency != null ? (
                    <span className={effColor}>{run.efficiency.toFixed(2)}%</span>
                  ) : '—'
                }
              />
            </div>

            {/* Resources */}
            <div className="card p-5">
              <h2 className="text-slate-100 text-sm font-semibold mb-3">Resource Utilization</h2>
              <MetricRow label="CPU Usage" value={run.cpu_usage != null ? `${run.cpu_usage.toFixed(1)}%` : '—'} mono />
              <MetricRow label="Memory %" value={run.memory_usage != null ? `${run.memory_usage.toFixed(1)}%` : '—'} mono />
              <MetricRow label="Peak Memory" value={run.peak_memory_mb != null ? `${run.peak_memory_mb.toFixed(1)} MB` : '—'} mono />
            </div>

            {/* Error */}
            {run.error_message && (
              <div className="card p-5 border-red-900">
                <h2 className="text-red-400 text-sm font-semibold mb-2 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" /> Error
                </h2>
                <pre className="text-xs text-red-300 overflow-auto max-h-48 leading-relaxed whitespace-pre-wrap">
                  {run.error_message}
                </pre>
              </div>
            )}

            {/* Running indicator */}
            {(run.status === 'running' || run.status === 'pending') && (
              <div className="card p-4 border-blue-900 bg-blue-950/30 flex items-center gap-3">
                <Loader2 className="w-4 h-4 animate-spin text-blue-400 flex-shrink-0" />
                <span className="text-blue-400 text-xs">
                  {run.status === 'running' ? 'Executing workload…' : 'Queued, waiting to start…'}
                </span>
              </div>
            )}
          </div>

          {/* Right: AI analysis */}
          <div className="xl:col-span-2">
            <AIAnalysisPanel
              benchmarkId={run.id}
              existingAnalysis={run.ai_analysis}
              benchmarkStatus={run.status}
              onAnalysisComplete={handleAnalysisComplete}
            />
          </div>
        </div>

        {/* Analysis modal */}
        {analysisModalOpen && (
          <RunAnalysisModal
            runSummary={run as unknown as BenchmarkRunSummary}
            onClose={() => setAnalysisModalOpen(false)}
          />
        )}

        {/* Report modal */}
        {reportOpen && report && (
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setReportOpen(false)}
          >
            <div
              className="card max-w-2xl w-full max-h-[80vh] overflow-auto p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-slate-100 font-semibold">Benchmark Report</h2>
                <button onClick={() => setReportOpen(false)} className="text-slate-500 hover:text-slate-300 text-xs">
                  Close
                </button>
              </div>
              <pre className="text-xs text-slate-400 leading-relaxed overflow-auto font-mono whitespace-pre-wrap">
                {JSON.stringify(report, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
