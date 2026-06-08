from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisResult:
    """Structured output from the AI analysis layer."""

    # High-level classification
    bottleneck_type: str = "unknown"        # cpu_bound | memory_bound | communication_bound | well_balanced
    bottleneck_summary: str = ""

    # Detailed sections
    speedup_explanation: str = ""
    bottleneck_details: str = ""
    optimization_recommendations: list[str] = field(default_factory=list)
    complexity_interpretation: str = ""

    # Amdahl / Gustafson analysis
    theoretical_max_speedup: float | None = None
    parallel_fraction_estimate: float | None = None

    # Confidence and metadata
    confidence: str = "high"               # high | medium | low
    provider: str = "unknown"
    model: str = "unknown"
    raw_response: Any = None

    def to_dict(self) -> dict:
        return {
            "bottleneck_type": self.bottleneck_type,
            "bottleneck_summary": self.bottleneck_summary,
            "speedup_explanation": self.speedup_explanation,
            "bottleneck_details": self.bottleneck_details,
            "optimization_recommendations": self.optimization_recommendations,
            "complexity_interpretation": self.complexity_interpretation,
            "theoretical_max_speedup": self.theoretical_max_speedup,
            "parallel_fraction_estimate": self.parallel_fraction_estimate,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
        }


class BaseAIProvider(ABC):
    """Contract every AI provider must implement."""

    @abstractmethod
    def analyze(self, benchmark_data: dict) -> AnalysisResult:
        """
        Accept a benchmark result dict and return a structured analysis.
        Must never raise – return a partial result with confidence='low' on failure.
        """
        ...
