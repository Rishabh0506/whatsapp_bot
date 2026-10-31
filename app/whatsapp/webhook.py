"""The webhook endpoint, built exactly as Meta's WhatsApp Cloud API expects it.

GET  /webhook  - Meta's one-time verification handshake (hub.challenge)
POST /webhook  - every incoming message / status; checked with X-Hub-Signature-256,
                 answered with 200 at once, processed in the background.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from .payloads import parse_webhook

log = logging.getLogger("webhook")


def valid_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret:
        return True            # no secret configured (not recommended for real WhatsApp)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


async def verify(request: Request) -> Response:
    conn = request.app.state.wa_conn
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == conn.verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    return PlainTextResponse("Forbidden", status_code=403)


async def receive(request: Request) -> Response:
    state = request.app.state
    body = await request.body()
    if not valid_signature(state.wa_conn.app_secret, body, request.headers.get("X-Hub-Signature-256")):
        log.warning("webhook rejected: bad signature")
        return PlainTextResponse("Invalid signature", status_code=401)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return PlainTextResponse("Bad JSON", status_code=400)
    messages, statuses = parse_webhook(payload)
    for st in statuses:
        state.storage.add_status(st.get("id"), st.get("status"), int(st.get("timestamp") or 0), st)
    for msg in messages:
        state.conversations.spawn(state.conversations.handle_inbound(msg))
    return PlainTextResponse("EVENT_RECEIVED")


routes = [Route("/webhook", verify, methods=["GET"]), Route("/webhook", receive, methods=["POST"])]
