/**
 * RunAnalysisModal
 * ─────────────────
 * Full-screen overlay with four tabs for a single benchmark run:
 *   Overview  · Diagnosis  · Profiling  · Certification
 */

import { useState, useEffect, useCallback, Component } from 'react'
import type { ReactNode } from 'react'
import {
  X, Cpu, MemoryStick, Clock, TrendingUp, BarChart2,
  Loader2, AlertTriangle, Activity, FlaskConical,
  Award, Download, Flame, ChevronRight, Zap, CheckCircle,
  Shield, Target, ChevronDown, ChevronUp, Info,
} from 'lucide-react'
import {
  getDiagnosis, getProfile, profileRun, getFlameGraph,
  generateCertification, fetchBenchmark,
} from '../services/api'
import type { BenchmarkRunSummary, BenchmarkRun, DiagnosisResult, CertificationReport } from '../types'
import StatusBadge from './StatusBadge'

// ── Constants ─────────────────────────────────────────────────────────────────

const WORKLOAD_LABELS: Record<string, string> = {
  matrix_multiplication: 'Matrix Multiplication',
  parallel_sort: 'Parallel Sort',
  image_processing: 'Image Processing',
  graph_bfs: 'Graph BFS',
}

function getWorkloadDisplayName(workloadType: string, workloadName?: string | null): string {
  if (workloadName && workloadType === 'custom_python') return workloadName
  if (workloadName) return workloadName
  return WORKLOAD_LABELS[workloadType] ?? workloadType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const BOTTLENECK_LABELS: Record<string, string> = {
  cpu_bound: 'CPU-Bound',
  memory_bound: 'Memory-Bound',
  synchronization_bound: 'Synchronization-Bound',
  communication_bound: 'Communication-Bound',
  load_imbalance: 'Load-Imbalanced',
  ipc_overhead: 'IPC-Overhead',
  worker_oversubscription: 'Worker-Oversubscribed',
  serialization_bottleneck: 'Serialization-Bottleneck',
  io_bound: 'I/O-Bound',
  well_balanced: 'Well-Balanced',
}

const BOTTLENECK_COLORS: Record<string, string> = {
  cpu_bound: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
  memory_bound: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
  synchronization_bound: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  communication_bound: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  load_imbalance: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  ipc_overhead: 'text-red-400 bg-red-500/10 border-red-500/30',
  worker_oversubscription: 'text-pink-400 bg-pink-500/10 border-pink-500/30',
  serialization_bottleneck: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
  io_bound: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  well_balanced: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
}

const GRADE_COLORS: Record<string, string> = {
  'A+': 'text-emerald-400 border-emerald-400',
  'A': 'text-emerald-400 border-emerald-400',
  'B': 'text-cyan-400 border-cyan-400',
  'C': 'text-amber-400 border-amber-400',
  'D': 'text-orange-400 border-orange-400',
  'F': 'text-red-400 border-red-400',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportCertificatePDF(htmlContent: string, filename: string) {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import('html2canvas'),
    import('jspdf'),
  ])

  // Use an iframe so the full document (including <head><style>) renders correctly.
  // Injecting into a div.innerHTML strips the <style> block → unstyled → 90+ pages.
  const iframe = document.createElement('iframe')
  iframe.style.cssText = 'position:fixed;left:-9999px;top:0;width:860px;height:1px;border:none'
  document.body.appendChild(iframe)

  const doc = iframe.contentDocument!
  doc.open(); doc.write(htmlContent); doc.close()

  // Wait for layout, then size iframe to actual content height
  await new Promise(r => setTimeout(r, 250))
  const contentH = doc.body.scrollHeight
  iframe.style.height = contentH + 'px'
  await new Promise(r => setTimeout(r, 100))

  const canvas = await html2canvas(doc.body, {
    scale: 2,
    useCORS: true,
    backgroundColor: '#f8fafc',
    width: 860,
    height: contentH,
    windowWidth: 860,
    windowHeight: contentH,
  })
  document.body.removeChild(iframe)

  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
  const pageW = pdf.internal.pageSize.getWidth()
  const pageH = pdf.internal.pageSize.getHeight()
  const imgData = canvas.toDataURL('image/png')
  const imgW = pageW
  const imgH = (canvas.height * imgW) / canvas.width

  let y = 0
  while (y < imgH) {
    if (y > 0) pdf.addPage()
    pdf.addImage(imgData, 'PNG', 0, -y, imgW, imgH)
    y += pageH
  }
  pdf.save(filename)
}

