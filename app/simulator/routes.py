"""WhatsApp simulator: plays the role of Meta's servers AND of the user's phone.

Meta's side (the bot cannot tell it apart from the real Cloud API):
  GET  /sim/graph/{media_id}                      -> media info with a short-lived download URL
  GET  /sim/graph-media/{media_id}?exp=...        -> the photo (needs the access token, expires after 5 min)
  POST /sim/graph/{phone_number_id}/messages      -> bot sends a message / read receipt
  ...and it calls the bot's /webhook with signed Cloud API payloads, plus sent/delivered statuses.

The phone's side (used by the chat page):
  POST /sim/api/send          user sends photos and/or text
  POST /sim/api/reply         user taps a reply button / list row
  GET  /sim/api/messages      the chat history the phone would show
  GET  /sim/api/media/{id}    photo for display in the chat
  GET  /sim/api/presence      whether the bot is showing "typing…" in this user's chat
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from .. import http
from ..config import SIM_ACCESS_TOKEN, SIM_APP_SECRET, SIM_PHONE_NUMBER_ID
from ..static import NoCacheStaticFiles

log = logging.getLogger("simulator")
STATIC = Path(__file__).parent / "static"
MEDIA_URL_TTL = 300   # Cloud API media URLs expire after 5 minutes
TYPING_TTL = 25       # WhatsApp hides the typing indicator after 25 seconds, or when the reply arrives


class SimStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.typing_until: dict[str, float] = {}     # wa_id -> time the typing indicator disappears
        self.media_dir = path.parent / "sim_media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS media (media_id TEXT PRIMARY KEY, path TEXT, mime TEXT, sha256 TEXT,
                size INTEGER, created_at REAL);
            CREATE TABLE IF NOT EXISTS messages (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, wa_id TEXT,
                sender TEXT, type TEXT, body TEXT, status TEXT, created_at REAL);""")
            self.db.commit()

    def q(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return [dict(r) for r in cur.fetchall()]


def _new_wamid() -> str:
    return "wamid.SIM" + uuid.uuid4().hex.upper()


def _authorized(request: Request) -> bool:
    return request.headers.get("Authorization") == f"Bearer {SIM_ACCESS_TOKEN}"


def compress_like_whatsapp(data: bytes, max_side: int, quality: int) -> bytes:
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)
    return out.getvalue()


def _contacts(wa_id: str, name: str) -> list:
    return [{"profile": {"name": name or "Test user"}, "wa_id": wa_id}]


def _envelope(value: dict) -> dict:
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "SIM_WABA_ID", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "15550000000", "phone_number_id": SIM_PHONE_NUMBER_ID},
                **value}}]}]}


