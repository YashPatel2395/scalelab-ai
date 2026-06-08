from app.ai.base import AnalysisResult, BaseAIProvider
from app.ai.mock_provider import MockAIProvider

__all__ = ["AnalysisResult", "BaseAIProvider", "MockAIProvider", "get_provider"]


def get_provider(provider_name: str, **kwargs) -> "BaseAIProvider":
    """Factory: returns the requested AI provider, falling back to mock."""
    name = provider_name.lower().strip()

    if name == "openai":
        try:
            from app.ai.openai_provider import OpenAIProvider
            return OpenAIProvider(**kwargs)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "OpenAI provider unavailable (%s) – falling back to mock.", exc
            )

    elif name == "anthropic":
        try:
            from app.ai.anthropic_provider import AnthropicProvider
            return AnthropicProvider(**kwargs)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Anthropic provider unavailable (%s) – falling back to mock.", exc
            )

    return MockAIProvider()
