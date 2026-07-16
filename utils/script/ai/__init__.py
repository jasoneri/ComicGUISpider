"""AI package root: kernel-only public surface.

Domain capabilities import from ``utils.script.ai.capabilities.<name>``.
"""

from .kernel import (
    AiProvider,
    AiProviderMgr,
    OpenAiCompatClient,
)

__all__ = [
    "AiProvider",
    "AiProviderMgr",
    "OpenAiCompatClient",
]
