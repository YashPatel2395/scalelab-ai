"""OpenAI provider – uses gpt-4o for structured JSON analysis."""

import json
import logging

from app.ai.base import AnalysisResult, BaseAIProvider
from app.ai.prompts import SYSTEM_PROMPT, format_analysis_prompt

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: str = "", model: str = "gpt-4o"):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package not installed") from exc

        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def analyze(self, benchmark_data: dict) -> AnalysisResult:
        try:
            prompt = format_analysis_prompt(benchmark_data)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content or "{}"
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
                provider="openai",
                model=self._model,
                raw_response=raw,
            )
        except Exception as exc:
            logger.error("OpenAI analysis failed: %s", exc)
            from app.ai.mock_provider import MockAIProvider
            result = MockAIProvider().analyze(benchmark_data)
            result.confidence = "low"
            result.provider = f"mock_fallback (openai error: {type(exc).__name__})"
            return result
