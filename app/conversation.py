"""Conversation manager: what happens with each incoming WhatsApp message.

- skips duplicate deliveries (same message id)
- marks messages as read
- downloads photos and groups photos that arrive close together into one item
- runs the diagnosis core and sends the reply
- keeps per-user session state (needed later for follow-up questions) and the 24-hour window
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field

from . import replies
from .config import Settings
from .core.pipeline import DiagnosisService
from .storage import Storage
from .whatsapp.client import WhatsAppClient, WhatsAppError
from .whatsapp.payloads import InboundMessage, text_message

log = logging.getLogger("conversation")

SERVICE_WINDOW_SECONDS = 24 * 3600      # free-form replies only within 24h of the user's last message
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@dataclass
class PhotoBatch:
    photos: list = field(default_factory=list)     # (timestamp, message_id, media_id, bytes)
    timer: asyncio.Task | None = None


class ConversationManager:
    def __init__(self, settings: Settings, storage: Storage, client: WhatsAppClient, service: DiagnosisService):
        self.settings = settings
        self.storage = storage
        self.client = client
        self.service = service
        self.batches: dict[str, PhotoBatch] = {}
        self._tasks: set[asyncio.Task] = set()
        self.media_dir = settings.data_dir / "media"

    def spawn(self, coro) -> asyncio.Task:
        """Run in the background (the webhook must answer Meta immediately)."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task):
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("background task failed", exc_info=task.exception())

    async def handle_inbound(self, msg: InboundMessage) -> None:
        if not self.storage.add_message(msg.id, msg.wa_id, "in", msg.type, msg.timestamp, msg.raw):
            log.info("duplicate delivery of %s ignored", msg.id)
            return
        self.storage.touch_session(msg.wa_id, msg.name, msg.timestamp or int(time.time()))
        await self.client.mark_read(msg.id)
        if msg.type == "image":
            await self._add_photo(msg)
        elif msg.type in ("text", "interactive", "button"):
            await self.reply(msg.wa_id, replies.text_not_supported())
        else:
            await self.reply(msg.wa_id, replies.type_not_supported(msg.type))

    async def _add_photo(self, msg: InboundMessage) -> None:
        try:
            data, mime = await self.client.download_media(msg.media_id)
        except (WhatsAppError, KeyError) as e:
            log.warning("media download failed: %s", e)
            await self.reply(msg.wa_id, replies.media_failed())
            return
        folder = self.media_dir / msg.wa_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{msg.media_id}{EXT.get(mime, '.jpg')}"
        path.write_bytes(data)
        self.storage.add_media(msg.media_id, msg.wa_id, msg.id, path, mime,
                               hashlib.sha256(data).hexdigest(), len(data), msg.caption)

        batch = self.batches.setdefault(msg.wa_id, PhotoBatch())
        batch.photos.append((msg.timestamp, msg.id, msg.media_id, data))
        if batch.timer:
            batch.timer.cancel()
        batch.timer = self.spawn(self._diagnose_after_wait(msg.wa_id, batch))

    async def _diagnose_after_wait(self, wa_id: str, batch: PhotoBatch) -> None:
        await asyncio.sleep(self.settings.get("channel.batch_wait_seconds", 6))
        if self.batches.get(wa_id) is batch:
            del self.batches[wa_id]          # photos arriving from now on start a new item
        batch.timer = None
        photos = sorted(batch.photos, key=lambda p: (p[0], p[1]))
        await self.diagnose_and_reply(wa_id, [p[1] for p in photos], [p[2] for p in photos], [p[3] for p in photos])

    async def diagnose_and_reply(self, wa_id: str, message_ids: list, media_ids: list, images: list[bytes]) -> None:
        try:
            result = await self.service.diagnose(images)
        except Exception as e:   # noqa: BLE001 - any failure is logged and reported in the chat
            log.exception("diagnosis failed")
            self.storage.add_diagnosis(wa_id, message_ids, media_ids, None, f"{type(e).__name__}: {e}")
            await self.reply(wa_id, replies.error(e))
            return
        diag_id = self.storage.add_diagnosis(wa_id, message_ids, media_ids, result, None)
        await self.reply(wa_id, replies.diagnosis(result, diag_id))

    def within_service_window(self, wa_id: str) -> bool:
        last = self.storage.last_inbound_ts(wa_id)
        return last is not None and time.time() - last <= SERVICE_WINDOW_SECONDS

    async def reply(self, wa_id: str, body: str) -> None:
        if not self.within_service_window(wa_id):
            log.warning("not replying to %s: outside the 24-hour window (would need a template message)", wa_id)
            return
        payload = text_message(wa_id, body)
        try:
            msg_id = await self.client.send_text(wa_id, body)
        except WhatsAppError as e:
            log.error("sending reply failed: %s", e)
            return
        self.storage.add_message(msg_id or f"out-{time.time()}", wa_id, "out", "text", int(time.time()), payload)
