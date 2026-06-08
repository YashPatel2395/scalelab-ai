"""Anthropic provider – uses Claude claude-sonnet-4-6 for structured JSON analysis."""

import json
import logging

from app.ai.base import AnalysisResult, BaseAIProvider
from app.ai.prompts import SYSTEM_PROMPT, format_analysis_prompt

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseAIProvider):
    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-6"):
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic package not installed") from exc

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")

        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def analyze(self, benchmark_data: dict) -> AnalysisResult:
        try:
            prompt = format_analysis_prompt(benchmark_data)
            full_prompt = (
                f"{prompt}\n\nRespond ONLY with the JSON object, no markdown fences."
            )
            message = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": full_prompt}],
            )
            raw = message.content[0].text if message.content else "{}"

            # Strip potential markdown fences
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]

            data = json.loads(raw)
            return AnalysisResult(
                bottleneck_type=data.get("bottleneck_type", "unknown"),
                bottleneck_summary=data.get("bottleneck_summary", ""),
                speedup_explanation=data.get("speedup_explanation", ""),
                bottleneck_details=data.get("bottleneck_details", ""),
                optimization_recommendations=data.get("optimization_recommendations", []),
                complexity_interpretation=data.get("complexity_interpretation", ""),
                theoretical_max_speedup=data.get("theoretical_max_speedup"),
                parallel_fraction_estimate=data.get("parallel_fraction_estimate"),
                confidence=data.get("confidence", "medium"),
                provider="anthropic",
                model=self._model,
                raw_response=raw,
            )
        except Exception as exc:
            logger.error("Anthropic analysis failed: %s", exc)
            from app.ai.mock_provider import MockAIProvider
            result = MockAIProvider().analyze(benchmark_data)
            result.confidence = "low"
            result.provider = f"mock_fallback (anthropic error: {type(exc).__name__})"
            return result
