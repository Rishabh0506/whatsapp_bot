"""Gemini (or any vision model) through OpenRouter's OpenAI-compatible Chat Completions API, with structured
JSON output. One OPENROUTER_API_KEY gives access to many models, so comparing models later is a settings change.

Request:  POST {api_base}/chat/completions
          system message = instructions; user message = the photos (base64 data URLs) + one line of text (+ the customer's own words, if any);
          response_format = the JSON schema built from fields.yaml (values must come from the allowed lists).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random

from ... import http
from .base import ImageInput, Provider, ProviderError, ProviderOutput, user_text

log = logging.getLogger("openrouter")

RETRYABLE = (408, 429, 500, 502, 503, 504)


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str, api_base: str = "https://openrouter.ai/api/v1",
                 temperature=None, reasoning_effort=None, timeout=120, max_retries=2,
                 app_title: str = "", app_url: str = "", extra: dict | None = None):
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set. Add it to the .env file (see .env.example).")
        self.api_key = api_key
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.max_retries = max_retries
        self.app_title = app_title
        self.app_url = app_url
        self.extra = extra or {}
        self.schema_mode = "json_schema"     # falls back to "json_object" if the route rejects JSON schemas

    def build_request(self, images: list[ImageInput], instructions: str, schema: dict, schema_mode: str,
                      text: str = "") -> dict:
        n = len(images)
        content = [{"type": "image_url",
                    "image_url": {"url": f"data:{im.mime};base64,{base64.b64encode(im.data).decode('ascii')}"}}
                   for im in images]
        content.append({"type": "text", "text": user_text(n, text)})
        if schema_mode == "json_object":
            fmt = {"type": "json_object"}
        else:
            fmt = {"type": "json_schema", "json_schema": {"name": "footwear_diagnosis", "strict": True, "schema": schema}}
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": content}],
            "response_format": fmt,
            # only route to providers that honour response_format, so the answer always follows the schema
            "provider": {"require_parameters": True},
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort}
        for k, v in self.extra.items():       # settings: openrouter.request_extra
            body[k] = {**body[k], **v} if isinstance(v, dict) and isinstance(body.get(k), dict) else v
        return body

    @staticmethod
    def parse_response(data: dict) -> tuple[str, dict]:
        if data.get("error") and not data.get("choices"):
            err = data["error"]
            raise ProviderError(f"OpenRouter error: {err.get('message', err)}", retryable=True)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("OpenRouter returned no answer", retryable=True)
        choice = choices[0]
        if choice.get("error"):
            raise ProviderError(f"Model error: {choice['error'].get('message', choice['error'])}", retryable=True)
        content = (choice.get("message") or {}).get("content") or ""
        if isinstance(content, list):          # some providers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        text = content.strip()
        if text.startswith("```"):             # tolerate ```json fences
            text = text.strip("`").removeprefix("json").strip()
        if not text:
            raise ProviderError(f"The model returned an empty answer (finish_reason={choice.get('finish_reason')})",
                                retryable=True)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"The model's answer is not valid JSON: {e}", retryable=True)
        u = data.get("usage") or {}
        usage = {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
                 "thinking_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                 "total_tokens": u.get("total_tokens"), "cost_usd": u.get("cost"),
                 "model_version": data.get("model"), "routed_to": data.get("provider")}
        return text, {"parsed": parsed, "usage": usage}

    async def _call(self, body: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.app_title:
            headers["X-Title"] = self.app_title
        if self.app_url:
            headers["HTTP-Referer"] = self.app_url
        r = await http.request("POST", f"{self.api_base}/chat/completions", headers=headers, json_body=body,
                               timeout=self.timeout)
        if r.status == 200:
            return r.json()
        try:
            err = r.json().get("error", {})
            msg = err.get("message", r.text)
            raw = (err.get("metadata") or {}).get("raw")
            if raw:
                msg += f" ({str(raw)[:300]})"
        except Exception:
            msg = r.text
        raise ProviderError(f"OpenRouter API error {r.status}: {msg[:600]}",
                            retryable=r.status in RETRYABLE, status=r.status)

    async def diagnose(self, images: list[ImageInput], instructions: str, schema: dict,
                       text: str = "") -> ProviderOutput:
        attempt = 0
        while True:
            try:
                data = await self._call(self.build_request(images, instructions, schema, self.schema_mode, text))
                raw, out = self.parse_response(data)
                return ProviderOutput(out["parsed"], raw, self.model, out["usage"])
            except ProviderError as e:
                # If no route accepts a JSON schema, fall back once to plain JSON mode; validation still checks it.
                low = str(e).lower()
                if (self.schema_mode == "json_schema" and e.status in (400, 404)
                        and any(w in low for w in ("response_format", "json_schema", "structured", "schema"))):
                    log.warning("JSON schema output rejected (%s); retrying in JSON mode", e)
                    self.schema_mode = "json_object"
                    continue
                if not e.retryable or attempt >= self.max_retries:
                    raise
                attempt += 1
                wait = (2 ** attempt) + random.random()
                log.warning("OpenRouter call failed (%s); retry %d in %.1fs", e, attempt, wait)
                await asyncio.sleep(wait)