async def _post_webhook(request: Request, payload: dict) -> None:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SIM_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    url = request.app.state.settings.get("app.public_base_url").rstrip("/") + "/webhook"
    r = await http.request("POST", url, body=body,
                           headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
    if r.status != 200:
        log.warning("webhook returned %s: %s", r.status, r.text[:200])


# ---------------------------------------------------------------- Meta's side
async def graph_media_info(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": {"message": "Invalid OAuth access token", "code": 190}}, status_code=401)
    sim: SimStore = request.app.state.sim
    rows = sim.q("SELECT * FROM media WHERE media_id=?", (request.path_params["media_id"],))
    if not rows:
        return JSONResponse({"error": {"message": "Media not found", "code": 100}}, status_code=404)
    m = rows[0]
    base = request.app.state.settings.get("app.public_base_url").rstrip("/")
    return JSONResponse({"messaging_product": "whatsapp", "id": m["media_id"], "mime_type": m["mime"],
                         "sha256": m["sha256"], "file_size": m["size"],
                         "url": f"{base}/sim/graph-media/{m['media_id']}?exp={int(time.time()) + MEDIA_URL_TTL}"})


async def graph_media_download(request: Request):
    if not _authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    if int(request.query_params.get("exp", 0)) < time.time():
        return PlainTextResponse("URL expired", status_code=404)
    rows = request.app.state.sim.q("SELECT * FROM media WHERE media_id=?", (request.path_params["media_id"],))
    if not rows:
        return PlainTextResponse("Not found", status_code=404)
    return Response(Path(rows[0]["path"]).read_bytes(), media_type=rows[0]["mime"])


async def graph_send(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": {"message": "Invalid OAuth access token", "code": 190}}, status_code=401)
    if request.path_params["phone_number_id"] != SIM_PHONE_NUMBER_ID:
        return JSONResponse({"error": {"message": "Unknown phone number id", "code": 100}}, status_code=400)
    p = await request.json()
    sim: SimStore = request.app.state.sim
    if p.get("status") == "read":
        sim.q("UPDATE messages SET status='read' WHERE id=?", (p.get("message_id"),))
        if (p.get("typing_indicator") or {}).get("type") == "text":
            rows = sim.q("SELECT wa_id FROM messages WHERE id=? AND sender='user'", (p.get("message_id"),))
            if rows:
                sim.typing_until[rows[0]["wa_id"]] = time.time() + TYPING_TTL
        return JSONResponse({"success": True})
    if p.get("messaging_product") != "whatsapp" or not p.get("to") or p.get("type") not in ("text", "interactive", "image"):
        return JSONResponse({"error": {"message": "Invalid message payload", "code": 100}}, status_code=400)
    msg_id = _new_wamid()
    sim.typing_until.pop(p["to"], None)          # the reply replaces "typing…"
    sim.q("INSERT INTO messages (id,wa_id,sender,type,body,status,created_at) VALUES (?,?,?,?,?,?,?)",
          (msg_id, p["to"], "bot", p["type"], json.dumps(p), "delivered", time.time()))

    async def statuses():   # real WhatsApp reports sent + delivered back to the webhook
        for st in ("sent", "delivered"):
            await _post_webhook(request, _envelope({"statuses": [
                {"id": msg_id, "status": st, "timestamp": str(int(time.time())), "recipient_id": p["to"]}]}))
    request.app.state.conversations.spawn(statuses())
    return JSONResponse({"messaging_product": "whatsapp", "contacts": [{"input": p["to"], "wa_id": p["to"]}],
                         "messages": [{"id": msg_id}]})


# ---------------------------------------------------------------- the phone's side
async def api_send(request: Request):
    form = await request.form()
    wa_id = (form.get("wa_id") or "919999999999").strip()
    name = (form.get("name") or "Test user").strip()
    text = (form.get("text") or "").strip()
    files = [f for f in form.getlist("photos") if getattr(f, "filename", None)]
    s, sim = request.app.state.settings, request.app.state.sim
    sent = []
    for i, f in enumerate(files):
        data = await f.read()
        try:
            if s.get("simulator.compress_like_whatsapp", True):
                data = compress_like_whatsapp(data, s.get("simulator.max_side", 1600), s.get("simulator.jpeg_quality", 80))
        except Exception:   # noqa: BLE001
            return JSONResponse({"error": f"{f.filename} is not an image"}, status_code=400)
        media_id = str(uuid.uuid4().int)[:16]
        path = sim.media_dir / f"{media_id}.jpg"
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        sim.q("INSERT INTO media VALUES (?,?,?,?,?,?)", (media_id, str(path), "image/jpeg", sha, len(data), time.time()))
        msg_id = _new_wamid()
        caption = text if (text and i == len(files) - 1) else ""   # WhatsApp attaches the caption to one photo
        image = {"mime_type": "image/jpeg", "sha256": sha, "id": media_id}
        if caption:
            image["caption"] = caption
        msg = {"from": wa_id, "id": msg_id, "timestamp": str(int(time.time())), "type": "image", "image": image}
        sim.q("INSERT INTO messages (id,wa_id,sender,type,body,status,created_at) VALUES (?,?,?,?,?,?,?)",
              (msg_id, wa_id, "user", "image", json.dumps(msg), "sent", time.time()))
        await _post_webhook(request, _envelope({"contacts": _contacts(wa_id, name), "messages": [msg]}))
        sent.append(msg_id)
    if text and not files:
        msg_id = _new_wamid()
        msg = {"from": wa_id, "id": msg_id, "timestamp": str(int(time.time())), "type": "text", "text": {"body": text}}
        sim.q("INSERT INTO messages (id,wa_id,sender,type,body,status,created_at) VALUES (?,?,?,?,?,?,?)",
              (msg_id, wa_id, "user", "text", json.dumps(msg), "sent", time.time()))
        await _post_webhook(request, _envelope({"contacts": _contacts(wa_id, name), "messages": [msg]}))
        sent.append(msg_id)
    return JSONResponse({"sent": sent})


async def api_reply(request: Request):
    p = await request.json()
    wa_id, kind = p.get("wa_id", "919999999999"), p.get("kind", "button_reply")
    msg_id = _new_wamid()
    msg = {"from": wa_id, "id": msg_id, "timestamp": str(int(time.time())), "type": "interactive",
           "interactive": {"type": kind, kind: {"id": p.get("reply_id", ""), "title": p.get("title", "")}}}
    request.app.state.sim.q("INSERT INTO messages (id,wa_id,sender,type,body,status,created_at) VALUES (?,?,?,?,?,?,?)",
                            (msg_id, wa_id, "user", "interactive", json.dumps(msg), "sent", time.time()))
    await _post_webhook(request, _envelope({"contacts": _contacts(wa_id, p.get("name", "")), "messages": [msg]}))
    return JSONResponse({"sent": [msg_id]})


async def api_messages(request: Request):
    wa_id = request.query_params.get("wa_id", "919999999999")
    after = int(request.query_params.get("after", 0))
    rows = request.app.state.sim.q("SELECT * FROM messages WHERE wa_id=? AND seq>? ORDER BY seq", (wa_id, after))
    for r in rows:
        r["body"] = json.loads(r["body"])
    return JSONResponse(rows)


async def api_media(request: Request):
    rows = request.app.state.sim.q("SELECT * FROM media WHERE media_id=?", (request.path_params["media_id"],))
    if not rows:
        return PlainTextResponse("Not found", status_code=404)
    return Response(Path(rows[0]["path"]).read_bytes(), media_type=rows[0]["mime"])


async def api_presence(request: Request):
    wa_id = request.query_params.get("wa_id", "919999999999")
    return JSONResponse({"typing": request.app.state.sim.typing_until.get(wa_id, 0) > time.time()})


async def home(request: Request):
    return RedirectResponse("/sim/")


routes = [
    Route("/", home),
    Route("/sim/graph/{media_id}", graph_media_info, methods=["GET"]),
    Route("/sim/graph-media/{media_id}", graph_media_download, methods=["GET"]),
    Route("/sim/graph/{phone_number_id}/messages", graph_send, methods=["POST"]),
    Route("/sim/api/send", api_send, methods=["POST"]),
    Route("/sim/api/reply", api_reply, methods=["POST"]),
    Route("/sim/api/messages", api_messages),
    Route("/sim/api/media/{media_id}", api_media),
    Route("/sim/api/presence", api_presence),
    Mount("/sim", app=NoCacheStaticFiles(directory=str(STATIC), html=True), name="sim-static"),
]
