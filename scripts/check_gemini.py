"""Check the model setup from the command line (works with the provider set in config/settings.yaml).

    python scripts/check_gemini.py                 check the API key and list the Gemini models you can use
    python scripts/check_gemini.py photo.jpg ...   run the full diagnosis on photo(s) and print the 10 fields
    add --raw to also print the model's raw JSON answer
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import http  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core.pipeline import DiagnosisService  # noqa: E402
from app.core.providers import make_provider  # noqa: E402
from app.core.reference import Reference  # noqa: E402


async def check_openrouter(settings: Settings):
    key = settings.secret("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set in .env (see .env.example)")
    base = settings.get("openrouter.api_base", "https://openrouter.ai/api/v1").rstrip("/")
    r = await http.request("GET", f"{base}/key", headers={"Authorization": f"Bearer {key}"})
    if r.status != 200:
        sys.exit(f"API key check failed ({r.status}): {r.text[:300]}")
    info = r.json().get("data", {})
    limit = info.get("limit")
    print(f"API key OK ({info.get('label', 'no label')}). Used so far: ${info.get('usage', 0):.4f}"
          + (f" of ${limit:.2f} limit" if limit is not None else " (no limit set)"))

    r = await http.request("GET", f"{base}/models")
    if r.status != 200:
        sys.exit(f"Could not list models ({r.status}): {r.text[:300]}")
    configured = settings.get("openrouter.model")
    models = [m for m in r.json().get("data", [])
              if m["id"].startswith("google/gemini") and "image" in (m.get("architecture") or {}).get("input_modalities", [])]
    print(f"\n{len(models)} Gemini models on OpenRouter accept photos  (* = supports structured JSON output):\n")
    for m in sorted(models, key=lambda m: m["id"]):
        p = m.get("pricing") or {}
        price = ""
        if p.get("prompt") and p.get("completion"):
            price = f"${float(p['prompt']) * 1e6:.2f} / ${float(p['completion']) * 1e6:.2f} per 1M in/out"
        star = "*" if "structured_outputs" in (m.get("supported_parameters") or []) else " "
        mark = "  <- configured" if m["id"] == configured else ""
        print(f"  {star} {m['id']:45s} {price}{mark}")
    if configured not in [m["id"] for m in models]:
        print(f"\nWARNING: the configured model '{configured}' is not in this list. "
              "Change openrouter.model in config/settings.yaml.")


async def check_gemini_direct(settings: Settings):
    key = settings.secret("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is not set in .env")
    base = settings.get("gemini.api_base").rstrip("/")
    r = await http.request("GET", f"{base}/models?pageSize=1000", headers={"x-goog-api-key": key})
    if r.status != 200:
        sys.exit(f"API key check failed ({r.status}): {r.text[:300]}")
    models = [m for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    configured = settings.get("gemini.model")
    print(f"API key OK. {len(models)} models support generateContent:\n")
    for m in models:
        name = m["name"].removeprefix("models/")
        mark = "  <- configured in settings.yaml" if name == configured else ""
        print(f"  {name:45s} {m.get('displayName', '')}{mark}")
    if configured not in [m["name"].removeprefix("models/") for m in models]:
        print(f"\nWARNING: the configured model '{configured}' is not in this list. Change gemini.model in config/settings.yaml.")


async def diagnose(settings: Settings, paths: list[str]):
    ref = Reference.load(settings.config_dir)
    service = DiagnosisService(settings, ref, make_provider(settings, ref))
    result = await service.diagnose([Path(p).read_bytes() for p in paths])
    m = result["meta"]
    cost = m["usage"].get("cost_usd")
    print(f"\nProvider: {m['provider']}   model: {m['model']}   prompt: {m['prompt_version']}   "
          f"time: {m['latency_ms'] / 1000:.1f}s   tokens: {m['usage'].get('total_tokens')}"
          + (f"   cost: ${cost:.5f}" if cost is not None else "") + "\n")
    for i, key in enumerate(result["order"], 1):
        f = result["fields"][key]
        extra = f"   (model said: {f['model_value']})" if f["value"] != f["model_value"] else ""
        print(f"{i:2d}. {f['label']:20s} {str(f['value']):38s} {f['confidence']:.2f}  {f['status']}{extra}")
    print(f"\nDecision: {result['decision']['action']} - {result['decision']['reason']}")
    print(f"Seen: {result['visible_evidence']}")
    if result["observation_note"]:
        print(f"Note: {result['observation_note']}")
    for w in result["warnings"]:
        print(f"Warning: {w['message']}")
    if "--raw" in sys.argv:
        print(json.dumps(json.loads(result["raw_model_output"]), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    s = Settings.load()
    if s.get("core.provider") == "mock":
        s = Settings.load(overrides={"core.provider": "openrouter"})
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if files:
        asyncio.run(diagnose(s, files))
    elif s.get("core.provider") == "gemini":
        asyncio.run(check_gemini_direct(s))
    else:
        asyncio.run(check_openrouter(s))
