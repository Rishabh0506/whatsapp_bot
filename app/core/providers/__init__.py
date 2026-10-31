"""Choose the model provider from settings. To compare models later, add a provider class and a branch here."""
from __future__ import annotations

from ...config import Settings
from ..reference import Reference
from .base import ImageInput, Provider, ProviderError, ProviderOutput
from .gemini import GeminiProvider
from .mock import MockProvider


def make_provider(settings: Settings, reference: Reference) -> Provider:
    name = settings.get("core.provider", "gemini")
    if name == "mock":
        return MockProvider(reference)
    if name == "gemini":
        g = lambda k, d=None: settings.get(f"gemini.{k}", d)  # noqa: E731
        return GeminiProvider(
            api_key=settings.secret("GEMINI_API_KEY"), model=g("model"), api_base=g("api_base"),
            temperature=g("temperature"), schema_mode=g("schema_mode", "json_schema"),
            timeout=g("timeout_seconds", 120), max_retries=g("max_retries", 2),
            generation_config_extra=g("generation_config_extra") or {})
    raise ValueError(f"Unknown provider '{name}' in settings (core.provider)")


__all__ = ["make_provider", "Provider", "ProviderError", "ProviderOutput", "ImageInput"]
