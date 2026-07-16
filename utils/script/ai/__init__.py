"""AI package root: kernel-only public surface.

Domain capabilities import from ``utils.script.ai.capabilities.<name>``.
"""

from .kernel import (
    AiProvider,
    OpenAiCompatClient,
    is_ai_provider_configured,
    load_ai_provider,
    normalize_provider_fields,
    provider_to_payload,
)

__all__ = [
    "AiProvider",
    "OpenAiCompatClient",
    "is_ai_provider_configured",
    "load_ai_provider",
    "normalize_provider_fields",
    "provider_to_payload",
]