function MetricRow({ label, value, mono = false }: {
  label: string; value: React.ReactNode; mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-800">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-sm text-slate-200 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

// ── Error Boundary ────────────────────────────────────────────────────────────

interface EBState { error: Error | null }

class AnalysisErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error): EBState {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-8 text-center space-y-3">
          <div className="w-10 h-10 rounded-full bg-red-950/50 border border-red-800 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-5 h-5 text-red-400" />
          </div>
          <p className="text-red-400 font-medium text-sm">Analysis panel crashed</p>
          <p className="text-red-300/70 text-xs max-w-sm mx-auto font-mono">
            {this.state.error.message}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            className="btn-secondary text-xs py-1.5 px-3 mx-auto"
          >
            Dismiss
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  runSummary: BenchmarkRunSummary
  onClose: () => void
}

type Tab = 'overview' | 'diagnosis' | 'profiling' | 'certification'

// ── Main component ────────────────────────────────────────────────────────────

export default function RunAnalysisModal({ runSummary, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('overview')
  const [run, setRun] = useState<BenchmarkRun | null>(null)
  const [runLoading, setRunLoading] = useState(true)

  // Fetch full run on mount
  useEffect(() => {
    fetchBenchmark(runSummary.id)
      .then(setRun)
      .catch(() => {})
      .finally(() => setRunLoading(false))
  }, [runSummary.id])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const displayName = getWorkloadDisplayName(runSummary.workload_type, runSummary.workload_name)

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <BarChart2 className="w-3.5 h-3.5" /> },
    { id: 'diagnosis', label: 'Diagnosis', icon: <Activity className="w-3.5 h-3.5" /> },
    { id: 'profiling', label: 'Profiling', icon: <Flame className="w-3.5 h-3.5" /> },
    { id: 'certification', label: 'Certification', icon: <Award className="w-3.5 h-3.5" /> },
  ]

  return (
    <div
      className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div>
              <h2 className="text-slate-100 font-semibold">{displayName}</h2>
              <p className="text-slate-500 text-xs font-mono mt-0.5">{runSummary.id}</p>
            </div>
            <StatusBadge status={runSummary.status} />
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 transition-colors p-1 rounded hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 px-6 py-2 border-b border-slate-800 flex-shrink-0">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === t.id
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          <AnalysisErrorBoundary>
            {tab === 'overview' && (
              <OverviewTab run={run} runSummary={runSummary} loading={runLoading} />
            )}
            {tab === 'diagnosis' && (
              <DiagnosisTab runId={runSummary.id} status={runSummary.status} />
            )}
            {tab === 'profiling' && (
              <ProfilingTab
                runId={runSummary.id}
                status={runSummary.status}
                workloadType={runSummary.workload_type}
              />
            )}
            {tab === 'certification' && (
              <CertificationTab
                runId={runSummary.id}
                displayName={displayName}
                status={runSummary.status}
              />
            )}
          </AnalysisErrorBoundary>
        </div>
      </div>
    </div>
  )
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({
  run, runSummary, loading,
}: {
  run: BenchmarkRun | null
  runSummary: BenchmarkRunSummary
  loading: boolean
}) {
  const effColor = (eff?: number | null) =>
    eff == null ? 'text-slate-600'
      : eff >= 80 ? 'text-emerald-400'
      : eff >= 50 ? 'text-amber-400'
      : 'text-red-400'

  if (loading) {
    return (
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="bg-slate-800 rounded-lg p-4 space-y-3 animate-pulse">
            <div className="h-4 bg-slate-700 rounded w-1/3" />
            {[...Array(4)].map((_, j) => (
              <div key={j} className="h-3 bg-slate-700 rounded" />
            ))}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Configuration */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
        <h3 className="text-slate-300 text-xs font-semibold uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-cyan-400" /> Configuration
        </h3>
        <MetricRow label="Workload Type" value={runSummary.workload_type.replace(/_/g, ' ')} />
        <MetricRow label="Input Size" value={runSummary.input_size.toLocaleString()} mono />
        <MetricRow label="Worker Count" value={runSummary.worker_count} mono />
        <MetricRow label="Iterations" value={run?.iterations ?? '—'} mono />
        <MetricRow label="Submitted" value={new Date(runSummary.created_at).toLocaleString()} mono />
        {run?.completed_at && (
          <MetricRow label="Completed" value={new Date(run.completed_at).toLocaleString()} mono />
        )}
      </div>

      {/* Performance */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
        <h3 className="text-slate-300 text-xs font-semibold uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <TrendingUp className="w-3.5 h-3.5 text-blue-400" /> Performance
        </h3>
        <MetricRow
          label="Parallel Time"
          value={
            runSummary.execution_time != null
              ? <span className="font-mono">{runSummary.execution_time.toFixed(4)}s</span>
              : '—'
          }
        />
        <MetricRow
          label="Sequential Baseline"
          value={
            run?.sequential_time != null
              ? <span className="font-mono">{run.sequential_time.toFixed(4)}s</span>
              : '—'
          }
        />
        <MetricRow
          label="Speedup"
          value={
            runSummary.speedup != null
              ? <span className="text-cyan-400 font-mono">{runSummary.speedup.toFixed(3)}×</span>
              : '—'
          }
        />
        <MetricRow
          label="Efficiency"
          value={
            runSummary.efficiency != null
              ? <span className={`font-mono ${effColor(runSummary.efficiency)}`}>
                  {runSummary.efficiency.toFixed(2)}%
                </span>
              : '—'
          }
        />
      </div>

      {/* Resources */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
        <h3 className="text-slate-300 text-xs font-semibold uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-purple-400" /> Resources
        </h3>
        <MetricRow
          label="CPU Usage"
          value={runSummary.cpu_usage != null ? <span className="font-mono">{runSummary.cpu_usage.toFixed(1)}%</span> : '—'}
        />
        <MetricRow
          label="Memory %"
          value={runSummary.memory_usage != null ? <span className="font-mono">{runSummary.memory_usage.toFixed(1)}%</span> : '—'}
        />
        <MetricRow
          label="Peak Memory"
          value={run?.peak_memory_mb != null ? <span className="font-mono">{run.peak_memory_mb.toFixed(1)} MB</span> : '—'}
        />

        {/* Efficiency bar */}
        {runSummary.efficiency != null && (
          <div className="mt-3 pt-3 border-t border-slate-700">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-500">Parallel Efficiency</span>
              <span className={`font-mono ${effColor(runSummary.efficiency)}`}>
                {runSummary.efficiency.toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${
                  runSummary.efficiency >= 80 ? 'bg-emerald-500'
                  : runSummary.efficiency >= 50 ? 'bg-amber-500'
                  : 'bg-red-500'
                }`}
                style={{ width: `${Math.min(100, runSummary.efficiency)}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Error or running state */}
      {run?.error_message && (
        <div className="md:col-span-3 bg-red-950/30 border border-red-900/50 rounded-lg p-4">
          <h3 className="text-red-400 text-xs font-semibold mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Error
          </h3>
          <pre className="text-xs text-red-300 overflow-auto max-h-32 leading-relaxed whitespace-pre-wrap font-mono">
            {run.error_message}
          </pre>
        </div>
      )}
      {(runSummary.status === 'running' || runSummary.status === 'pending') && (
        <div className="md:col-span-3 bg-blue-950/30 border border-blue-900/50 rounded-lg p-4 flex items-center gap-3">
          <Loader2 className="w-4 h-4 animate-spin text-blue-400 flex-shrink-0" />
          <span className="text-blue-400 text-xs">
            {runSummary.status === 'running' ? 'Executing workload…' : 'Queued, waiting to start…'}
          </span>
        </div>
      )}
    </div>
  )
}

// ── Diagnosis Tab ─────────────────────────────────────────────────────────────

function DiagnosisTab({ runId, status }: { runId: string; status: string }) {
  const [result, setResult] = useState<DiagnosisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showWhy, setShowWhy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await getDiagnosis(runId)
      setResult(d)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Diagnosis failed')
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    if (status === 'completed') load()
  }, [status, load])

  if (status !== 'completed') {
    return (
      <div className="p-6 text-center text-slate-500 text-sm pt-16">
        Diagnosis is available after the benchmark completes.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center pt-16 gap-2 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
        Running diagnosis engine…
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-950/30 border border-red-900/50 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-red-400 text-sm font-medium">Diagnosis failed</p>
            <p className="text-red-300 text-xs mt-1">{error}</p>
            <button onClick={load} className="btn-secondary mt-3 text-xs py-1.5 px-3">
              Retry
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!result) return null

  const primaryLabel = BOTTLENECK_LABELS[result.primary_bottleneck] ?? result.primary_bottleneck
  const primaryColor = BOTTLENECK_COLORS[result.primary_bottleneck] ?? 'text-slate-400 bg-slate-800 border-slate-700'

  // Defensive: if backend is missing diagnostic_strength, derive it from all_scores.
  // all_scores is always present; diagnostic_strength = primary_score - secondary_score.
  const rawStrength = result.diagnostic_strength
  const strength: number | null = typeof rawStrength === 'number'
    ? rawStrength
    : (() => {
        const vals = Object.values(result.all_scores ?? {})
          .filter((v): v is number => typeof v === 'number')
          .sort((a, b) => b - a)
        return vals.length >= 2 ? Math.max(0, vals[0] - vals[1]) : (vals[0] ?? null)
      })()

  const strengthPct = strength !== null ? Math.round(strength * 100) : null
  const improvementPct = typeof result.expected_improvement_pct === 'number'
    ? result.expected_improvement_pct : null

  const riskColor = result.risk_assessment?.startsWith('HIGH')
    ? 'text-red-400 bg-red-950/30 border-red-900/50'
    : result.risk_assessment?.startsWith('MEDIUM')
    ? 'text-amber-400 bg-amber-950/30 border-amber-900/50'
    : 'text-emerald-400 bg-emerald-950/30 border-emerald-900/50'

  const sortedScores = Object.entries(result.all_scores ?? {}).sort(([, a], [, b]) => b - a)
  const primaryScore = typeof result.all_scores?.[result.primary_bottleneck] === 'number'
    ? result.all_scores[result.primary_bottleneck] : null
  const secondaryScore = result.secondary_bottleneck && typeof result.secondary_evidence_strength === 'number'
    ? result.secondary_evidence_strength : null

  return (
    <div className="p-6 space-y-5">
      {/* Primary bottleneck + strength */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
          <p className="text-xs text-slate-500 mb-2">Primary Bottleneck</p>
          <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold border ${primaryColor}`}>
            {primaryLabel}
          </span>
          {result.secondary_bottleneck && (
            <div className="mt-3">
              <p className="text-xs text-slate-500 mb-1">Secondary</p>
              <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs border ${
                BOTTLENECK_COLORS[result.secondary_bottleneck] ?? 'text-slate-400 bg-slate-800 border-slate-700'
              }`}>
                {BOTTLENECK_LABELS[result.secondary_bottleneck] ?? result.secondary_bottleneck}
              </span>
            </div>
          )}
        </div>

        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
          <p className="text-xs text-slate-500 mb-2">
            Diagnostic Strength
            <span className="text-slate-600 ml-1">(primary score − secondary score)</span>
          </p>
          {strength !== null ? (
            <>
              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        (strengthPct ?? 0) >= 40 ? 'bg-cyan-500'
                        : (strengthPct ?? 0) >= 20 ? 'bg-amber-500'
                        : 'bg-slate-500'
                      }`}
                      style={{ width: `${strengthPct ?? 0}%` }}
                    />
                  </div>
                </div>
                <span className="font-mono text-sm text-slate-200 w-12 text-right">
                  {strength.toFixed(2)}
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1.5">
                {(strengthPct ?? 0) >= 40
                  ? 'Clear — primary classifier leads clearly'
                  : (strengthPct ?? 0) >= 20
                  ? 'Moderate — some separation from next classifier'
                  : 'Ambiguous — multiple classifiers are close'}
              </p>
            </>
          ) : (
            <p className="text-xs text-slate-500 mt-1.5">Score data unavailable</p>
          )}

          {result.risk_assessment && (
            <div className={`mt-3 rounded border px-3 py-2 text-xs ${riskColor}`}>
              <span className="font-semibold">Risk: </span>
              {result.risk_assessment}
            </div>
          )}
        </div>
      </div>

      {/* Executive summary */}
      <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-slate-500 mb-1.5">Executive Summary</p>
        <p className="text-slate-300 text-sm leading-relaxed">{result.executive_summary}</p>
      </div>

      {/* Why this diagnosis — expandable */}
      <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg overflow-hidden">
        <button
          onClick={() => setShowWhy((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/50 transition-colors"
        >
          <div className="flex items-center gap-2 text-xs text-slate-400 font-medium uppercase tracking-wide">
            <Info className="w-3.5 h-3.5 text-cyan-400" />
            Why this diagnosis?
          </div>
          {showWhy
            ? <ChevronUp className="w-4 h-4 text-slate-500" />
            : <ChevronDown className="w-4 h-4 text-slate-500" />
          }
        </button>
        {showWhy && (
          <div className="px-4 pb-4 space-y-3 border-t border-slate-700/50">
            <p className="text-xs text-slate-500 mt-3 leading-relaxed">
              The diagnosis engine runs <strong className="text-slate-400">10 classifiers</strong> in parallel.
              Each classifier scores the workload from 0 to 1 based on measured metrics (CPU, memory,
              speedup, efficiency, I/O, etc.). The highest-scoring classifier is declared the primary bottleneck.
              Diagnostic strength is the absolute gap between the top two scores — not a probability.
            </p>

            {/* Scoring rule summary */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="space-y-1">
                <p className="text-slate-500 font-medium uppercase tracking-wide text-[10px]">Primary Classifier</p>
                <div className="flex items-center justify-between bg-slate-900 rounded px-3 py-2">
                  <span className={`font-medium ${primaryColor.split(' ')[0]}`}>{primaryLabel}</span>
                  <span className="font-mono text-slate-200">
                    {primaryScore !== null ? primaryScore.toFixed(3) : '—'}
                  </span>
                </div>
              </div>
              {result.secondary_bottleneck && (
                <div className="space-y-1">
                  <p className="text-slate-500 font-medium uppercase tracking-wide text-[10px]">Secondary Classifier</p>
                  <div className="flex items-center justify-between bg-slate-900 rounded px-3 py-2">
                    <span className={`font-medium ${
                      (BOTTLENECK_COLORS[result.secondary_bottleneck] ?? '').split(' ')[0]
                    }`}>
                      {BOTTLENECK_LABELS[result.secondary_bottleneck] ?? result.secondary_bottleneck}
                    </span>
                    <span className="font-mono text-slate-200">
                      {secondaryScore !== null ? secondaryScore.toFixed(3) : '—'}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Diagnostic strength derivation */}
            {strength !== null && primaryScore !== null && (
              <div className="bg-slate-900 rounded px-3 py-2 text-xs font-mono text-slate-400">
                diagnostic_strength = {primaryScore.toFixed(3)}
                {secondaryScore !== null ? ` − ${secondaryScore.toFixed(3)} = ${strength.toFixed(3)}` : ' (no secondary)'}
              </div>
            )}

            {/* Evidence */}
            <div>
              <p className="text-slate-500 font-medium uppercase tracking-wide text-[10px] mb-2">
                Evidence used by primary classifier
              </p>
              <div className="space-y-0">
                {result.evidence.map((e, i) => (
                  <div key={i} className="flex justify-between items-center py-1 border-b border-slate-800 last:border-0">
                    <span className="text-xs text-slate-500">{e.metric}</span>
                    <span className="text-xs text-slate-300 font-mono">{e.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Evidence card + improvement */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
          <p className="text-xs text-slate-500 mb-3 uppercase tracking-wide">Measured Evidence</p>
          <div className="space-y-0">
            {result.evidence.map((e, i) => (
              <div key={i} className="flex justify-between items-center py-1.5 border-b border-slate-700/50 last:border-0">
                <span className="text-xs text-slate-400">{e.metric}</span>
                <span className="text-xs text-slate-200 font-mono">{e.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Expected improvement + recommendations */}
        <div className="space-y-3">
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
            <div className="flex items-start justify-between mb-1">
              <p className="text-xs text-slate-500">Expected Improvement</p>
              <span className="text-[10px] text-slate-600 bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5">
                heuristic estimate
              </span>
            </div>
            <p className="text-2xl font-bold text-cyan-400 font-mono">
              {improvementPct !== null ? `+${improvementPct.toFixed(1)}%` : '—'}
            </p>
            <p className="text-[10px] text-slate-600 mt-1">
              Estimated gain if the primary bottleneck is fully eliminated.
              Formula: (100% − efficiency) × bottleneck-specific factor.
            </p>
          </div>

          <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
            <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide">Optimization Opportunities</p>
            <ul className="space-y-2">
              {result.optimization_opportunities.map((opp, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                  <ChevronRight className="w-3 h-3 text-cyan-400 mt-0.5 flex-shrink-0" />
                  {opp}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* All classifier scores */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-slate-500 mb-3 uppercase tracking-wide">All Classifier Scores</p>
        <div className="space-y-2">
          {sortedScores.map(([name, score]) => {
            const s = typeof score === 'number' ? score : 0
            return (
              <div key={name} className="flex items-center gap-3">
                <span className="text-xs text-slate-400 w-44 truncate">
                  {BOTTLENECK_LABELS[name] ?? name}
                </span>
                <div className="flex-1 bg-slate-700 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all ${
                      name === result.primary_bottleneck ? 'bg-cyan-500' : 'bg-slate-500'
                    }`}
                    style={{ width: `${s * 100}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-slate-400 w-10 text-right">
                  {s.toFixed(3)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Profiling Tab ─────────────────────────────────────────────────────────────

interface ProfileHotspot {
  function: string
  calls: number
  total_time_ms: number
  self_time_ms: number
  pct_of_total: number
  is_app?: boolean  // added by backend; undefined = treat as app (backward compat)
}

interface ProfileData {
  workload_type: string
  total_time_ms: number
  total_calls: number
  peak_memory_mb: number
  top_hotspots: ProfileHotspot[]
  memory_hotspots: Array<{
    filename: string
    lineno: number
    size_kb: number
    count: number
  }>
}

// ── Profiling helpers ─────────────────────────────────────────────────────────

const _FW_PATTERNS = [
  'multiprocessing', 'concurrent', 'threading', 'queue', 'socket',
  'pickle', 'copyreg', '_bootstrap', 'selectors', 'signal.py',
  'socketserver', 'ssl.py', 'subprocess', '<string>',
]

function isFrameworkHotspot(h: ProfileHotspot): boolean {
  if (typeof h.is_app === 'boolean') return !h.is_app
  const lower = h.function.toLowerCase()
  return lower.includes('{built-in') || _FW_PATTERNS.some(p => lower.includes(p))
}

function extractFuncName(fn: string): string {
  const m = fn.match(/\(([^)]+)\)$/)
  return m ? m[1] : (fn.split('/').pop() ?? fn)
}

const _SYNC_FN_PATTERNS = ['acquire', 'release', 'lock', 'condition', 'wait', 'join',
  'barrier', 'semaphore', '_recv', 'recv_bytes', 'recv_into', '_poll']

function isSyncHotspot(h: ProfileHotspot): boolean {
  if (!isFrameworkHotspot(h)) return false
  const name = extractFuncName(h.function).toLowerCase()
  return _SYNC_FN_PATTERNS.some(p => name.includes(p))
}

// selfPct = self_time_ms as % of the profile's total measured time
function computeSelfPct(h: ProfileHotspot, totalMs: number): number {
  if (totalMs <= 0) return 0
  return Math.min((h.self_time_ms / totalMs) * 100, 100)
}

function inferOptimization(fn: string, selfPct: number): { candidate: string; impact: 'high' | 'medium' | 'low' } {
  const name = extractFuncName(fn).toLowerCase()
  let candidate = 'profile deeper with line_profiler'
  if (/sum|add|mul|dot|matmul|compute|calc|arith/.test(name)) candidate = 'vectorization (numpy/scipy)'
  else if (/sort|search|find|look|binary|hash/.test(name)) candidate = 'algorithm selection'
  else if (/read|write|load|save|open|file|io|parse/.test(name)) candidate = 'I/O buffering or async I/O'
  else if (/map|apply|transform|process|filter|convert/.test(name)) candidate = 'vectorization or parallelism'
  else if (/spawn|worker|thread|pool|fork/.test(name)) candidate = 'parallelism tuning'
  else if (/run|execute|main|bench/.test(name)) candidate = 'algorithm or data structure'
  // Use self-time % for impact rating
  const impact: 'high' | 'medium' | 'low' = selfPct >= 20 ? 'high' : selfPct >= 8 ? 'medium' : 'low'
  return { candidate, impact }
}

function ProfilingTab({ runId, status, workloadType }: {
  runId: string
  status: string
  workloadType: string
}) {
  const [profileData, setProfileData] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [flameSvg, setFlameSvg] = useState<string | null>(null)
  const [flameLoading, setFlameLoading] = useState(false)
  const [flameVisible, setFlameVisible] = useState(false)

  const loadProfile = useCallback(async () => {
    setLoading(true)
    setError(null)
    console.log('[PROFILING_DEBUG] ProfilingTab loadProfile runId=%s', runId)
    try {
      const data = await getProfile(runId)
      // Always set profileData when the API returns 200.
      // Empty top_hotspots is valid (profiling ran but found nothing to show).
      console.log('[PROFILING_DEBUG] ProfilingTab getProfile OK: keys=%s total_calls=%s',
        Object.keys(data).join(','), data.total_calls)
      setProfileData(data as unknown as ProfileData)
    } catch (err) {
      // 404 = no profiling data stored — normal when profiling was not enabled
      const msg = err instanceof Error ? err.message : ''
      const is404 = msg.toLowerCase().includes('no profiling data') ||
                    msg.toLowerCase().includes('post first')
      console.log('[PROFILING_DEBUG] ProfilingTab getProfile ERR: msg=%s is404=%s', msg, is404)
      if (!is404) {
        setError(`Could not load profiling data: ${msg}`)
      }
      // 404 is silently treated as "profiling was not enabled"
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    if (status === 'completed') loadProfile()
  }, [status, loadProfile])

  const handleRunProfiler = async () => {
    setRunning(true)
    setError(null)
    try {
      await profileRun(runId)
      await loadProfile()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Profiling failed'
      // Translate the backend's rejection of custom workloads into a helpful message
      if (msg.includes('cannot be profiled') || msg.includes('Enable profiling')) {
        setError(
          'This workload cannot be profiled on demand. ' +
          'Re-run from Custom Workloads with "Enable Profiling" checked.'
        )
      } else {
        setError(msg)
      }
    } finally {
      setRunning(false)
    }
  }

  const handleViewFlameGraph = async () => {
    if (flameSvg) {
      setFlameVisible((v) => !v)
      return
    }
    setFlameLoading(true)
    try {
      const svg = await getFlameGraph(runId)
      setFlameSvg(svg)
      setFlameVisible(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load flame graph')
    } finally {
      setFlameLoading(false)
    }
  }

  if (status !== 'completed') {
    return (
      <div className="p-6 text-center text-slate-500 text-sm pt-16">
        Profiling is available after the benchmark completes.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center pt-16 gap-2 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
        Loading profiling data…
      </div>
    )
  }

  return (
    <div className="p-6 space-y-5">
      {error && (
        <div className="bg-red-950/30 border border-red-900/50 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span className="text-red-300 text-xs">{error}</span>
        </div>
      )}

      {!profileData ? (
        workloadType === 'custom_python' ? (
          /* Custom workloads: profiling must be enabled at run time */
          <div className="text-center py-12">
            <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4">
              <Flame className="w-6 h-6 text-slate-600" />
            </div>
            <p className="text-slate-400 text-sm mb-1">Profiling was not enabled for this run</p>
            <p className="text-slate-600 text-xs max-w-sm mx-auto leading-relaxed">
              Re-run the workload from the <strong className="text-slate-500">Custom Workloads</strong> page
              with the <strong className="text-slate-500">Enable Profiling</strong> checkbox checked.
              Profiling is captured during the parallel run and cannot be added retroactively.
            </p>
          </div>
        ) : (
          /* Built-in workloads: can profile on demand */
          <div className="text-center py-12">
            <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4">
              <Flame className="w-6 h-6 text-slate-600" />
            </div>
            <p className="text-slate-400 text-sm mb-1">No profiling data yet</p>
            <p className="text-slate-600 text-xs mb-4">
              Run the profiler to get cProfile hotspot data and a flame graph.
            </p>
            <button
              onClick={handleRunProfiler}
              disabled={running}
              className="btn-primary"
            >
              {running ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Profiling…</>
              ) : (
                <><Activity className="w-3.5 h-3.5" /> Run Profiler</>
              )}
            </button>
          </div>
        )
      ) : !profileData.top_hotspots || profileData.top_hotspots.length === 0 ? (
        /* Profiling ran but captured no hotspots */
        <div className="text-center py-12">
          <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4">
            <Activity className="w-6 h-6 text-slate-600" />
          </div>
          <p className="text-slate-400 text-sm mb-1">Profiling ran — no hotspots captured</p>
          <p className="text-slate-600 text-xs max-w-sm mx-auto leading-relaxed">
            cProfile recorded {profileData.total_calls?.toLocaleString() ?? 0} function calls in{' '}
            {profileData.total_time_ms?.toFixed(1) ?? 0} ms, but all frames were in
            standard library modules (filtered from output). Your workload may delegate
            almost entirely to built-in C extensions.
          </p>
          {workloadType !== 'custom_python' && (
            <button onClick={handleRunProfiler} disabled={running} className="btn-secondary mt-4 text-xs py-1.5 px-3">
              {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Activity className="w-3 h-3" />}
              Re-profile
            </button>
          )}
        </div>
      ) : (
        <ProfilingResults
          profileData={profileData}
          workloadType={workloadType}
          running={running}
          flameLoading={flameLoading}
          flameSvg={flameSvg}
          flameVisible={flameVisible}
          onRunProfiler={handleRunProfiler}
          onViewFlameGraph={handleViewFlameGraph}
        />
      )}
    </div>
  )
}

// ── Profiling Results ─────────────────────────────────────────────────────────

// Tooltip helper: wraps a column header with an Info icon carrying a native title
function ColHeader({ label, tip }: { label: string; tip: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {label}
      <span title={tip} className="cursor-help">
        <Info className="w-3 h-3 text-slate-600 inline" />
      </span>
    </span>
  )
}

function HotspotTable({
  hotspots,
  totalMs,
  accentClass,
  selfBarClass,
}: {
  hotspots: ProfileHotspot[]  // already sorted by self_time_ms desc
  totalMs: number
  accentClass: string
  selfBarClass: string
}) {
  if (hotspots.length === 0) return null
  // Max self pct across rows — for bar scaling
  const maxSelfPct = Math.max(...hotspots.map(h => computeSelfPct(h, totalMs)), 1)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-700/50">
            <th className="px-4 py-2 text-left text-slate-500 font-medium">Function</th>
            <th className="px-4 py-2 text-right text-slate-500 font-medium">Calls</th>
            <th className="px-4 py-2 text-right text-slate-500 font-medium">
              <ColHeader
                label="Cumul %"
                tip="Cumulative Time: time spent inside this function and all child calls. Parent functions always show ≥ child values — this is expected."
              />
            </th>
            <th className="px-4 py-2 text-right text-slate-500 font-medium">
              <ColHeader
                label="Self %"
                tip="Self Time: time spent only in this function body, excluding child calls. Sorted by this column. Values >20% are highlighted."
              />
            </th>
          </tr>
        </thead>
        <tbody>
          {hotspots.map((h, i) => {
            const selfPct = computeSelfPct(h, totalMs)
            const isHot  = selfPct >= 20
            return (
              <tr
                key={i}
                className={`border-b border-slate-800/50 hover:bg-slate-800/40 ${
                  isHot ? 'bg-amber-950/20' : ''
                }`}
                title={h.function}
              >
                <td className="px-4 py-2 max-w-xs">
                  <div className="flex items-center gap-1.5">
                    {isHot && (
                      <span
                        className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0"
                        title="Self time >20% — primary optimization target"
                      />
                    )}
                    <div>
                      <span className={`font-mono ${accentClass}`}>
                        {extractFuncName(h.function)}
                      </span>
                      <span className="text-slate-600 ml-1.5 text-[10px] font-mono truncate block">
                        {h.function.split('/').pop()?.split('(')[0]}
                      </span>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-2 text-right font-mono text-slate-500">
                  {h.calls.toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right font-mono text-slate-500">
                  {h.pct_of_total.toFixed(1)}%
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 bg-slate-700 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${selfBarClass}`}
                        style={{ width: `${(selfPct / maxSelfPct) * 100}%` }}
                      />
                    </div>
                    <span className={`font-mono w-10 text-right ${isHot ? 'text-amber-400 font-semibold' : 'text-slate-400'}`}>
                      {selfPct.toFixed(1)}%
                    </span>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ProfilingResults({
  profileData,
  workloadType,
  running,
  flameLoading,
  flameSvg,
  flameVisible,
  onRunProfiler,
  onViewFlameGraph,
}: {
  profileData: ProfileData
  workloadType: string
  running: boolean
  flameLoading: boolean
  flameSvg: string | null
  flameVisible: boolean
  onRunProfiler: () => void
  onViewFlameGraph: () => void
}) {
  const [showFramework, setShowFramework] = useState(false)

  const totalMs = profileData.total_time_ms || 1

  // Partition and sort each group by self_time_ms descending
  const sortBySelf = (arr: ProfileHotspot[]) =>
    [...arr].sort((a, b) => b.self_time_ms - a.self_time_ms)

  const appHotspots  = sortBySelf(profileData.top_hotspots.filter(h => !isFrameworkHotspot(h)))
  const syncHotspots = sortBySelf(profileData.top_hotspots.filter(h => isSyncHotspot(h)))
  const fwOnlyHotspots = sortBySelf(
    profileData.top_hotspots.filter(h => isFrameworkHotspot(h) && !isSyncHotspot(h))
  )
  const allFwHotspots = sortBySelf(profileData.top_hotspots.filter(h => isFrameworkHotspot(h)))

  // Three-way self-time breakdown
  const appSelf  = appHotspots.reduce((s, h) => s + h.self_time_ms, 0)
  const syncSelf = syncHotspots.reduce((s, h) => s + h.self_time_ms, 0)
  const fwSelf   = fwOnlyHotspots.reduce((s, h) => s + h.self_time_ms, 0)
  const bucketTotal = appSelf + syncSelf + fwSelf || 1
  const appPct  = Math.round((appSelf  / bucketTotal) * 100)
  const syncPct = Math.round((syncSelf / bucketTotal) * 100)
  const fwPct   = 100 - appPct - syncPct

  // Interpretation card — top app hotspot by self-time
  const topApp = appHotspots[0]
  const topSelfPct = topApp ? computeSelfPct(topApp, totalMs) : 0
  const opt = topApp ? inferOptimization(topApp.function, topSelfPct) : null

  const impactColors = {
    high:   'text-red-400 bg-red-500/10 border-red-500/30',
    medium: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    low:    'text-slate-400 bg-slate-700/50 border-slate-600/30',
  }

  return (
    <>
      {/* ── Summary metrics ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total Time',     value: `${profileData.total_time_ms.toFixed(1)} ms` },
          { label: 'Function Calls', value: profileData.total_calls.toLocaleString() },
          { label: 'Peak Memory',    value: `${profileData.peak_memory_mb.toFixed(1)} MB` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 text-center">
            <p className="text-xs text-slate-500 mb-1">{label}</p>
            <p className="text-slate-200 font-mono text-sm font-semibold">{value}</p>
          </div>
        ))}
      </div>

      {/* ── Three-way self-time breakdown ────────────────────────────────── */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
            Self-Time Breakdown
          </p>
          <span
            title="Based on exclusive self-time, which does not double-count parent/child calls."
            className="text-[10px] text-slate-600 cursor-help flex items-center gap-0.5"
          >
            self-time only <Info className="w-3 h-3" />
          </span>
        </div>
        <div className="flex rounded-full overflow-hidden h-3">
          <div className="bg-cyan-500 transition-all"  style={{ width: `${appPct}%` }}  title={`Application: ${appPct}%`} />
          <div className="bg-amber-500 transition-all" style={{ width: `${syncPct}%` }} title={`Synchronization: ${syncPct}%`} />
          <div className="bg-slate-600 transition-all" style={{ width: `${fwPct}%` }}   title={`Framework: ${fwPct}%`} />
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-cyan-500 shrink-0" />
            <div>
              <span className="text-slate-300 font-semibold">{appPct}%</span>
              <span className="text-slate-500 ml-1">Application</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-amber-500 shrink-0" />
            <div>
              <span className="text-slate-300 font-semibold">{syncPct}%</span>
              <span className="text-slate-500 ml-1">Synchronization</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-slate-600 shrink-0" />
            <div>
              <span className="text-slate-400 font-semibold">{fwPct}%</span>
              <span className="text-slate-500 ml-1">Framework</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Interpretation card ──────────────────────────────────────────── */}
      {topApp && opt && (
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <Flame className="w-4 h-4 text-orange-400" />
            <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">
              Top Optimization Candidate
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">Hotspot function</p>
              <p className="font-mono text-cyan-400 text-sm font-semibold truncate" title={topApp.function}>
                {extractFuncName(topApp.function)}()
              </p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">
                <ColHeader
                  label="Consumes (self-time)"
                  tip="Self-time % of total profiled duration. More meaningful than cumulative % for identifying where to optimize."
                />
              </p>
              <p className={`font-mono text-sm font-semibold ${topSelfPct >= 20 ? 'text-amber-400' : 'text-slate-200'}`}>
                {topSelfPct.toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">Optimization candidate</p>
              <p className="text-slate-300 text-xs">{opt.candidate}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">Potential impact</p>
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase border ${impactColors[opt.impact]}`}>
                {opt.impact}
              </span>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-700/50 text-[10px] text-slate-500 space-y-0.5">
            <p>
              Most runtime is spent inside{' '}
              <span className="font-mono text-cyan-400">{extractFuncName(topApp.function)}()</span>
            </p>
            {syncPct > 5 && (
              <p>
                Synchronization overhead{' '}
                <span className="text-amber-400 font-semibold">{syncPct}%</span>
                {' '}— workers may be blocked waiting on locks or IPC.
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── Application Hotspots ─────────────────────────────────────────── */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700/50 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-500" />
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Application Hotspots</p>
          <span className="text-[10px] text-slate-600 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5">
            {appHotspots.length}
          </span>
          <span className="text-[10px] text-slate-600 ml-auto">sorted by self-time ↓</span>
        </div>
        {appHotspots.length > 0 ? (
          <HotspotTable
            hotspots={appHotspots}
            totalMs={totalMs}
            accentClass="text-cyan-400"
            selfBarClass="bg-cyan-500"
          />
        ) : (
          <div className="px-4 py-6 text-center">
            <p className="text-slate-500 text-xs">No application-level hotspots detected.</p>
            <p className="text-slate-600 text-[11px] mt-1">
              All captured time is in framework/runtime code.
            </p>
          </div>
        )}
      </div>

      {/* ── Framework / Runtime section ──────────────────────────────────── */}
      {allFwHotspots.length > 0 && (
        <div className="bg-slate-800/30 border border-slate-700/30 rounded-lg overflow-hidden">
          <button
            onClick={() => setShowFramework(v => !v)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-800/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-slate-500" />
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                Framework / Runtime Internals
              </p>
              <span className="text-[10px] text-slate-600 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5">
                {allFwHotspots.length}
              </span>
              {syncPct > 0 && (
                <span className="text-[10px] text-amber-600 ml-1">
                  {syncPct}% sync · {fwPct}% framework
                </span>
              )}
            </div>
            {showFramework
              ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
              : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
            }
          </button>
          {showFramework && (
            <div className="border-t border-slate-700/30">
              <HotspotTable
                hotspots={allFwHotspots}
                totalMs={totalMs}
                accentClass="text-slate-400"
                selfBarClass="bg-slate-500"
              />
            </div>
          )}
        </div>
      )}

      {/* ── Flame graph ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <button onClick={onViewFlameGraph} disabled={flameLoading} className="btn-secondary">
          {flameLoading
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…</>
            : <><Flame className="w-3.5 h-3.5 text-orange-400" /> {flameVisible ? 'Hide' : 'View'} Flame Graph</>
          }
        </button>
        {workloadType !== 'custom_python' && (
          <button onClick={onRunProfiler} disabled={running} className="btn-secondary text-xs py-1.5 px-3">
            {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Activity className="w-3 h-3" />}
            Re-profile
          </button>
        )}
      </div>

      {flameVisible && flameSvg && (
        <div className="bg-slate-950 border border-slate-700 rounded-lg overflow-auto">
          <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <p className="text-xs text-slate-400 font-medium">Flame Graph</p>
              <div className="flex items-center gap-2 text-[10px] text-slate-600">
                <span className="w-2 h-2 rounded-sm bg-cyan-500 inline-block" /> App
                <span className="w-2 h-2 rounded-sm bg-slate-600 inline-block ml-1" /> Framework
              </div>
            </div>
            <p className="text-xs text-slate-600">Hover for details</p>
          </div>
          <div className="min-w-full" dangerouslySetInnerHTML={{ __html: flameSvg }} />
        </div>
      )}

      {/* ── Memory hotspots ──────────────────────────────────────────────── */}
      {profileData.memory_hotspots && profileData.memory_hotspots.length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/50">
            <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">
              Memory Allocation Hotspots
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700/50">
                  <th className="px-4 py-2 text-left text-slate-500 font-medium">File</th>
                  <th className="px-4 py-2 text-right text-slate-500 font-medium">Line</th>
                  <th className="px-4 py-2 text-right text-slate-500 font-medium">Size (KB)</th>
                  <th className="px-4 py-2 text-right text-slate-500 font-medium">Allocations</th>
                </tr>
              </thead>
              <tbody>
                {profileData.memory_hotspots.map((m, i) => (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                    <td className="px-4 py-2 font-mono text-slate-300 max-w-xs truncate">
                      {m.filename.split('/').pop()}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-slate-400">{m.lineno}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{m.size_kb.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-400">{m.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

// ── Certification Tab ─────────────────────────────────────────────────────────

function CertificationTab({
  runId, displayName, status,
}: {
  runId: string
  displayName: string
  status: string
}) {
  const [report, setReport] = useState<CertificationReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await generateCertification([runId], displayName)
      setReport(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Certification failed')
    } finally {
      setLoading(false)
    }
  }, [runId, displayName])

  if (status !== 'completed') {
    return (
      <div className="p-6 text-center text-slate-500 text-sm pt-16">
        Certification is available after the benchmark completes.
      </div>
    )
  }

  if (!report && !loading) {
    return (
      <div className="p-6 text-center py-12">
        <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4">
          <Award className="w-6 h-6 text-slate-600" />
        </div>
        <p className="text-slate-400 text-sm mb-1">Scalability Certification</p>
        <p className="text-slate-600 text-xs mb-1 max-w-sm mx-auto">
          Generate a certification report with grade, scaling analysis, and optimization recommendations.
        </p>
        <p className="text-slate-700 text-xs mb-4 max-w-sm mx-auto">
          For stronger certification, run a scaling study (multiple worker counts) from Research Mode.
        </p>
        {error && (
          <p className="text-red-400 text-xs mb-3">{error}</p>
        )}
        <button onClick={generate} className="btn-primary">
          <Award className="w-3.5 h-3.5" /> Generate Certification
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center pt-16 gap-2 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
        Generating certification report…
      </div>
    )
  }

  if (!report) return null

  const gradeColor = GRADE_COLORS[report.certification.grade] ?? 'text-slate-400 border-slate-400'
  const effPct = report.analysis.best_efficiency_pct

  return (
    <div className="p-6 space-y-5">
      {/* Grade + summary row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Grade */}
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4 flex flex-col items-center justify-center">
          <p className="text-xs text-slate-500 mb-2">Grade</p>
          <div className={`text-5xl font-black border-2 rounded-xl w-20 h-20 flex items-center justify-center ${gradeColor}`}>
            {report.certification.grade}
          </div>
          <p className="text-xs text-slate-500 mt-2 text-center leading-tight">
            {report.certification.grade_description}
          </p>
        </div>

        {/* Key metrics */}
        <div className="md:col-span-3 grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { label: 'Best Speedup', value: `${report.analysis.best_speedup.toFixed(2)}×`, color: 'text-cyan-400' },
            {
              label: 'Best Efficiency',
              value: `${effPct.toFixed(1)}%`,
              color: effPct >= 80 ? 'text-emerald-400' : effPct >= 50 ? 'text-amber-400' : 'text-red-400',
            },
            {
              label: 'Optimal Workers',
              value: `${report.recommendations.optimal_worker_count}`,
              color: 'text-slate-200',
            },
            {
              label: 'Theoretical Ceiling',
              value: report.analysis.theoretical_ceiling != null
                ? `${report.analysis.theoretical_ceiling.toFixed(1)}×`
                : 'N/A',
              color: 'text-purple-400',
            },
            {
              label: 'Parallel Fraction',
              value: report.analysis.parallel_fraction != null
                ? `${(report.analysis.parallel_fraction * 100).toFixed(1)}%`
                : 'N/A',
              color: 'text-blue-400',
            },
            {
              label: 'Primary Bottleneck',
              value: BOTTLENECK_LABELS[report.diagnosis.primary_bottleneck] ?? report.diagnosis.primary_bottleneck,
              color: 'text-slate-300',
            },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-500 mb-1">{label}</p>
              <p className={`text-base font-semibold font-mono ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Grade rationale */}
      <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-slate-500 mb-1.5">Certification Rationale</p>
        <p className="text-slate-300 text-sm leading-relaxed">{report.certification.rationale}</p>
      </div>

      {/* Diagnosis summary */}
      <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-slate-500 mb-1.5">Diagnostic Summary</p>
        <p className="text-slate-300 text-sm leading-relaxed">{report.diagnosis.executive_summary}</p>
      </div>

      {/* Scaling data table */}
      {report.scaling_data && report.scaling_data.length > 1 && (
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/50">
            <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Scaling Data</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700/50">
                  <th className="px-4 py-2 text-left text-slate-500">Workers</th>
                  <th className="px-4 py-2 text-right text-slate-500">Time (s)</th>
                  <th className="px-4 py-2 text-right text-slate-500">Speedup</th>
                  <th className="px-4 py-2 text-right text-slate-500">Efficiency</th>
                </tr>
              </thead>
              <tbody>
                {report.scaling_data.map((row) => (
                  <tr key={row.worker_count} className="border-b border-slate-800/50">
                    <td className="px-4 py-2 font-mono text-slate-300">{row.worker_count}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-400">
                      {row.execution_time_s.toFixed(4)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-cyan-400">
                      {row.speedup.toFixed(2)}×
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      <span className={
                        row.efficiency_pct >= 80 ? 'text-emerald-400'
                        : row.efficiency_pct >= 50 ? 'text-amber-400'
                        : 'text-red-400'
                      }>
                        {row.efficiency_pct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recommendations */}
      {report.recommendations.optimization_priorities?.length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide mb-3 flex items-center gap-1.5">
            <Target className="w-3.5 h-3.5 text-cyan-400" /> Optimization Priorities
          </p>
          <ul className="space-y-2">
            {report.recommendations.optimization_priorities.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                <CheckCircle className="w-3 h-3 text-emerald-400 mt-0.5 flex-shrink-0" />
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Export buttons */}
      <div className="flex items-center gap-3 pt-1">
        <p className="text-xs text-slate-500 mr-1">Export:</p>
        <button
          onClick={() => exportCertificatePDF(
            report.export_html,
            `scalelab-cert-${runId.slice(0, 8)}.pdf`
          )}
          className="btn-primary text-xs py-1.5 px-3"
        >
          <Download className="w-3 h-3" /> PDF
        </button>
        <button
          onClick={() => downloadFile(
            report.export_html,
            `certification-${runId.slice(0, 8)}.html`,
            'text/html'
          )}
          className="btn-secondary text-xs py-1.5 px-3"
        >
          <Download className="w-3 h-3" /> HTML
        </button>
        <button
          onClick={generate}
          disabled={loading}
          className="btn-secondary text-xs py-1.5 px-3 ml-auto"
        >
          <Shield className="w-3 h-3" /> Regenerate
        </button>
      </div>
    </div>
  )
}
