import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, PieChart, Pie, Cell,
} from 'recharts'
import {
  FlaskConical, TrendingUp, GitCompare, Cpu, Loader2, AlertCircle,
  ChevronDown, ChevronUp, RefreshCw, Layers, CheckCircle, Award, Download,
} from 'lucide-react'
import Header from '../components/Header'
import {
  fetchExperiments,
  createExperiment,
  compareExperiment,
  fetchBenchmarks,
  addRunsToExperiment,
  predictScalability,
  recommendWorkers,
  fetchMPITiming,
  createScalingStudy,
  generateCertification,
} from '../services/api'
import type {
  Experiment,
  ExperimentComparison,
  ScalabilityPrediction,
  RecommendationResult,
  BenchmarkRunSummary,
  MPITiming,
  ScalingStudyResponse,
  CertificationReport,
} from '../types'

type Tab = 'theory' | 'experiments' | 'mpi'

// ── Helpers ────────────────────────────────────────────────────────────────

function amdahlSpeedup(p: number, P: number): number {
  return 1 / ((1 - p) + p / P)
}
function gustafsonSpeedup(alpha: number, P: number): number {
  return P - alpha * (P - 1)
}

const WORKER_RANGE = [1, 2, 4, 6, 8, 12, 16, 24, 32]

// ── Theory Comparison tab ─────────────────────────────────────────────────

