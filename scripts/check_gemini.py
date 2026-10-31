"""Check the Gemini setup from the command line.

    python scripts/check_gemini.py                 list the models your API key can use
    python scripts/check_gemini.py photo.jpg ...   run the full diagnosis on photo(s) and print the 10 fields
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


async def list_models(settings: Settings):
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
    print(f"\nModel: {result['meta']['model']}   prompt: {result['meta']['prompt_version']}   "
          f"time: {result['meta']['latency_ms'] / 1000:.1f}s   tokens: {result['meta']['usage'].get('total_tokens')}\n")
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
    s = Settings.load(overrides={"core.provider": "gemini"})
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    asyncio.run(diagnose(s, files) if files else list_models(s))
