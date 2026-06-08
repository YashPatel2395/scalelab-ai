"""
Prompt templates for the AI analysis layer.
Structured to produce deterministic, parseable output from any LLM provider.
"""

SYSTEM_PROMPT = """\
You are a distributed systems performance engineer specializing in parallel computing,
scalability analysis, and bottleneck identification. You analyze benchmark results from
a distributed performance platform and produce structured, technically precise explanations.

Your analysis must be grounded in computer science principles:
- Amdahl's Law for speedup upper bounds
- Gustafson's Law for scaled workloads
- Roofline model for memory vs compute bounds
- Communication overhead in distributed systems

Always distinguish between CPU-bound, memory-bound, and communication-bound behavior.
Be honest about limitations – do not overclaim parallelism benefits for inherently serial workloads.
"""

ANALYSIS_PROMPT_TEMPLATE = """\
Analyze this parallel benchmark result and provide a structured performance assessment.

## Benchmark Data
- Workload: {workload_type}
- Input Size: {input_size}
- Worker Count: {worker_count}
- Execution Time (parallel): {execution_time:.4f}s
- Sequential Baseline: {sequential_time:.4f}s
- Measured Speedup: {speedup:.3f}x
- Parallel Efficiency: {efficiency:.1f}%
- CPU Usage: {cpu_usage:.1f}%
- Memory Usage: {memory_usage:.1f}%
- Peak Memory: {peak_memory_mb:.1f} MB

## Instructions
Respond in JSON with exactly this structure:
{{
  "bottleneck_type": "<cpu_bound|memory_bound|communication_bound|well_balanced>",
  "bottleneck_summary": "<one sentence>",
  "speedup_explanation": "<2-3 sentences explaining observed speedup vs theoretical>",
  "bottleneck_details": "<2-3 sentences on the specific bottleneck>",
  "optimization_recommendations": ["<rec1>", "<rec2>", "<rec3>"],
  "complexity_interpretation": "<time complexity at this scale>",
  "theoretical_max_speedup": <float based on Amdahl>,
  "parallel_fraction_estimate": <float 0-1>,
  "confidence": "<high|medium|low>"
}}
"""


def format_analysis_prompt(benchmark_data: dict) -> str:
    return ANALYSIS_PROMPT_TEMPLATE.format(
        workload_type=benchmark_data.get("workload_type", "unknown"),
        input_size=benchmark_data.get("input_size", 0),
        worker_count=benchmark_data.get("worker_count", 1),
        execution_time=benchmark_data.get("execution_time") or 0.0,
        sequential_time=benchmark_data.get("sequential_time") or 0.0,
        speedup=benchmark_data.get("speedup") or 1.0,
        efficiency=benchmark_data.get("efficiency") or 100.0,
        cpu_usage=benchmark_data.get("cpu_usage") or 0.0,
        memory_usage=benchmark_data.get("memory_usage") or 0.0,
        peak_memory_mb=benchmark_data.get("peak_memory_mb") or 0.0,
    )
