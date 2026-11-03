"""Google Gemini via its REST API (generateContent) with structured JSON output."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random

from ... import http
from ..prompt import to_openapi_schema
from .base import ImageInput, Provider, ProviderError, ProviderOutput, user_text

log = logging.getLogger("gemini")


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, api_base: str, temperature=None, schema_mode="json_schema",
                 timeout=120, max_retries=2, generation_config_extra: dict | None = None):
        if not api_key:
            raise ProviderError("GEMINI_API_KEY is not set. Add it to the .env file (see .env.example).")
        self.api_key = api_key
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.temperature = temperature
        self.schema_mode = schema_mode
        self.timeout = timeout
        self.max_retries = max_retries
        self.extra = generation_config_extra or {}

    def build_request(self, images: list[ImageInput], instructions: str, schema: dict, schema_mode: str,
                      text: str = "") -> dict:
        parts = [{"inlineData": {"mimeType": im.mime, "data": base64.b64encode(im.data).decode("ascii")}}
                 for im in images]
        n = len(images)
        parts.append({"text": user_text(n, text)})
        gen = {"responseMimeType": "application/json"}
        if schema_mode == "openapi":
            gen["responseSchema"] = to_openapi_schema(schema)
        else:
            gen["responseJsonSchema"] = schema
        if self.temperature is not None:
            gen["temperature"] = self.temperature
        gen.update(self.extra)
        return {"systemInstruction": {"parts": [{"text": instructions}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen}

    @staticmethod
    def parse_response(data: dict) -> tuple[str, dict]:
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(f"Gemini returned no answer{f' (blocked: {reason})' if reason else ''}")
        cand = cands[0]
        texts = [p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought")]
        text = "".join(texts).strip()
        if not text:
            raise ProviderError(f"Gemini returned an empty answer (finishReason={cand.get('finishReason')})",
                                retryable=True)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Gemini answer is not valid JSON: {e}", retryable=True)
        u = data.get("usageMetadata") or {}
        usage = {"input_tokens": u.get("promptTokenCount"), "output_tokens": u.get("candidatesTokenCount"),
                 "thinking_tokens": u.get("thoughtsTokenCount"), "total_tokens": u.get("totalTokenCount"),
                 "model_version": data.get("modelVersion")}
        return text, {"parsed": parsed, "usage": usage}

    async def _call(self, body: dict) -> dict:
        url = f"{self.api_base}/models/{self.model}:generateContent"
        r = await http.request("POST", url, headers={"x-goog-api-key": self.api_key}, json_body=body,
                               timeout=self.timeout)
        if r.status == 200:
            return r.json()
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        raise ProviderError(f"Gemini API error {r.status}: {msg[:500]}",
                            retryable=r.status in (429, 500, 502, 503, 504), status=r.status)

    async def diagnose(self, images: list[ImageInput], instructions: str, schema: dict,
                       text: str = "") -> ProviderOutput:
        mode = self.schema_mode
        attempt = 0
        while True:
            try:
                data = await self._call(self.build_request(images, instructions, schema, mode, text))
                raw, out = self.parse_response(data)
                return ProviderOutput(out["parsed"], raw, self.model, out["usage"])
            except ProviderError as e:
                # Some models/API versions reject responseJsonSchema: fall back to responseSchema once.
                if e.status == 400 and mode == "json_schema" and "responseJsonSchema" in str(e):
                    log.warning("responseJsonSchema rejected; retrying with responseSchema")
                    mode = self.schema_mode = "openapi"
                    continue
                if not e.retryable or attempt >= self.max_retries:
                    raise
                attempt += 1
                wait = (2 ** attempt) + random.random()
                log.warning("Gemini call failed (%s); retry %d in %.1fs", e, attempt, wait)
                await asyncio.sleep(wait)