function TheoryTab() {
  const [parallelFraction, setParallelFraction] = useState(0.85)
  const [serialOverhead, setSerialOverhead] = useState(0.15)
  const [prediction, setPrediction] = useState<ScalabilityPrediction | null>(null)
  const [recommendation, setRecommendation] = useState<RecommendationResult | null>(null)
  const [loadingPred, setLoadingPred] = useState(false)
  const [workloadType, setWorkloadType] = useState('image_processing')
  const [inputSize, setInputSize] = useState(2048)
  const [predError, setPredError] = useState<string | null>(null)

  // Scaling study state
  const [studyWorkerCounts] = useState([1, 2, 4, 8])
  const [runningStudy, setRunningStudy] = useState(false)
  const [studyResult, setStudyResult] = useState<ScalingStudyResponse | null>(null)
  const [studyError, setStudyError] = useState<string | null>(null)

  // Certification state
  const [certReport, setCertReport] = useState<CertificationReport | null>(null)
  const [certLoading, setCertLoading] = useState(false)
  const [certError, setCertError] = useState<string | null>(null)

  const handleCertification = async (runIds: string[], displayName: string) => {
    setCertLoading(true)
    setCertError(null)
    setCertReport(null)
    try {
      const report = await generateCertification(runIds, displayName)
      setCertReport(report)
    } catch (err) {
      setCertError(err instanceof Error ? err.message : 'Certification failed')
    } finally {
      setCertLoading(false)
    }
  }

  const handleScalingStudy = async () => {
    setStudyError(null)
    setStudyResult(null)
    setCertReport(null)
    setRunningStudy(true)
    try {
      const result = await createScalingStudy({
        workload_type: workloadType,
        input_size: inputSize,
        worker_counts: studyWorkerCounts,
        iterations: 1,
      })
      setStudyResult(result)
      // Auto-refit after a delay to let runs start
      setTimeout(() => fetchPrediction(), 2000)
    } catch (err) {
      setStudyError(err instanceof Error ? err.message : 'Failed to start scaling study')
    } finally {
      setRunningStudy(false)
    }
  }

  const insufficientData =
    prediction?.model_used === 'insufficient_data' ||
    (prediction?.r_squared !== null && prediction?.r_squared !== undefined && prediction.r_squared < 0.3)

  const chartData = WORKER_RANGE.map((P) => ({
    workers: P,
    amdahl: +amdahlSpeedup(parallelFraction, P).toFixed(3),
    gustafson: +gustafsonSpeedup(serialOverhead, P).toFixed(3),
    ideal: P,
  }))

  const fetchPrediction = useCallback(async () => {
    setLoadingPred(true)
    setPredError(null)
    try {
      const [pred, rec] = await Promise.all([
        predictScalability(workloadType, inputSize, WORKER_RANGE),
        recommendWorkers(workloadType, inputSize),
      ])
      setPrediction(pred)
      setRecommendation(rec)
    } catch (e: unknown) {
      setPredError(e instanceof Error ? e.message : 'Failed to fetch prediction')
    } finally {
      setLoadingPred(false)
    }
  }, [workloadType, inputSize])

  useEffect(() => { fetchPrediction() }, [fetchPrediction])

  const predChartData = prediction
    ? WORKER_RANGE.map((P) => {
        const pt = prediction.predictions.find((p) => p.worker_count === P)
        return {
          workers: P,
          amdahl: +amdahlSpeedup(parallelFraction, P).toFixed(3),
          gustafson: +gustafsonSpeedup(serialOverhead, P).toFixed(3),
          fitted: pt ? +pt.predicted_speedup.toFixed(3) : null,
          ideal: P,
        }
      })
    : chartData

  return (
    <div className="space-y-8">
      {/* Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
          <h3 className="text-slate-200 font-medium text-sm">Law Parameters</h3>
          <div>
            <label className="text-slate-400 text-xs block mb-1">
              Amdahl Parallel Fraction (p = {(parallelFraction * 100).toFixed(0)}%)
            </label>
            <input
              type="range" min="0.1" max="0.99" step="0.01"
              value={parallelFraction}
              onChange={(e) => setParallelFraction(+e.target.value)}
              className="w-full accent-cyan-500"
            />
            <p className="text-slate-500 text-xs mt-1">
              Theoretical max speedup: {(1 / (1 - parallelFraction)).toFixed(1)}×
            </p>
          </div>
          <div>
            <label className="text-slate-400 text-xs block mb-1">
              Gustafson Serial Overhead (α = {(serialOverhead * 100).toFixed(0)}%)
            </label>
            <input
              type="range" min="0.01" max="0.9" step="0.01"
              value={serialOverhead}
              onChange={(e) => setSerialOverhead(+e.target.value)}
              className="w-full accent-purple-500"
            />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
          <h3 className="text-slate-200 font-medium text-sm">Fitted Prediction (from real data)</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-slate-400 text-xs block mb-1">Workload</label>
              <select
                value={workloadType}
                onChange={(e) => setWorkloadType(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-slate-200 text-xs"
              >
                <option value="matrix_multiplication">Matrix Multiply</option>
                <option value="parallel_sort">Parallel Sort</option>
                <option value="image_processing">Image Processing</option>
                <option value="graph_bfs">Graph BFS</option>
              </select>
            </div>
            <div>
              <label className="text-slate-400 text-xs block mb-1">Input Size</label>
              <input
                type="number"
                value={inputSize}
                onChange={(e) => setInputSize(+e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-slate-200 text-xs"
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={fetchPrediction}
              disabled={loadingPred}
              className="flex items-center gap-2 px-3 py-1.5 bg-cyan-600/20 border border-cyan-500/40 rounded text-cyan-400 text-xs hover:bg-cyan-600/30 transition-colors disabled:opacity-50"
            >
              {loadingPred ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              Refit from data
            </button>
            <button
              onClick={handleScalingStudy}
              disabled={runningStudy}
              className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600/20 border border-emerald-500/40 rounded text-emerald-400 text-xs hover:bg-emerald-600/30 transition-colors disabled:opacity-50"
              title={`Submit benchmarks at workers ${studyWorkerCounts.join(', ')} — same input size — and group in an experiment`}
            >
              {runningStudy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Layers className="w-3.5 h-3.5" />}
              Generate Scaling Study
            </button>
          </div>

          {/* Scaling study result */}
          {studyResult && (
            <div className="flex items-start gap-2 px-3 py-2 rounded bg-emerald-950/30 border border-emerald-700/30 text-xs">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-emerald-300 font-medium">
                  Scaling study submitted — {studyResult.run_ids.length} runs at workers {studyResult.worker_counts.join(', ')}
                </p>
                <p className="text-emerald-600 mt-0.5">
                  Runs are executing in the background. Click "Refit from data" once they complete, then generate a Certification Report.
                </p>
                <button
                  onClick={() => handleCertification(
                    studyResult.run_ids,
                    studyResult.workload_type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
                  )}
                  disabled={certLoading}
                  className="mt-2 flex items-center gap-1.5 px-3 py-1.5 bg-amber-600/20 border border-amber-500/40 rounded text-amber-400 text-xs hover:bg-amber-600/30 transition-colors disabled:opacity-50"
                >
                  {certLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Award className="w-3 h-3" />}
                  Generate Certification Report
                </button>
              </div>
            </div>
          )}
          {studyError && (
            <p className="text-red-400 text-xs flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" /> {studyError}
            </p>
          )}
          {certError && (
            <p className="text-red-400 text-xs flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" /> {certError}
            </p>
          )}

          {/* Insufficient data guardrail */}
          {prediction && insufficientData && (
            <div className="flex items-start gap-2 px-3 py-2 rounded bg-amber-950/30 border border-amber-700/30 text-xs">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-amber-300 font-medium">Insufficient data for reliable prediction</p>
                <p className="text-amber-600 mt-0.5">{prediction.recommendation}</p>
                <p className="text-amber-700 mt-1">
                  Use <strong className="text-amber-500">Generate Scaling Study</strong> above to collect clean data at this input size.
                </p>
              </div>
            </div>
          )}

          {prediction && !insufficientData && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-800 rounded p-2">
                <span className="text-slate-500">Model</span>
                <p className="text-slate-200 font-mono mt-0.5">{prediction.model_used}</p>
              </div>
              <div className="bg-slate-800 rounded p-2">
                <span className="text-slate-500">R²</span>
                <p className={`font-mono mt-0.5 ${
                  (prediction.r_squared ?? 0) >= 0.8 ? 'text-emerald-400' :
                  (prediction.r_squared ?? 0) >= 0.5 ? 'text-amber-400' :
                  'text-red-400'
                }`}>
                  {prediction.r_squared != null ? prediction.r_squared.toFixed(3) : '—'}
                </p>
              </div>
              <div className="bg-slate-800 rounded p-2">
                <span className="text-slate-500">Data points</span>
                <p className="text-slate-200 font-mono mt-0.5">{prediction.data_points_used}</p>
              </div>
              <div className="bg-slate-800 rounded p-2">
                <span className="text-slate-500">Max speedup</span>
                <p className="text-slate-200 font-mono mt-0.5">
                  {prediction.theoretical_max_speedup ?? '∞'}×
                </p>
              </div>
            </div>
          )}
          {predError && (
            <p className="text-red-400 text-xs flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" /> {predError}
            </p>
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
        <h3 className="text-slate-200 font-medium text-sm mb-4">Speedup vs Worker Count</h3>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={predChartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="workers" stroke="#475569" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Workers', position: 'insideBottom', offset: -4, fill: '#64748b', fontSize: 11 }} />
            <YAxis stroke="#475569" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Speedup', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 12 }}
              labelStyle={{ color: '#94a3b8' }}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
            <Line type="monotone" dataKey="ideal" stroke="#334155" strokeDasharray="4 4" dot={false} name="Ideal (linear)" />
            <Line type="monotone" dataKey="amdahl" stroke="#22d3ee" strokeWidth={2} dot={false} name={`Amdahl (p=${(parallelFraction*100).toFixed(0)}%)`} />
            <Line type="monotone" dataKey="gustafson" stroke="#a78bfa" strokeWidth={2} dot={false} name={`Gustafson (α=${(serialOverhead*100).toFixed(0)}%)`} />
            {prediction && (
              <Line type="monotone" dataKey="fitted" stroke="#34d399" strokeWidth={2} strokeDasharray="6 2" dot={{ r: 3, fill: '#34d399' }} name="Fitted (real data)" />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Recommendation */}
      {recommendation && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
          <h3 className="text-slate-200 font-medium text-sm mb-3">Worker Count Recommendation</h3>
          <div className="flex flex-wrap gap-4 mb-4">
            <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg px-4 py-3">
              <p className="text-slate-500 text-xs">Optimal Workers</p>
              <p className="text-cyan-400 text-2xl font-bold">{recommendation.optimal_worker_count}</p>
            </div>
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-4 py-3">
              <p className="text-slate-500 text-xs">Expected Speedup</p>
              <p className="text-emerald-400 text-2xl font-bold">{recommendation.expected_speedup.toFixed(2)}×</p>
            </div>
            <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg px-4 py-3">
              <p className="text-slate-500 text-xs">Expected Efficiency</p>
              <p className="text-purple-400 text-2xl font-bold">{(recommendation.expected_efficiency * 100).toFixed(1)}%</p>
            </div>
          </div>
          <p className="text-slate-400 text-xs leading-relaxed">{recommendation.reasoning}</p>
        </div>
      )}

      {/* Certification report */}
      {certLoading && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 flex items-center gap-2 text-slate-400 text-sm">
          <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
          Generating certification report…
        </div>
      )}
      {certReport && (
        <ScalingCertificationReport report={certReport} />
      )}

      {/* Theory explanation */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <h4 className="text-cyan-400 font-medium text-xs mb-2">Amdahl's Law</h4>
          <p className="text-slate-500 text-xs leading-relaxed mb-2">
            S(P) = 1 / ((1 − p) + p/P) — speedup is bounded by the serial fraction.
            Even with infinite cores, speedup cannot exceed 1/(1−p).
            Models <strong className="text-slate-300">strong scaling</strong>: fixed problem size, more workers.
          </p>
          <p className="text-slate-600 font-mono text-xs">
            {parallelFraction >= 0.9
              ? `At p=${(parallelFraction*100).toFixed(0)}%, speedup ceiling = ${(1/(1-parallelFraction)).toFixed(1)}× — highly parallelisable.`
              : `At p=${(parallelFraction*100).toFixed(0)}%, speedup ceiling = ${(1/(1-parallelFraction)).toFixed(1)}× — serial bottleneck dominates.`}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <h4 className="text-purple-400 font-medium text-xs mb-2">Gustafson's Law</h4>
          <p className="text-slate-500 text-xs leading-relaxed mb-2">
            S(P) = P − α(P − 1) — speedup scales with cores when problem size grows proportionally.
            No theoretical ceiling; models <strong className="text-slate-300">weak scaling</strong>:
            each worker gets more work.
          </p>
          <p className="text-slate-600 font-mono text-xs">
            At α={serialOverhead.toFixed(2)}, {WORKER_RANGE[WORKER_RANGE.length - 2]} workers
            → {gustafsonSpeedup(serialOverhead, WORKER_RANGE[WORKER_RANGE.length - 2]).toFixed(1)}× speedup.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Scaling Certification Report (inline display) ─────────────────────────

const GRADE_COLORS_RESEARCH: Record<string, string> = {
  'A+': 'text-emerald-400 border-emerald-400',
  'A': 'text-emerald-400 border-emerald-400',
  'B': 'text-cyan-400 border-cyan-400',
  'C': 'text-amber-400 border-amber-400',
  'D': 'text-orange-400 border-orange-400',
  'F': 'text-red-400 border-red-400',
}

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

  const iframe = document.createElement('iframe')
  iframe.style.cssText = 'position:fixed;left:-9999px;top:0;width:860px;height:1px;border:none'
  document.body.appendChild(iframe)

  const doc = iframe.contentDocument!
  doc.open(); doc.write(htmlContent); doc.close()

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

function ScalingCertificationReport({ report }: { report: CertificationReport }) {
  const gradeColor = GRADE_COLORS_RESEARCH[report.certification.grade] ?? 'text-slate-400 border-slate-400'
  const effPct = report.analysis.best_efficiency_pct

  return (
    <div className="bg-slate-900 border border-amber-700/30 rounded-lg p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-slate-200 font-medium text-sm flex items-center gap-2">
          <Award className="w-4 h-4 text-amber-400" />
          Scalability Certification — {report.workload_name}
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => exportCertificatePDF(report.export_html, `scalelab-cert-${report.workload_type}.pdf`)}
            className="flex items-center gap-1 px-2.5 py-1 text-xs bg-cyan-500/10 border border-cyan-500/30 rounded text-cyan-400 hover:bg-cyan-500/20 transition-colors font-medium"
          >
            <Download className="w-3 h-3" /> PDF
          </button>
          <button
            onClick={() => downloadFile(report.export_html, `cert-${report.workload_type}.html`, 'text/html')}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded text-slate-400 hover:text-slate-200 transition-colors"
          >
            <Download className="w-3 h-3" /> HTML
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className={`flex flex-col items-center justify-center border-2 rounded-xl p-4 ${gradeColor}`}>
          <span className="text-4xl font-black">{report.certification.grade}</span>
          <span className="text-xs mt-1 opacity-70">{report.certification.grade_description}</span>
        </div>
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
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-slate-800 border border-slate-700 rounded-lg p-3">
            <p className="text-xs text-slate-500 mb-1">{label}</p>
            <p className={`text-xl font-bold font-mono ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      <p className="text-slate-400 text-xs leading-relaxed">{report.certification.rationale}</p>

      {/* Scaling data table */}
      {report.scaling_data.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/50">
                <th className="px-3 py-2 text-left text-slate-500">Workers</th>
                <th className="px-3 py-2 text-right text-slate-500">Time (s)</th>
                <th className="px-3 py-2 text-right text-slate-500">Speedup</th>
                <th className="px-3 py-2 text-right text-slate-500">Efficiency</th>
              </tr>
            </thead>
            <tbody>
              {report.scaling_data.map((row) => (
                <tr key={row.worker_count} className="border-b border-slate-800/50">
                  <td className="px-3 py-1.5 font-mono text-slate-300">{row.worker_count}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-400">{row.execution_time_s.toFixed(4)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-cyan-400">{row.speedup.toFixed(2)}×</td>
                  <td className={`px-3 py-1.5 text-right font-mono ${
                    row.efficiency_pct >= 80 ? 'text-emerald-400'
                    : row.efficiency_pct >= 50 ? 'text-amber-400'
                    : 'text-red-400'
                  }`}>{row.efficiency_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Experiments tab ───────────────────────────────────────────────────────

function ExperimentsTab() {
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [benchmarks, setBenchmarks] = useState<BenchmarkRunSummary[]>([])
  const [comparison, setComparison] = useState<ExperimentComparison | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [selectedExp, setSelectedExp] = useState<string | null>(null)
  const [expandedExp, setExpandedExp] = useState<string | null>(null)
  const [selectedRuns, setSelectedRuns] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    try {
      const [exps, runs] = await Promise.all([
        fetchExperiments(),
        fetchBenchmarks({ limit: 200, status: 'completed' }),
      ])
      setExperiments(exps)
      setBenchmarks(runs)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      await createExperiment({ name: newName.trim() })
      setNewName('')
      await load()
    } catch {
      /* noop */
    } finally {
      setCreating(false)
    }
  }

  const handleAddRuns = async (expId: string) => {
    if (selectedRuns.size === 0) return
    try {
      await addRunsToExperiment(expId, Array.from(selectedRuns))
      setSelectedRuns(new Set())
      await load()
    } catch { /* noop */ }
  }

  const handleCompare = async (expId: string) => {
    try {
      const cmp = await compareExperiment(expId)
      setComparison(cmp)
      setSelectedExp(expId)
    } catch { /* noop */ }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 text-slate-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-red-400 text-sm py-10">
        <AlertCircle className="w-4 h-4" /> {error}
      </div>
    )
  }

  const compChartData = comparison?.runs
    .filter((r) => r.status === 'completed')
    .map((r) => ({
      label: `${r.worker_count}w / ${r.input_size}`,
      speedup: r.speedup ?? 0,
      efficiency: r.efficiency ?? 0,
    }))

  return (
    <div className="space-y-6">
      {/* Create experiment */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <h3 className="text-slate-200 font-medium text-sm mb-3">New Experiment</h3>
        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="Experiment name…"
            className="flex-1 bg-slate-800 border border-slate-700 rounded px-3 py-2 text-slate-200 text-xs placeholder:text-slate-600"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newName.trim()}
            className="px-4 py-2 bg-cyan-600/20 border border-cyan-500/40 rounded text-cyan-400 text-xs hover:bg-cyan-600/30 transition-colors disabled:opacity-50"
          >
            {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Create'}
          </button>
        </div>
      </div>

      {/* Experiment list */}
      <div className="space-y-3">
        {experiments.length === 0 && (
          <p className="text-slate-600 text-sm text-center py-8">No experiments yet. Create one above.</p>
        )}
        {experiments.map((exp) => (
          <div key={exp.id} className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3">
              <div>
                <span className="text-slate-200 text-sm font-medium">{exp.name}</span>
                <span className="text-slate-500 text-xs ml-3">{exp.run_ids.length} runs</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleCompare(exp.id)}
                  className="px-2.5 py-1 rounded text-xs text-purple-400 border border-purple-500/30 hover:bg-purple-500/10 transition-colors"
                >
                  Compare
                </button>
                <button
                  onClick={() => setExpandedExp(expandedExp === exp.id ? null : exp.id)}
                  className="p-1 text-slate-500 hover:text-slate-300"
                >
                  {expandedExp === exp.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {expandedExp === exp.id && (
              <div className="border-t border-slate-800 px-4 py-3 space-y-3">
                <p className="text-slate-500 text-xs">Add completed runs to this experiment:</p>
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {benchmarks.map((run) => (
                    <label key={run.id} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedRuns.has(run.id)}
                        onChange={(e) => {
                          const s = new Set(selectedRuns)
                          e.target.checked ? s.add(run.id) : s.delete(run.id)
                          setSelectedRuns(s)
                        }}
                        className="accent-cyan-500"
                      />
                      <span className="text-slate-400 text-xs font-mono">
                        {run.workload_type} · {run.input_size}sz · {run.worker_count}w
                        {run.speedup ? ` · ${run.speedup.toFixed(2)}×` : ''}
                      </span>
                    </label>
                  ))}
                </div>
                <button
                  onClick={() => handleAddRuns(exp.id)}
                  disabled={selectedRuns.size === 0}
                  className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded text-slate-300 text-xs hover:border-cyan-500/40 disabled:opacity-40 transition-colors"
                >
                  Add {selectedRuns.size} run{selectedRuns.size !== 1 ? 's' : ''}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Comparison view */}
      {comparison && selectedExp && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
          <h3 className="text-slate-200 font-medium text-sm">
            Comparison: <span className="text-cyan-400">{comparison.experiment_name}</span>
          </h3>

          {comparison.summary.completed_runs > 0 && (
            <div className="flex flex-wrap gap-3">
              <div className="bg-slate-800 rounded px-3 py-2 text-xs">
                <span className="text-slate-500">Best speedup</span>
                <p className="text-emerald-400 font-bold text-lg">{comparison.summary.best_speedup?.toFixed(2)}×</p>
              </div>
              <div className="bg-slate-800 rounded px-3 py-2 text-xs">
                <span className="text-slate-500">Avg speedup</span>
                <p className="text-cyan-400 font-bold text-lg">{comparison.summary.avg_speedup?.toFixed(2)}×</p>
              </div>
              <div className="bg-slate-800 rounded px-3 py-2 text-xs">
                <span className="text-slate-500">Avg efficiency</span>
                <p className="text-purple-400 font-bold text-lg">{comparison.summary.avg_efficiency?.toFixed(1)}%</p>
              </div>
            </div>
          )}

          {compChartData && compChartData.length > 0 && (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={compChartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="label" stroke="#475569" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis stroke="#475569" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                <Bar dataKey="speedup" fill="#22d3ee" name="Speedup" radius={[3, 3, 0, 0]} />
                <Bar dataKey="efficiency" fill="#a78bfa" name="Efficiency %" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </div>
  )
}

// ── MPI tab ───────────────────────────────────────────────────────────────

function MPITab() {
  const [nProcesses, setNProcesses] = useState(4)
  const [matrixSize, setMatrixSize] = useState(512)
  const [result, setResult] = useState<MPITiming | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchMPITiming(nProcesses, matrixSize)
      setResult(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  const pieData = result
    ? [
        { name: 'Computation', value: result.breakdown_pct.computation, color: '#22d3ee' },
        { name: 'Communication', value: result.breakdown_pct.communication, color: '#f59e0b' },
        { name: 'Synchronisation', value: result.breakdown_pct.synchronization, color: '#a78bfa' },
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
        <h3 className="text-slate-200 font-medium text-sm">MPI Matrix Multiply Timing</h3>
        <p className="text-slate-500 text-xs">
          Runs <code className="bg-slate-800 px-1 rounded">mpiexec -n P mpi_matrix_multiply.py N</code> and
          measures computation / communication / synchronisation breakdown.
          Falls back to modelled estimates when MPI is not installed.
        </p>
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="text-slate-400 text-xs block mb-1">Processes</label>
            <input
              type="number" min="1" max="32" value={nProcesses}
              onChange={(e) => setNProcesses(+e.target.value)}
              className="w-24 bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-slate-200 text-xs"
            />
          </div>
          <div>
            <label className="text-slate-400 text-xs block mb-1">Matrix size (N×N)</label>
            <select
              value={matrixSize}
              onChange={(e) => setMatrixSize(+e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-slate-200 text-xs"
            >
              {[64, 128, 256, 512, 1024, 2048].map((n) => (
                <option key={n} value={n}>{n}×{n}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={run}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-1.5 bg-cyan-600/20 border border-cyan-500/40 rounded text-cyan-400 text-xs hover:bg-cyan-600/30 transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Cpu className="w-3.5 h-3.5" />}
              Run MPI Benchmark
            </button>
          </div>
        </div>

        {error && (
          <p className="text-red-400 text-xs flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5" /> {error}
          </p>
        )}
      </div>

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Timings */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-slate-200 font-medium text-sm">Timing Breakdown</h4>
              {!result.mpi_available && (
                <span className="text-amber-400 text-xs border border-amber-500/30 bg-amber-500/10 rounded px-2 py-0.5">
                  Modelled (no MPI)
                </span>
              )}
              {result.mpi_available && (
                <span className="text-emerald-400 text-xs border border-emerald-500/30 bg-emerald-500/10 rounded px-2 py-0.5">
                  Real MPI
                </span>
              )}
            </div>
            <div className="space-y-2">
              {[
                { label: 'Computation', value: result.computation_time, pct: result.breakdown_pct.computation, color: 'bg-cyan-500' },
                { label: 'Communication', value: result.communication_time, pct: result.breakdown_pct.communication, color: 'bg-amber-500' },
                { label: 'Synchronisation', value: result.synchronization_time, pct: result.breakdown_pct.synchronization, color: 'bg-purple-500' },
              ].map((row) => (
                <div key={row.label}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">{row.label}</span>
                    <span className="text-slate-300 font-mono">
                      {(row.value * 1000).toFixed(2)} ms ({row.pct}%)
                    </span>
                  </div>
                  <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div className={`h-full ${row.color} rounded-full`} style={{ width: `${row.pct}%` }} />
                  </div>
                </div>
              ))}
              <div className="pt-2 border-t border-slate-800 flex justify-between text-xs">
                <span className="text-slate-500">Total</span>
                <span className="text-slate-200 font-mono">{(result.total_time * 1000).toFixed(2)} ms</span>
              </div>
            </div>
          </div>

          {/* Pie chart */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
            <h4 className="text-slate-200 font-medium text-sm mb-2">Phase Distribution</h4>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value">
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number) => [`${v}%`, '']}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Theory */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-3">
        <h4 className="text-slate-200 font-medium text-sm">MPI Execution Model</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="space-y-1">
            <p className="text-cyan-400 font-medium">Scatter / Gather</p>
            <p className="text-slate-500">Rank 0 distributes A row-slabs to all ranks (Scatter), gathers result slabs back (Gather). Cost: O(N²/P) bytes × 2.</p>
          </div>
          <div className="space-y-1">
            <p className="text-amber-400 font-medium">Broadcast</p>
            <p className="text-slate-500">Matrix B is broadcast to all ranks. Cost: O(N²) bytes — same for all P, so B overhead is constant regardless of P.</p>
          </div>
          <div className="space-y-1">
            <p className="text-purple-400 font-medium">Barrier Sync</p>
            <p className="text-slate-500">Barriers ensure all ranks finish their slab before Gather. Synchronisation cost grows with P due to collective coordination.</p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function ResearchMode() {
  const [tab, setTab] = useState<Tab>('theory')

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'theory', label: 'Theory Comparison', icon: <TrendingUp className="w-4 h-4" /> },
    { id: 'experiments', label: 'Experiments', icon: <GitCompare className="w-4 h-4" /> },
    { id: 'mpi', label: 'MPI Timing', icon: <Cpu className="w-4 h-4" /> },
  ]

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Header />
      <main className="max-w-screen-2xl mx-auto px-6 py-8">
        {/* Page title */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/30 flex items-center justify-center">
            <FlaskConical className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h1 className="text-slate-100 font-semibold text-lg">Research Mode</h1>
            <p className="text-slate-500 text-xs">Scalability theory, experiment tracking, and MPI profiling</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b border-slate-800">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-purple-500 text-purple-400'
                  : 'border-transparent text-slate-500 hover:text-slate-300'
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'theory' && <TheoryTab />}
        {tab === 'experiments' && <ExperimentsTab />}
        {tab === 'mpi' && <MPITab />}
      </main>
    </div>
  )
}
