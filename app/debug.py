"""Debug API for the test interface: the bot's internal view (fields, confidences, decisions).
Channel-independent: works the same in simulator and real WhatsApp mode."""
from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route


async def diagnoses(request: Request):
    wa_id = request.query_params.get("wa_id") or None
    limit = min(int(request.query_params.get("limit", 20)), 200)
    return JSONResponse(request.app.state.storage.list_diagnoses(wa_id, limit))


async def info(request: Request):
    s, st = request.app.state.settings, request.app.state
    return JSONResponse({
        "channel": s.get("channel.mode"),
        "provider": s.get("core.provider"),
        "model": getattr(st.service.provider, "model", ""),
        "prompt": s.get("core.prompt"),
        "bands": {"accept": s.get("rules.accept_threshold"), "unknown_below": s.get("rules.unknown_below")},
        "batch_wait_seconds": s.get("channel.batch_wait_seconds"),
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
    Route("/debug/api/diagnoses", diagnoses),
    Route("/debug/api/info", info),
    Route("/debug/media/{media_id}", media),
]
