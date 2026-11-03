"""Fake model for testing the pipeline and the interface without an API key.
Answers are random but repeatable: the same photo always gets the same answer."""
from __future__ import annotations

import hashlib
import json
import random

from ..reference import Reference
from .base import ImageInput, Provider, ProviderOutput


class MockProvider(Provider):
    name = "mock"
    model = "mock"

    def __init__(self, reference: Reference):
        self.ref = reference

    async def diagnose(self, images: list[ImageInput], instructions: str, schema: dict,
                       text: str = "") -> ProviderOutput:
        seed = hashlib.sha256(b"".join(im.data for im in images)).hexdigest()
        rnd = random.Random(seed)
        row = rnd.choice(self.ref.universe) if self.ref.universe else {}
        answer: dict = {"visible_evidence": "Mock answer: no model was called."}
        for f in self.ref.fields:
            conf = round(rnd.choice([rnd.uniform(0.3, 0.5), rnd.uniform(0.5, 0.8), rnd.uniform(0.8, 0.99)]), 2)
            if f.kind == "issue_pair":
                answer[f.key] = {"issue_category": "None", "damage_mode": "None", "confidence": conf}
                continue
            value = row.get(f.key)
            if f.key in ("receiving_substrate", "applied_substrate") and value:
                value = value.split(" / ")[0]
            if value not in f.values:
                value = "Usable" if f.key == "image_status" else rnd.choice(f.values)
            answer[f.key] = {"value": value, "confidence": conf}
        answer["observation_note"] = ""
        return ProviderOutput(answer, json.dumps(answer), self.model, {"input_tokens": 0, "output_tokens": 0})
