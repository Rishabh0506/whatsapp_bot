"""Backend dashboard: the bot's internal view (fields, confidences, decisions, raw model output).

Served on its own port (dashboard.port in settings, default 8001), never on the public bot port, so customers
and the internet can't reach it even when the bot port is exposed for real WhatsApp.
Channel-independent: works the same in simulator and real WhatsApp mode.

  GET /                     the dashboard page
  GET /api/diagnoses        newest first; ?limit=<n> (the page asks for 1) &wa_id=<number> (optional)
  GET /api/info             provider, model, prompt, bands, fields
  GET /media/{media_id}     a stored photo
"""
from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from . import replies
from .static import NoCacheStaticFiles

STATIC = Path(__file__).parent / "dashboard_static"
SHARED_STATE = ("settings", "reference", "storage", "service", "conversations")


async def diagnoses(request: Request):
    wa_id = request.query_params.get("wa_id") or None
    limit = min(int(request.query_params.get("limit", 30)), 200)
    rows = request.app.state.storage.list_diagnoses(wa_id, limit)
    storage = request.app.state.storage
    for r in rows:
        if not r.get("reply"):    # older rows (or a diagnosis replaced by a newer look): rebuild the wording
            lang = r.get("lang") or "en"
            r["reply"] = replies.diagnosis(r["result"], lang) if r["result"] else replies.error(None, lang)
            r["reply_rebuilt"] = True
        case = storage.get_case(r["case_id"]) if r.get("case_id") else None
        r["case"] = case
        r["conversation_open"] = bool(case and not case.get("ended_at"))
    return JSONResponse(rows)


async def info(request: Request):
    s, st = request.app.state.settings, request.app.state
    return JSONResponse({
        "channel": s.get("channel.mode"),
        "provider": s.get("core.provider"),
        "model": getattr(st.service.provider, "model", ""),
        "prompt": s.get("core.prompt"),
        "bands": {"accept": s.get("rules.accept_threshold"), "unknown_below": s.get("rules.unknown_below")},
        "batch_wait_seconds": s.get("channel.batch_wait_seconds"),
        "max_tries": s.get("conversation.max_tries", 3),
        "close_after_seconds": s.get("conversation.close_after_seconds", 300),
        "keep_records": st.conversations.keep_records,
        "reference": st.reference.source_info(),
        "fields": [{"key": f.key, "label": f.label, "product_deciding": f.product_deciding}
                   for f in st.reference.fields],
    })


async def media(request: Request):
    path = request.app.state.storage.media_path(request.path_params["media_id"])
    if not path or not Path(path).exists():
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(path)


routes = [
    Route("/api/diagnoses", diagnoses),
    Route("/api/info", info),
    Route("/media/{media_id}", media),
    Mount("/", app=NoCacheStaticFiles(directory=str(STATIC), html=True), name="dashboard-static"),
]


def build_dashboard(bot_app: Starlette) -> Starlette:
    """A second web app that shares the bot's storage and settings (same process, same database)."""
    app = Starlette(routes=routes)
    for name in SHARED_STATE:
        setattr(app.state, name, getattr(bot_app.state, name))
    return app
