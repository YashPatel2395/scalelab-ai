import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Zap, TrendingUp, BarChart2, AlertCircle, Clock,
  RefreshCw,
} from 'lucide-react'
import Header from '../components/Header'
import MetricCard from '../components/MetricCard'
import RunForm from '../components/RunForm'
import BenchmarkTable from '../components/BenchmarkTable'
import AIAnalysisPanel from '../components/AIAnalysisPanel'
import RunAnalysisModal from '../components/RunAnalysisModal'
import SpeedupChart from '../charts/SpeedupChart'
import EfficiencyChart from '../charts/EfficiencyChart'
import ExecutionTimeChart from '../charts/ExecutionTimeChart'
import ResourceChart from '../charts/ResourceChart'
import { fetchBenchmarks, fetchStats } from '../services/api'
import type { BenchmarkRunSummary, SummaryStats, ChartPoint, AIAnalysis } from '../types'

const POLL_INTERVAL_MS = 3000

export default function Dashboard() {
  const [runs, setRuns] = useState<BenchmarkRunSummary[]>([])
  const [stats, setStats] = useState<SummaryStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [analysisStore, setAnalysisStore] = useState<Record<string, AIAnalysis>>({})
  const [analysisModalRun, setAnalysisModalRun] = useState<BenchmarkRunSummary | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const hasPending = runs.some((r) => r.status === 'pending' || r.status === 'running')

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true)
    try {
      const [runsData, statsData] = await Promise.all([
        fetchBenchmarks({ limit: 200 }),
        fetchStats(),
      ])
      setRuns(runsData)
      setStats(statsData)
    } catch {
      // no-op on poll failures
    } finally {
      if (!silent) setRefreshing(false)
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadData()
  }, [loadData])

  // Auto-poll while there are pending/running runs
  useEffect(() => {
    if (hasPending) {
      pollRef.current = setInterval(() => loadData(true), POLL_INTERVAL_MS)
    } else {
      if (pollRef.current) clearInterval(pollRef.current)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [hasPending, loadData])

  const handleRunStarted = (runId: string) => {
    setSelectedRunId(runId)
    // Immediately refresh to show the pending run
    setTimeout(() => loadData(true), 500)
  }

  const handleDeleted = (id: string) => {
    setRuns((prev) => prev.filter((r) => r.id !== id))
    if (selectedRunId === id) setSelectedRunId(null)
    fetchStats().then(setStats).catch(() => {})
  }

  const handleAnalysisComplete = (runId: string, analysis: AIAnalysis) => {
    setAnalysisStore((prev) => ({ ...prev, [runId]: analysis }))
  }

  // Build chart data from completed runs
  const completedRuns = runs.filter((r) => r.status === 'completed')
  const chartPoints: ChartPoint[] = completedRuns.map((r) => ({
    worker_count: r.worker_count,
    speedup: r.speedup,
    efficiency: r.efficiency,
    execution_time: r.execution_time,
    cpu_usage: r.cpu_usage,
    memory_usage: r.memory_usage,
    workload_type: r.workload_type,
  }))

  const selectedRun = selectedRunId ? runs.find((r) => r.id === selectedRunId) : null

  return (
    <div className="min-h-screen bg-[#030712]">
      <Header />

      <main className="max-w-screen-2xl mx-auto px-6 py-8 space-y-8">
        {/* ── Hero ────────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
              Distributed Performance Intelligence
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              Run parallel workloads · Collect metrics · AI-powered bottleneck analysis
            </p>
          </div>
          <button
            onClick={() => loadData()}
            disabled={refreshing}
            className="btn-secondary"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* ── Metric cards ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
          <MetricCard
            label="Total Runs"
            value={stats?.total_runs ?? null}
            icon={<Zap />}
            accentColor="cyan"
            loading={loading}
            subtext={`${stats?.completed_runs ?? 0} completed`}
          />
          <MetricCard
            label="Best Speedup"
            value={stats?.best_speedup != null ? `${stats.best_speedup.toFixed(2)}` : null}
            unit="×"
            icon={<TrendingUp />}
            accentColor="blue"
            loading={loading}
            subtext="Across all workloads"
          />
          <MetricCard
            label="Avg Efficiency"
            value={stats?.average_efficiency != null ? `${stats.average_efficiency.toFixed(1)}` : null}
            unit="%"
            icon={<BarChart2 />}
            accentColor="green"
            loading={loading}
            subtext="Parallel efficiency"
          />
          <MetricCard
            label="Failed Runs"
            value={stats?.failed_runs ?? null}
            icon={<AlertCircle />}
            accentColor={stats && stats.failed_runs > 0 ? 'red' : 'green'}
            loading={loading}
            subtext={stats?.failed_runs === 0 ? 'All clean' : 'Check logs'}
          />
          <MetricCard
            label="Slowest Workload"
            value={
              stats?.most_expensive_workload
                ? stats.most_expensive_workload.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 12)
                : null
            }
            unit={stats?.most_expensive_time != null ? `${stats.most_expensive_time.toFixed(2)}s` : undefined}
            icon={<Clock />}
            accentColor="amber"
            loading={loading}
            subtext="Longest parallel run"
          />
        </div>

        {/* ── Main layout: form + analysis ─────────────────────────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Run form */}
          <div className="xl:col-span-1">
            <RunForm onRunStarted={handleRunStarted} />
          </div>

          {/* AI analysis for selected run */}
          <div className="xl:col-span-2">
            {selectedRun ? (
              <AIAnalysisPanel
                benchmarkId={selectedRun.id}
                existingAnalysis={analysisStore[selectedRun.id] ?? null}
                benchmarkStatus={selectedRun.status}
                onAnalysisComplete={(a) => handleAnalysisComplete(selectedRun.id, a)}
              />
            ) : (
              <div className="card p-6 h-full flex flex-col items-center justify-center gap-3 text-center min-h-[200px]">
                <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center">
                  <Zap className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-slate-400 text-sm font-medium">No run selected</p>
                  <p className="text-slate-600 text-xs mt-0.5">
                    Submit a benchmark run or click a row in the history table to load AI analysis.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Charts ───────────────────────────────────────────────────────── */}
        <div>
          <div className="mb-4">
            <h2 className="text-slate-100 font-semibold text-sm">Scalability Analysis</h2>
            <p className="text-slate-500 text-xs mt-0.5">
              Aggregated from {completedRuns.length} completed runs
            </p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <SpeedupChart data={chartPoints} />
            <EfficiencyChart data={chartPoints} />
            <ExecutionTimeChart data={chartPoints} />
            <ResourceChart data={chartPoints} />
          </div>
        </div>

        {/* ── Benchmark table ───────────────────────────────────────────────── */}
        <div>
          <BenchmarkTable
            runs={runs}
            onDeleted={handleDeleted}
            onViewAnalysis={(run) => setAnalysisModalRun(run)}
            loading={loading}
          />
        </div>
      </main>

      {/* Analysis modal */}
      {analysisModalRun && (
        <RunAnalysisModal
          runSummary={analysisModalRun}
          onClose={() => setAnalysisModalRun(null)}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-16 py-6 text-center">
        <p className="text-xs text-slate-600">
          ScaleLab AI · Distributed Performance Intelligence Platform ·{' '}
          <span className="font-mono">v1.0.0</span>
        </p>
      </footer>
    </div>
  )
}
