"""Choose the model provider from settings (core.provider).

  openrouter  Gemini (or other models) through OpenRouter, key OPENROUTER_API_KEY   <- default
  gemini      Gemini directly from Google AI Studio, key GEMINI_API_KEY
  mock        fake answers, no key, for tests and trying the interface

Through OpenRouter, comparing models is mostly a change of openrouter.model. A model that needs a different
API gets its own provider class and a branch here."""
from __future__ import annotations

from ...config import Settings
from ..reference import Reference
from .base import ImageInput, Provider, ProviderError, ProviderOutput
from .gemini import GeminiProvider
from .mock import MockProvider
from .openrouter import OpenRouterProvider


def make_provider(settings: Settings, reference: Reference) -> Provider:
    name = settings.get("core.provider", "openrouter")
    if name == "mock":
        return MockProvider(reference)
    if name == "openrouter":
        o = lambda k, d=None: settings.get(f"openrouter.{k}", d)  # noqa: E731
        return OpenRouterProvider(
            api_key=settings.secret("OPENROUTER_API_KEY"), model=o("model"),
            api_base=o("api_base", "https://openrouter.ai/api/v1"), temperature=o("temperature"),
            reasoning_effort=o("reasoning_effort"), timeout=o("timeout_seconds", 120),
            max_retries=o("max_retries", 2), app_title=o("app_title", ""), app_url=o("app_url", ""),
            extra=o("request_extra") or {})
    if name == "gemini":   # Google AI Studio directly (the original setup; kept as an option)
        g = lambda k, d=None: settings.get(f"gemini.{k}", d)  # noqa: E731
        return GeminiProvider(
            api_key=settings.secret("GEMINI_API_KEY"), model=g("model"), api_base=g("api_base"),
            temperature=g("temperature"), schema_mode=g("schema_mode", "json_schema"),
            timeout=g("timeout_seconds", 120), max_retries=g("max_retries", 2),
            generation_config_extra=g("generation_config_extra") or {})
    raise ValueError(f"Unknown provider '{name}' in settings (core.provider)")


__all__ = ["make_provider", "Provider", "ProviderError", "ProviderOutput", "ImageInput"]
