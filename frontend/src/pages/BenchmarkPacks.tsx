/**
 * BenchmarkPacks — Industry Benchmark Packs page
 *
 * Shows the 5 production-representative workloads as cards.
 * Users can run a single pack (with configurable input size / worker count)
 * or select multiple packs for side-by-side comparison.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play, Loader2, CheckCircle, XCircle, ChevronRight, BarChart3,
  GitCompare, Layers, Clock, Cpu, Zap, TrendingUp, AlertCircle,
  X, Check, ShieldCheck, ShieldAlert, ShieldX, AlertTriangle,
} from 'lucide-react'
import Header from '../components/Header'
import { fetchBenchmarkPacks, submitBenchmark, fetchBenchmark } from '../services/api'
import type { BenchmarkPack, BenchmarkRun } from '../types'

// ── Color maps ──────────────────────────────────────────────────────────────

type PackColor = 'cyan' | 'emerald' | 'amber' | 'red' | 'purple'

const COLOR_BORDER: Record<PackColor, string> = {
  cyan: 'border-cyan-500/40',
  emerald: 'border-emerald-500/40',
  amber: 'border-amber-500/40',
  red: 'border-red-500/40',
  purple: 'border-purple-500/40',
}
const COLOR_BG: Record<PackColor, string> = {
  cyan: 'bg-cyan-500/10',
  emerald: 'bg-emerald-500/10',
  amber: 'bg-amber-500/10',
  red: 'bg-red-500/10',
  purple: 'bg-purple-500/10',
}
const COLOR_TEXT: Record<PackColor, string> = {
  cyan: 'text-cyan-400',
  emerald: 'text-emerald-400',
  amber: 'text-amber-400',
  red: 'text-red-400',
  purple: 'text-purple-400',
}
const COLOR_BTN: Record<PackColor, string> = {
  cyan: 'bg-cyan-500/20 hover:bg-cyan-500/30 border-cyan-500/40 text-cyan-300',
  emerald: 'bg-emerald-500/20 hover:bg-emerald-500/30 border-emerald-500/40 text-emerald-300',
  amber: 'bg-amber-500/20 hover:bg-amber-500/30 border-amber-500/40 text-amber-300',
  red: 'bg-red-500/20 hover:bg-red-500/30 border-red-500/40 text-red-300',
  purple: 'bg-purple-500/20 hover:bg-purple-500/30 border-purple-500/40 text-purple-300',
}
const COLOR_RING: Record<PackColor, string> = {
  cyan: 'ring-cyan-500/60',
  emerald: 'ring-emerald-500/60',
  amber: 'ring-amber-500/60',
  red: 'ring-red-500/60',
  purple: 'ring-purple-500/60',
}

function packColor(c: string): PackColor {
  return (['cyan', 'emerald', 'amber', 'red', 'purple'].includes(c) ? c : 'cyan') as PackColor
}

// ── Grade badge ──────────────────────────────────────────────────────────────

function GradeBadge({ grade }: { grade: string }) {
  const color =
    grade.startsWith('A') ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' :
    grade.startsWith('B') ? 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30' :
    'text-amber-400 bg-amber-500/10 border-amber-500/30'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-bold font-mono ${color}`}>
      {grade}
    </span>
  )
}

// ── Bottleneck chip ───────────────────────────────────────────────────────────

function BottleneckChip({ label }: { label: string }) {
  const color =
    label.includes('CPU') ? 'text-orange-400 bg-orange-500/10 border-orange-500/30' :
    label.includes('Memory') ? 'text-blue-400 bg-blue-500/10 border-blue-500/30' :
    label.includes('Communication') ? 'text-violet-400 bg-violet-500/10 border-violet-500/30' :
    'text-slate-400 bg-slate-500/10 border-slate-500/30'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs ${color}`}>
      <Cpu className="w-3 h-3" />
      {label}
    </span>
  )
}

// ── Speedup badge ─────────────────────────────────────────────────────────────

function SpeedupBadge({ speedup }: { speedup: number }) {
  const color =
    speedup >= 3 ? 'text-emerald-400' :
    speedup >= 1.5 ? 'text-cyan-400' :
    speedup >= 1.1 ? 'text-amber-400' :
    'text-red-400'
  return <span className={`font-mono font-bold ${color}`}>{speedup.toFixed(2)}×</span>
}

// ── fmt helpers ──────────────────────────────────────────────────────────────

function fmtSize(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function fmtMs(s: number): string {
  const ms = s * 1000
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  if (ms >= 1) return `${ms.toFixed(1)}ms`
  const us = s * 1_000_000
  if (us >= 1) return `${us.toFixed(0)}µs`
  return '< 1µs'
}

// ── Quality badge ─────────────────────────────────────────────────────────────

function QualityBadge({ score }: { score: string | null }) {
  if (!score || score === 'Unknown') return null
  if (score === 'Reliable') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium text-emerald-400 bg-emerald-500/10 border-emerald-500/30">
        <ShieldCheck className="w-3 h-3" />
        Reliable
      </span>
    )
  }
  if (score === 'Marginal') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium text-amber-400 bg-amber-500/10 border-amber-500/30">
        <ShieldAlert className="w-3 h-3" />
        Marginal
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium text-red-400 bg-red-500/10 border-red-500/30">
      <ShieldX className="w-3 h-3" />
      Invalid
    </span>
  )
}

// ── Run Modal ─────────────────────────────────────────────────────────────────

interface RunConfig {
  inputSize: number
  workerCount: number
  iterations: number
}

interface RunResult {
  run: BenchmarkRun
  durationMs: number
}

interface RunModalProps {
  pack: BenchmarkPack
  onClose: () => void
}

function RunModal({ pack, onClose }: RunModalProps) {
  const navigate = useNavigate()
  const color = packColor(pack.color)
  const [config, setConfig] = useState<RunConfig>({
    inputSize: pack.default_input_size,
    workerCount: 4,
    iterations: 1,
  })
  const [phase, setPhase] = useState<'config' | 'running' | 'done' | 'error'>('config')
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progressLabel, setProgressLabel] = useState('Submitting...')

  const handleRun = async () => {
    setPhase('running')
    setError(null)
    const t0 = Date.now()
    try {
      setProgressLabel('Submitting benchmark...')
      const run = await submitBenchmark({
        workload_type: pack.workload_type as any,
        input_size: config.inputSize,
        worker_count: config.workerCount,
        iterations: config.iterations,
      })

      setProgressLabel('Running workload...')
      // Poll until complete
      let polled: BenchmarkRun = run
      for (let attempt = 0; attempt < 120; attempt++) {
        await new Promise(r => setTimeout(r, 1000))
        polled = await fetchBenchmark(run.id)
        if (polled.status === 'completed' || polled.status === 'failed') break
      }

      if (polled.status === 'failed') {
        throw new Error(polled.error_message || 'Benchmark failed')
      }

      setResult({ run: polled, durationMs: Date.now() - t0 })
      setPhase('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setPhase('error')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className={`bg-slate-900 border ${COLOR_BORDER[color]} rounded-xl w-full max-w-lg shadow-2xl`}>
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-slate-800">
          <div>
            <div className={`text-xs font-medium ${COLOR_TEXT[color]} mb-1`}>{pack.domain_tag}</div>
            <h2 className="text-slate-100 font-semibold text-lg">{pack.name}</h2>
            <p className="text-slate-500 text-xs mt-0.5">{pack.subtitle}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors ml-4 mt-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {phase === 'config' && (
            <>
              {/* Input size */}
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-2">
                  {pack.input_label} — Input Size
                </label>
                <div className="flex flex-wrap gap-2">
                  {pack.size_presets.map(s => (
                    <button
                      key={s}
                      onClick={() => setConfig(c => ({ ...c, inputSize: s }))}
                      className={`px-3 py-1.5 rounded text-xs font-mono border transition-colors ${
                        config.inputSize === s
                          ? `${COLOR_BG[color]} ${COLOR_BORDER[color]} ${COLOR_TEXT[color]}`
                          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {fmtSize(s)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Worker count */}
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-2">
                  Worker Count
                </label>
                <div className="flex gap-2">
                  {[1, 2, 4, 8].map(w => (
                    <button
                      key={w}
                      onClick={() => setConfig(c => ({ ...c, workerCount: w }))}
                      className={`px-3 py-1.5 rounded text-xs font-mono border transition-colors ${
                        config.workerCount === w
                          ? `${COLOR_BG[color]} ${COLOR_BORDER[color]} ${COLOR_TEXT[color]}`
                          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {w}
                    </button>
                  ))}
                </div>
              </div>

              {/* Iterations */}
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-2">
                  Iterations (best-of)
                </label>
                <div className="flex gap-2">
                  {[1, 3, 5].map(n => (
                    <button
                      key={n}
                      onClick={() => setConfig(c => ({ ...c, iterations: n }))}
                      className={`px-3 py-1.5 rounded text-xs font-mono border transition-colors ${
                        config.iterations === n
                          ? `${COLOR_BG[color]} ${COLOR_BORDER[color]} ${COLOR_TEXT[color]}`
                          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {n}×
                    </button>
                  ))}
                </div>
              </div>

              {/* Est runtime note */}
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Clock className="w-3.5 h-3.5" />
                Estimated runtime ~{pack.estimated_runtime_s}s at default size with 4 workers
              </div>

              <button
                onClick={handleRun}
                className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border transition-colors font-medium text-sm ${COLOR_BTN[color]}`}
              >
                <Play className="w-4 h-4" />
                Run Benchmark
              </button>
            </>
          )}

          {phase === 'running' && (
            <div className="flex flex-col items-center gap-4 py-8">
              <Loader2 className={`w-8 h-8 animate-spin ${COLOR_TEXT[color]}`} />
              <p className="text-slate-400 text-sm">{progressLabel}</p>
              <p className="text-slate-600 text-xs">
                {fmtSize(config.inputSize)} {pack.input_label} · {config.workerCount} workers
              </p>
            </div>
          )}

          {phase === 'done' && result && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-emerald-400">
                  <CheckCircle className="w-5 h-5" />
                  <span className="font-medium">Benchmark Complete</span>
                </div>
                <QualityBadge score={result.run.quality_score} />
              </div>

              {result.run.measurement_warning && (
                <div className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-xs ${
                  result.run.quality_score === 'Invalid'
                    ? 'bg-red-950/40 border-red-500/30 text-red-400'
                    : 'bg-amber-950/40 border-amber-500/30 text-amber-400'
                }`}>
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  {result.run.measurement_warning}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Speedup</div>
                  <div className="text-2xl font-mono">
                    <SpeedupBadge speedup={result.run.speedup ?? 1} />
                  </div>
                </div>
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Efficiency</div>
                  <div className="text-2xl font-mono font-bold text-slate-200">
                    {result.run.efficiency?.toFixed(1) ?? '—'}%
                  </div>
                </div>
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Parallel Time</div>
                  <div className="text-sm font-mono text-slate-200">
                    {result.run.execution_time != null ? fmtMs(result.run.execution_time) : '—'}
                  </div>
                </div>
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Sequential</div>
                  <div className="text-sm font-mono text-slate-200">
                    {result.run.sequential_time != null ? fmtMs(result.run.sequential_time) : '—'}
                  </div>
                </div>
              </div>

              <button
                onClick={() => navigate(`/benchmark/${result.run.id}`)}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-sm transition-colors"
              >
                <BarChart3 className="w-4 h-4" />
                View Full Analysis
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {phase === 'error' && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-red-400">
                <XCircle className="w-5 h-5" />
                <span className="font-medium">Benchmark Failed</span>
              </div>
              {error && (
                <pre className="text-xs text-red-400/80 bg-red-950/30 border border-red-500/20 rounded p-3 overflow-auto max-h-32">
                  {error}
                </pre>
              )}
              <button
                onClick={() => { setPhase('config'); setError(null) }}
                className="w-full py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-sm transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Comparison run state ──────────────────────────────────────────────────────

interface CompareResult {
  pack: BenchmarkPack
  run: BenchmarkRun | null
  error: string | null
  status: 'pending' | 'running' | 'done' | 'error'
}

// ── Comparison Modal ──────────────────────────────────────────────────────────

interface ComparisonModalProps {
  packs: BenchmarkPack[]
  onClose: () => void
}

function ComparisonModal({ packs, onClose }: ComparisonModalProps) {
  const navigate = useNavigate()
  const [workerCount, setWorkerCount] = useState(4)
  const [iterations, setIterations] = useState(1)
  // Each pack uses its own default_input_size
  const [phase, setPhase] = useState<'config' | 'running' | 'done'>('config')
  const [results, setResults] = useState<CompareResult[]>([])

  const handleRun = async () => {
    const initial: CompareResult[] = packs.map(p => ({
      pack: p, run: null, error: null, status: 'pending',
    }))
    setResults(initial)
    setPhase('running')

    // Run each pack sequentially (avoids resource contention)
    const updated = [...initial]
    for (let i = 0; i < packs.length; i++) {
      const pack = packs[i]
      updated[i] = { ...updated[i], status: 'running' }
      setResults([...updated])

      try {
        const run = await submitBenchmark({
          workload_type: pack.workload_type as any,
          input_size: pack.default_input_size,
          worker_count: workerCount,
          iterations,
        })

        let polled: BenchmarkRun = run
        for (let attempt = 0; attempt < 120; attempt++) {
          await new Promise(r => setTimeout(r, 1000))
          polled = await fetchBenchmark(run.id)
          if (polled.status === 'completed' || polled.status === 'failed') break
        }

        if (polled.status === 'failed') throw new Error(polled.error_message || 'Failed')

        updated[i] = { ...updated[i], run: polled, status: 'done' }
      } catch (err) {
        updated[i] = {
          ...updated[i],
          error: err instanceof Error ? err.message : 'Error',
          status: 'error',
        }
      }
      setResults([...updated])
    }
    setPhase('done')
  }

  // Sort by speedup descending for the results table
  const sortedResults = [...results].sort((a, b) => {
    const sa = a.run?.speedup ?? 0
    const sb = b.run?.speedup ?? 0
    return sb - sa
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl shadow-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-slate-800 shrink-0">
          <div>
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-medium mb-1">
              <GitCompare className="w-3.5 h-3.5" />
              Comparison Mode
            </div>
            <h2 className="text-slate-100 font-semibold text-lg">
              Run {packs.length} Benchmark{packs.length > 1 ? 's' : ''} Side-by-Side
            </h2>
            <p className="text-slate-500 text-xs mt-0.5">
              {packs.map(p => p.name).join(' · ')}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 ml-4 mt-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto flex-1 space-y-5">
          {phase === 'config' && (
            <>
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-2">
                  Worker Count (applied to all packs)
                </label>
                <div className="flex gap-2">
                  {[1, 2, 4, 8].map(w => (
                    <button
                      key={w}
                      onClick={() => setWorkerCount(w)}
                      className={`px-3 py-1.5 rounded text-xs font-mono border transition-colors ${
                        workerCount === w
                          ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {w}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-400 font-medium block mb-2">Iterations</label>
                <div className="flex gap-2">
                  {[1, 3].map(n => (
                    <button
                      key={n}
                      onClick={() => setIterations(n)}
                      className={`px-3 py-1.5 rounded text-xs font-mono border transition-colors ${
                        iterations === n
                          ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {n}×
                    </button>
                  ))}
                </div>
              </div>

              {/* Pack summary */}
              <div className="space-y-2">
                {packs.map(p => {
                  const c = packColor(p.color)
                  return (
                    <div key={p.id} className={`flex items-center justify-between rounded-lg p-3 ${COLOR_BG[c]} border ${COLOR_BORDER[c]}`}>
                      <div>
                        <span className={`text-sm font-medium ${COLOR_TEXT[c]}`}>{p.name}</span>
                        <span className="text-slate-500 text-xs ml-2">{fmtSize(p.default_input_size)} {p.input_label}</span>
                      </div>
                      <GradeBadge grade={p.scalability_grade} />
                    </div>
                  )
                })}
              </div>

              <button
                onClick={handleRun}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 font-medium text-sm transition-colors"
              >
                <Play className="w-4 h-4" />
                Run Comparison
              </button>
            </>
          )}

          {(phase === 'running' || phase === 'done') && (
            <div className="space-y-3">
              {/* Progress rows */}
              <div className="space-y-2">
                {results.map(r => {
                  const c = packColor(r.pack.color)
                  return (
                    <div key={r.pack.id} className={`flex items-center gap-3 rounded-lg p-3 bg-slate-800 border ${
                      r.status === 'done' ? COLOR_BORDER[c] :
                      r.status === 'error' ? 'border-red-500/30' :
                      r.status === 'running' ? 'border-slate-600' :
                      'border-slate-700/50'
                    }`}>
                      <div className="shrink-0">
                        {r.status === 'pending' && <div className="w-4 h-4 rounded-full border border-slate-600" />}
                        {r.status === 'running' && <Loader2 className={`w-4 h-4 animate-spin ${COLOR_TEXT[c]}`} />}
                        {r.status === 'done' && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                        {r.status === 'error' && <XCircle className="w-4 h-4 text-red-400" />}
                      </div>
                      <span className={`text-sm font-medium flex-1 ${COLOR_TEXT[c]}`}>{r.pack.name}</span>
                      {r.status === 'done' && r.run && (
                        <div className="flex items-center gap-4 text-xs">
                          <span className="text-slate-400">
                            {r.run.execution_time ? fmtMs(r.run.execution_time) : '—'}
                          </span>
                          <SpeedupBadge speedup={r.run.speedup ?? 1} />
                        </div>
                      )}
                      {r.status === 'error' && (
                        <span className="text-xs text-red-400 truncate max-w-32">{r.error}</span>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Comparison table (once all done) */}
              {phase === 'done' && (
                <div className="mt-4">
                  <h3 className="text-xs text-slate-400 font-medium uppercase tracking-wider mb-3">
                    Scalability Comparison — {workerCount} Workers
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-slate-500 border-b border-slate-800">
                          <th className="pb-2 pr-3">Rank</th>
                          <th className="pb-2 pr-3">Workload</th>
                          <th className="pb-2 pr-3 text-right">Speedup</th>
                          <th className="pb-2 pr-3 text-right">Efficiency</th>
                          <th className="pb-2 pr-3 text-right">Time</th>
                          <th className="pb-2 text-right">Grade</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedResults.map((r, idx) => {
                          const c = packColor(r.pack.color)
                          return (
                            <tr key={r.pack.id} className="border-b border-slate-800/50">
                              <td className="py-2 pr-3 text-slate-500 font-mono text-xs">#{idx + 1}</td>
                              <td className="py-2 pr-3">
                                <span className={`font-medium ${COLOR_TEXT[c]}`}>{r.pack.name}</span>
                                <span className="text-slate-500 text-xs block">{r.pack.domain_tag}</span>
                              </td>
                              <td className="py-2 pr-3 text-right">
                                {r.run ? <SpeedupBadge speedup={r.run.speedup ?? 1} /> : <span className="text-red-400 text-xs">Error</span>}
                              </td>
                              <td className="py-2 pr-3 text-right text-slate-300 font-mono text-xs">
                                {r.run?.efficiency?.toFixed(1) ?? '—'}%
                              </td>
                              <td className="py-2 pr-3 text-right text-slate-400 font-mono text-xs">
                                {r.run?.execution_time ? fmtMs(r.run.execution_time) : '—'}
                              </td>
                              <td className="py-2 text-right">
                                <GradeBadge grade={r.pack.scalability_grade} />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Per-pack detail links */}
                  <div className="flex flex-wrap gap-2 mt-4">
                    {sortedResults.filter(r => r.run).map(r => {
                      const c = packColor(r.pack.color)
                      return (
                        <button
                          key={r.pack.id}
                          onClick={() => navigate(`/benchmark/${r.run!.id}`)}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs border transition-colors ${COLOR_BTN[c]}`}
                        >
                          <BarChart3 className="w-3 h-3" />
                          {r.pack.name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Pack Card ─────────────────────────────────────────────────────────────────

interface PackCardProps {
  pack: BenchmarkPack
  selected: boolean
  compareMode: boolean
  onSelect: () => void
  onRun: () => void
}

function PackCard({ pack, selected, compareMode, onSelect, onRun }: PackCardProps) {
  const color = packColor(pack.color)

  return (
    <div
      className={`relative rounded-xl border transition-all duration-200 ${COLOR_BORDER[color]} bg-slate-900 hover:bg-slate-800/60 ${
        selected ? `ring-2 ${COLOR_RING[color]} ${COLOR_BG[color]}` : ''
      }`}
    >
      {/* Comparison checkbox */}
      {compareMode && (
        <button
          onClick={onSelect}
          className={`absolute top-3 right-3 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
            selected
              ? `${COLOR_BG[color]} ${COLOR_BORDER[color]} ${COLOR_TEXT[color]}`
              : 'border-slate-600 bg-slate-800'
          }`}
        >
          {selected && <Check className="w-3 h-3" />}
        </button>
      )}

      <div className="p-5">
        {/* Domain tag */}
        <div className="flex items-center justify-between mb-3">
          <span className={`text-xs font-medium px-2 py-0.5 rounded ${COLOR_BG[color]} ${COLOR_TEXT[color]}`}>
            {pack.domain_tag}
          </span>
          <GradeBadge grade={pack.scalability_grade} />
        </div>

        {/* Name + subtitle */}
        <h3 className="text-slate-100 font-semibold text-base mb-1">{pack.name}</h3>
        <p className={`text-xs font-medium ${COLOR_TEXT[color]} mb-2`}>{pack.subtitle}</p>
        <p className="text-slate-500 text-xs mb-4">{pack.domain}</p>

        {/* Pipeline stages */}
        <div className="flex flex-wrap gap-1.5 mb-4">
          {pack.stages.map((stage, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400"
            >
              <Layers className="w-2.5 h-2.5" />
              {stage}
            </span>
          ))}
        </div>

        {/* Bottleneck */}
        <div className="mb-4">
          <BottleneckChip label={pack.expected_bottleneck_label} />
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 text-xs text-slate-500 mb-4">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            ~{pack.estimated_runtime_s}s
          </span>
          <span className="flex items-center gap-1">
            <Zap className="w-3 h-3" />
            {fmtSize(pack.default_input_size)} {pack.input_label}
          </span>
        </div>

        {/* Run button */}
        {!compareMode && (
          <button
            onClick={onRun}
            className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg border text-sm font-medium transition-colors ${COLOR_BTN[color]}`}
          >
            <Play className="w-4 h-4" />
            Run Benchmark
          </button>
        )}

        {compareMode && (
          <button
            onClick={onSelect}
            className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg border text-sm font-medium transition-colors ${
              selected
                ? `${COLOR_BG[color]} ${COLOR_BORDER[color]} ${COLOR_TEXT[color]}`
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
            }`}
          >
            {selected ? <><Check className="w-4 h-4" /> Selected</> : 'Select for Comparison'}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function BenchmarkPacks() {
  const [packs, setPacks] = useState<BenchmarkPack[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [compareMode, setCompareMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [runPack, setRunPack] = useState<BenchmarkPack | null>(null)
  const [showComparison, setShowComparison] = useState(false)

  useEffect(() => {
    fetchBenchmarkPacks()
      .then(setPacks)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectedPacks = packs.filter(p => selectedIds.has(p.id))

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Header />

      <main className="max-w-screen-xl mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-medium uppercase tracking-widest mb-2">
              <TrendingUp className="w-3.5 h-3.5" />
              Industry Standard Workloads
            </div>
            <h1 className="text-2xl font-bold text-slate-100">Benchmark Packs</h1>
            <p className="text-slate-400 text-sm mt-1">
              Production-representative workloads across ML, data engineering, observability, fintech, and recommendation systems.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {compareMode && selectedIds.size >= 2 && (
              <button
                onClick={() => setShowComparison(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 text-sm font-medium transition-colors"
              >
                <GitCompare className="w-4 h-4" />
                Compare {selectedIds.size} Packs
              </button>
            )}
            <button
              onClick={() => {
                setCompareMode(m => !m)
                setSelectedIds(new Set())
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
                compareMode
                  ? 'bg-slate-700 border-slate-600 text-slate-200'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
              }`}
            >
              <GitCompare className="w-4 h-4" />
              {compareMode ? 'Exit Compare' : 'Compare Mode'}
            </button>
          </div>
        </div>

        {/* Compare mode hint */}
        {compareMode && (
          <div className="mb-6 flex items-center gap-2 text-sm text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
            <AlertCircle className="w-4 h-4 shrink-0" />
            Select 2–5 packs to run a side-by-side comparison. Each pack runs with its default input size.
            {selectedIds.size > 0 && (
              <span className="ml-auto text-amber-300 font-medium">{selectedIds.size} selected</span>
            )}
          </div>
        )}

        {/* Content */}
        {loading && (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
          </div>
        )}

        {error && (
          <div className="flex items-center gap-3 text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
            <AlertCircle className="w-5 h-5 shrink-0" />
            {error}
          </div>
        )}

        {!loading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {packs.map(pack => (
              <PackCard
                key={pack.id}
                pack={pack}
                selected={selectedIds.has(pack.id)}
                compareMode={compareMode}
                onSelect={() => toggleSelect(pack.id)}
                onRun={() => setRunPack(pack)}
              />
            ))}
          </div>
        )}
      </main>

      {/* Modals */}
      {runPack && (
        <RunModal pack={runPack} onClose={() => setRunPack(null)} />
      )}

      {showComparison && selectedPacks.length >= 2 && (
        <ComparisonModal
          packs={selectedPacks}
          onClose={() => setShowComparison(false)}
        />
      )}
    </div>
  )
}
