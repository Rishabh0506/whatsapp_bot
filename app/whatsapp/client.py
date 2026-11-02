"""Talks to the WhatsApp Cloud API (Graph API): fetch photos, send messages, mark as read.
Pointed at the built-in simulator or at Meta purely by settings."""
from __future__ import annotations

import logging

from .. import http
from ..config import WhatsAppConnection
from . import payloads

log = logging.getLogger("whatsapp")


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(self, conn: WhatsAppConnection):
        self.conn = conn

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.conn.access_token}"}

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Two steps, as in the Cloud API: GET /{media-id} -> short-lived URL, then GET the URL with the token."""
        r = await http.request("GET", f"{self.conn.base_url}/{media_id}", headers=self._auth)
        if r.status != 200:
            raise WhatsAppError(f"Media lookup failed ({r.status}): {r.text[:300]}")
        info = r.json()
        f = await http.request("GET", info["url"], headers={**self._auth, "User-Agent": "footwear-bot/1.0"}, timeout=60)
        if f.status != 200:
            raise WhatsAppError(f"Media download failed ({f.status})")
        return f.body, info.get("mime_type", "image/jpeg")

    async def send(self, payload: dict) -> dict:
        r = await http.request("POST", f"{self.conn.base_url}/{self.conn.phone_number_id}/messages",
                               headers=self._auth, json_body=payload)
        if r.status != 200:
            raise WhatsAppError(f"Send failed ({r.status}): {r.text[:300]}")
        return r.json()

    async def send_text(self, to: str, body: str) -> str:
        res = await self.send(payloads.text_message(to, body))
        return (res.get("messages") or [{}])[0].get("id", "")

    async def mark_read(self, message_id: str, typing: bool = False) -> None:
        try:
            await self.send(payloads.read_receipt(message_id, typing))
        except WhatsAppError as e:          # a failed read receipt must never break the conversation
            log.warning("mark_read failed: %s", e)
