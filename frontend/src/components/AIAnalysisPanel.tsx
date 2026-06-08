import { useState } from 'react'
import { Brain, Loader2, ChevronDown, ChevronRight, AlertTriangle, CheckCircle, Cpu, HardDrive, Radio } from 'lucide-react'
import type { AIAnalysis } from '../types'
import { analyzeBottleneck } from '../services/api'
import { clsx } from 'clsx'

interface Props {
  benchmarkId: string
  existingAnalysis: AIAnalysis | null
  benchmarkStatus: string
  onAnalysisComplete: (analysis: AIAnalysis) => void
}

const BOTTLENECK_CONFIG = {
  cpu_bound: {
    label: 'CPU Bound',
    icon: Cpu,
    color: 'text-amber-400',
    bg: 'bg-amber-950',
    border: 'border-amber-800',
  },
  memory_bound: {
    label: 'Memory Bound',
    icon: HardDrive,
    color: 'text-purple-400',
    bg: 'bg-purple-950',
    border: 'border-purple-800',
  },
  communication_bound: {
    label: 'Communication Bound',
    icon: Radio,
    color: 'text-blue-400',
    bg: 'bg-blue-950',
    border: 'border-blue-800',
  },
  well_balanced: {
    label: 'Well Balanced',
    icon: CheckCircle,
    color: 'text-emerald-400',
    bg: 'bg-emerald-950',
    border: 'border-emerald-800',
  },
  unknown: {
    label: 'Unknown',
    icon: AlertTriangle,
    color: 'text-slate-400',
    bg: 'bg-slate-800',
    border: 'border-slate-700',
  },
}

export default function AIAnalysisPanel({
  benchmarkId,
  existingAnalysis,
  benchmarkStatus,
  onAnalysisComplete,
}: Props) {
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(existingAnalysis)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    speedup: true,
    bottleneck: true,
    recommendations: true,
    complexity: false,
  })

  const handleAnalyze = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await analyzeBottleneck(benchmarkId)
      setAnalysis(result)
      onAnalysisComplete(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const toggle = (key: string) =>
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }))

  const canAnalyze = benchmarkStatus === 'completed'

  if (!analysis) {
    return (
      <div className="card p-6 flex flex-col items-center gap-4 text-center">
        <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
          <Brain className="w-6 h-6 text-purple-400" />
        </div>
        <div>
          <h3 className="text-slate-100 font-semibold text-sm">AI Bottleneck Analysis</h3>
          <p className="text-slate-500 text-xs mt-1 max-w-xs">
            {canAnalyze
              ? "Analyze this benchmark with Amdahl's Law, complexity theory, and workload profiling."
              : `Benchmark must be completed before analysis. Current status: ${benchmarkStatus}.`}
          </p>
        </div>

        {error && (
          <div className="w-full px-3 py-2 rounded-lg bg-red-950 border border-red-800 text-red-400 text-xs text-left">
            {error}
          </div>
        )}

        <button
          onClick={handleAnalyze}
          disabled={loading || !canAnalyze}
          className="btn-primary"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Analyzing…
            </>
          ) : (
            <>
              <Brain className="w-4 h-4" />
              Analyze Bottleneck
            </>
          )}
        </button>
      </div>
    )
  }

  const cfg = BOTTLENECK_CONFIG[analysis.bottleneck_type] ?? BOTTLENECK_CONFIG.unknown
  const IconComp = cfg.icon

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="w-4 h-4 text-purple-400" />
          <h3 className="text-slate-100 font-semibold text-sm">AI Analysis</h3>
          <span className="text-xs text-slate-600 font-mono">
            {analysis.provider} / {analysis.model}
          </span>
        </div>
        <button onClick={handleAnalyze} disabled={loading || !canAnalyze} className="btn-secondary text-xs py-1 px-3">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Re-analyze'}
        </button>
      </div>

      <div className="p-5 space-y-4">
        {/* Bottleneck classification */}
        <div className={clsx('rounded-lg border px-4 py-3 flex items-start gap-3', cfg.bg, cfg.border)}>
          <IconComp className={clsx('w-5 h-5 mt-0.5 flex-shrink-0', cfg.color)} />
          <div>
            <div className={clsx('font-semibold text-sm', cfg.color)}>{cfg.label}</div>
            <p className="text-slate-400 text-xs mt-0.5">{analysis.bottleneck_summary}</p>
          </div>
          {analysis.theoretical_max_speedup && (
            <div className="ml-auto text-right flex-shrink-0">
              <div className="text-xs text-slate-500">Amdahl ceiling</div>
              <div className="font-mono font-semibold text-sm text-slate-200">
                {analysis.theoretical_max_speedup.toFixed(2)}×
              </div>
            </div>
          )}
        </div>

        {/* Speedup explanation */}
        <Section
          title="Speedup Analysis"
          open={expanded.speedup}
          onToggle={() => toggle('speedup')}
        >
          <p className="text-xs text-slate-400 leading-relaxed">{analysis.speedup_explanation}</p>
          {analysis.parallel_fraction_estimate && (
            <div className="mt-3 flex items-center gap-3">
              <span className="text-xs text-slate-500">Parallel fraction (p):</span>
              <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full transition-all"
                  style={{ width: `${analysis.parallel_fraction_estimate * 100}%` }}
                />
              </div>
              <span className="font-mono text-xs text-cyan-400">
                {(analysis.parallel_fraction_estimate * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </Section>

        {/* Bottleneck details */}
        <Section
          title="Bottleneck Details"
          open={expanded.bottleneck}
          onToggle={() => toggle('bottleneck')}
        >
          <p className="text-xs text-slate-400 leading-relaxed">{analysis.bottleneck_details}</p>
        </Section>

        {/* Recommendations */}
        <Section
          title="Optimization Recommendations"
          open={expanded.recommendations}
          onToggle={() => toggle('recommendations')}
        >
          <ul className="space-y-2">
            {analysis.optimization_recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                <span className="w-4 h-4 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center flex-shrink-0 font-mono text-[10px] mt-0.5">
                  {i + 1}
                </span>
                <span className="leading-relaxed">{rec}</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* Complexity */}
        <Section
          title="Complexity Interpretation"
          open={expanded.complexity}
          onToggle={() => toggle('complexity')}
        >
          <p className="text-xs text-slate-400 leading-relaxed font-mono">
            {analysis.complexity_interpretation}
          </p>
        </Section>

        {/* Confidence indicator */}
        <div className="flex items-center justify-end gap-2 pt-1">
          <span className="text-xs text-slate-600">Analysis confidence:</span>
          <span
            className={clsx(
              'badge border',
              analysis.confidence === 'high'
                ? 'text-emerald-400 bg-emerald-950 border-emerald-800'
                : analysis.confidence === 'medium'
                ? 'text-amber-400 bg-amber-950 border-amber-800'
                : 'text-red-400 bg-red-950 border-red-800'
            )}
          >
            {analysis.confidence}
          </span>
        </div>
      </div>
    </div>
  )
}

function Section({
  title,
  open,
  onToggle,
  children,
}: {
  title: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-slate-800/40 transition-colors"
      >
        <span className="text-xs font-medium text-slate-300">{title}</span>
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
        )}
      </button>
      {open && <div className="px-4 pb-3 pt-1">{children}</div>}
    </div>
  )
}
