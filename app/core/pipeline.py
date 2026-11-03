"""The diagnosis core: photos in -> 10 fields + confidence + decision out.
It knows nothing about WhatsApp or any other channel, so every channel reuses it unchanged.

Steps: prepare images (+ the customer's text) -> model -> validate -> rules. Later steps (solution selection,
voice input) are added here without touching the existing ones."""
from __future__ import annotations

import logging
import time

from ..config import Settings
from .images import prepare_image
from .prompt import build_schema, load_prompt
from .providers import ImageInput, Provider, ProviderError
from .reference import Reference
from .rules import apply_rules
from .validation import normalize

log = logging.getLogger("pipeline")


class DiagnosisService:
    def __init__(self, settings: Settings, reference: Reference, provider: Provider):
        self.settings = settings
        self.ref = reference
        self.provider = provider
        self.schema = build_schema(reference.fields)

    async def diagnose(self, images: list[bytes], text: str = "") -> dict:
        """Returns a result dict. Raises ProviderError if the model call fails.
        text: what the customer wrote about the problem (any language), given to the model with the photos."""
        s = self.settings
        max_images = s.get("core.max_images_per_item", 5)
        prepared = [ImageInput(prepare_image(b, s.get("core.max_image_side", 1600))) for b in images[:max_images]]
        instructions, prompt_version = load_prompt(s.config_dir, s.get("core.prompt", "diagnosis_v1"), self.ref)

        started = time.perf_counter()
        out = await self.provider.diagnose(prepared, instructions, self.schema, text=text.strip())
        latency_ms = int((time.perf_counter() - started) * 1000)

        fields, warnings, extras = normalize(out.parsed, self.ref)
        accept, unknown_below = s.get("rules.accept_threshold", 0.8), s.get("rules.unknown_below", 0.5)
        decision = apply_rules(fields, self.ref, accept, unknown_below)
        if len(images) > max_images:
            warnings.append({"code": "too_many_images", "field": None,
                             "message": f"Only the first {max_images} of {len(images)} photos were used"})
        return {
            "fields": fields,
            "order": [f.key for f in self.ref.fields],
            "decision": decision,
            "warnings": warnings,
            **extras,
            "meta": {
                "provider": self.provider.name, "model": out.model, "prompt_version": prompt_version,
                "latency_ms": latency_ms, "usage": out.usage, "image_count": len(prepared),
                "customer_text": text.strip(),
                "bands": {"accept": accept, "unknown_below": unknown_below},
            },
            "raw_model_output": out.raw_text,
        }


__all__ = ["DiagnosisService", "ProviderError"]
