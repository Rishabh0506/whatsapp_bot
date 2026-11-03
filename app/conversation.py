"""Conversation manager: the customer journey (docs/USER_JOURNEY.md) for every incoming WhatsApp message.

- skips duplicate deliveries (same message id), marks messages as read
- keeps each customer's open conversation: language, photos, text, tries, timer (saved in data/bot.db)
- asks for the language first (English / Hindi buttons), keeping anything sent before that
- groups photos that arrive close together, diagnoses photos + the customer's text, and replies
- counts tries (photos, text-only retries, voice notes / videos); gives up after the last one
- a message that is only a greeting starts a fresh conversation
- closes a conversation 5 minutes after the bot's last real reply if the customer says nothing
- keeps or deletes the closed conversation's records (settings: records.keep_after_close)

Everything here uses only what the WhatsApp Cloud API offers (text, reply buttons, read receipts, typing
indicator), so it behaves the same in the simulator and on real WhatsApp.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import replies
from .config import Settings
from .core.pipeline import DiagnosisService
from .language import BUTTONS, change_language_request, is_greeting, language_choice
from .storage import Storage
from .whatsapp.client import WhatsAppClient, WhatsAppError
from .whatsapp.payloads import InboundMessage, buttons_message, text_message

log = logging.getLogger("conversation")

SERVICE_WINDOW_SECONDS = 24 * 3600      # free-form replies only within 24h of the user's last message
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
TEXT_TYPES = ("text", "interactive", "button")
VOICE_VIDEO = ("audio", "video")
IGNORED = ("reaction", "system", "ephemeral")          # nothing to answer
# Photos judged like this are left out of later tries in the same conversation.
SKIP_PHOTO = {"Blurry", "Not Footwear", "More Than One Item"}


@dataclass
class Conversation:
    """One customer's open conversation (= one case). Saved as JSON in sessions.state."""
    case: str
    started: float
    lang: str | None = None                            # "en" / "hi"; None until chosen
    photos: list = field(default_factory=list)         # {"media_id", "msg_id", "try", "skip"}
    texts: list = field(default_factory=list)          # {"msg_id", "text", "try"}
    tries: int = 0
    answered: bool = False                             # steps or cobbler suggestion sent
    reply_at: float | None = None                      # bot's last REAL reply; None while the bot owes a reply

    def usable_photos(self) -> list[dict]:
        return [p for p in self.photos if not p.get("skip")]

    @classmethod
    def from_dict(cls, d: dict) -> "Conversation":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Runtime:
    """Per-customer things that only live in memory."""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    batch: list = field(default_factory=list)          # photos waiting to be grouped into one item
    batch_seq: int = 0
    busy: bool = False                                 # the model is working on this customer's photos
    dirty: bool = False                                # a new photo / text arrived while it was working


class ConversationManager:
    def __init__(self, settings: Settings, storage: Storage, client: WhatsAppClient, service: DiagnosisService):
        self.settings = settings
        self.storage = storage
        self.client = client
        self.service = service
        self.media_dir = settings.data_dir / "media"
        self._rt: dict[str, Runtime] = {}
        self._tasks: set[asyncio.Task] = set()
        self._closer: asyncio.Task | None = None

    # ------------------------------------------------------------ settings
    @property
    def close_after(self) -> float:
        return float(self.settings.get("conversation.close_after_seconds", 300))

    @property
    def max_tries(self) -> int:
        return int(self.settings.get("conversation.max_tries", 3))

    @property
    def keep_records(self) -> bool:
        v = self.settings.get("records.keep_after_close", "auto")
        if v is None or str(v).lower() == "auto":
            return self.settings.get("channel.mode", "simulator") == "simulator"
        return v is True or str(v).lower() in ("true", "yes", "1")

    # ------------------------------------------------------------ background tasks
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

    def start(self) -> None:
        """Starts the regular check that closes quiet conversations (called when the server starts)."""
        if self._closer is None:
            now = time.time()
            for wa_id, state in self.storage.open_conversations():
                if not state.get("reply_at"):      # a reply was being prepared when the server stopped
                    conv = Conversation.from_dict(state)
                    conv.reply_at = now
                    self._save(wa_id, conv)
            self._closer = self.spawn(self._closer_loop())

    async def stop(self) -> None:
        if self._closer:
            self._closer.cancel()
            self._closer = None

    async def _closer_loop(self):
        while True:
            await asyncio.sleep(float(self.settings.get("conversation.check_every_seconds", 15)))
            try:
                await self.close_idle()
            except Exception:  # noqa: BLE001 - keep checking
                log.exception("closing idle conversations failed")

    async def close_idle(self, now: float | None = None) -> None:
        """Closes every conversation where the customer has said nothing for close_after seconds since the
        bot's last real reply. Sends the closing message, then forgets the conversation and the language."""
        now = now or time.time()
        for wa_id, state in self.storage.open_conversations():
            ra = state.get("reply_at")
            if not ra or now - ra < self.close_after:
                continue
            rt = self.rt(wa_id)
            async with rt.lock:
                conv = self._load(wa_id)
                if (conv and conv.reply_at and now - conv.reply_at >= self.close_after
                        and not rt.busy and not rt.batch):
                    await self._end(wa_id, conv, "timeout", closing=True)

    # ------------------------------------------------------------ state
    def rt(self, wa_id: str) -> Runtime:
        return self._rt.setdefault(wa_id, Runtime())

    def _load(self, wa_id: str) -> Conversation | None:
        state = self.storage.get_state(wa_id)
        return Conversation.from_dict(state) if state else None

    def _save(self, wa_id: str, conv: Conversation) -> None:
        self.storage.set_state(wa_id, asdict(conv))

    def _new(self, wa_id: str, lang: str | None = None) -> Conversation:
        conv = Conversation(case=f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
                            started=time.time(), lang=lang)
        self.storage.start_case(conv.case, wa_id, conv.started)
        self._save(wa_id, conv)
        return conv

    async def _end(self, wa_id: str, conv: Conversation, reason: str, closing: bool = False,
                   keep_language: bool = False) -> Conversation | None:
        """Ends the conversation (case). keep_language=True starts a new case right away in the same language
        (a new problem after an answer); otherwise the bot forgets the conversation and the language."""
        if closing:
            await self._send(wa_id, conv, replies.closing(conv.lang), real=False)
        self.storage.update_case(conv.case, ended_at=time.time(), end_reason=reason, tries=conv.tries, lang=conv.lang)
        if not self.keep_records:
            self.storage.delete_case(conv.case)
        self.rt(wa_id).dirty = False
        if keep_language:
            return self._new(wa_id, conv.lang)
        self.storage.set_state(wa_id, None)
        if not self.keep_records and reason in ("timeout", "tries"):
            self.storage.delete_session(wa_id)      # name + last message time; recreated by the next message
        log.info("conversation %s with %s ended (%s)", conv.case, wa_id, reason)
        return None

    # ------------------------------------------------------------ incoming messages
    async def handle_inbound(self, msg: InboundMessage) -> None:
        if not self.storage.add_message(msg.id, msg.wa_id, "in", msg.type, msg.timestamp, msg.raw):
            log.info("duplicate delivery of %s ignored", msg.id)
            return
        if msg.type in IGNORED:
            return
        self.storage.touch_session(msg.wa_id, msg.name, msg.timestamp or int(time.time()))
        await self.client.mark_read(msg.id)
        if msg.type == "image":
            await self._receive_photo(msg)
            return
        async with self.rt(msg.wa_id).lock:
            await self._on_message(msg)

    async def _receive_photo(self, msg: InboundMessage) -> None:
        rt = self.rt(msg.wa_id)
        try:
            data, mime = await self.client.download_media(msg.media_id)
        except (WhatsAppError, KeyError) as e:
            log.warning("media download failed: %s", e)
            async with rt.lock:
                conv = self._load(msg.wa_id)
                await self._send(msg.wa_id, conv, replies.media_failed(conv.lang if conv else None))
            return
        folder = self.media_dir / msg.wa_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{msg.media_id}{EXT.get(mime, '.jpg')}"
        path.write_bytes(data)
        self.storage.add_media(msg.media_id, msg.wa_id, msg.id, path, mime,
                               hashlib.sha256(data).hexdigest(), len(data), msg.caption)
        # WhatsApp sends each photo as its own message: photos arriving close together are one item
        async with rt.lock:
            rt.batch.append({"msg_id": msg.id, "media_id": msg.media_id, "caption": msg.caption or ""})
            rt.batch_seq += 1
            self.spawn(self._batch_after_wait(msg.wa_id, rt.batch_seq))

    async def _batch_after_wait(self, wa_id: str, seq: int) -> None:
        await asyncio.sleep(self.settings.get("channel.batch_wait_seconds", 6))
        rt = self.rt(wa_id)
        async with rt.lock:
            if rt.batch_seq != seq or not rt.batch:
                return                             # a later photo restarted the wait
            photos, rt.batch = rt.batch, []
            await self._on_photos(wa_id, photos)

    async def _on_photos(self, wa_id: str, photos: list[dict]) -> None:
        conv = self._load(wa_id)
        if conv is None:
            conv = self._new(wa_id)
        elif conv.answered:
            # "send a photo if there's another problem": a new case, same language, tries start again
            conv = await self._end(wa_id, conv, "solved", keep_language=True)
        for p in photos:
            conv.photos.append({"media_id": p["media_id"], "msg_id": p["msg_id"], "try": None, "skip": False})
            self.storage.set_message_case(p["msg_id"], conv.case)
            self.storage.set_media_case(p["media_id"], conv.case)
            caption = p["caption"].strip()
            if caption:
                choice = language_choice(caption)
                if choice:
                    conv.lang = choice
                elif not is_greeting(caption, self.settings.get("conversation.greetings")):
                    conv.texts.append({"msg_id": p["msg_id"], "text": caption, "try": None})
        conv.reply_at = None
        self._save(wa_id, conv)
        if conv.lang is None:
            await self._ask_language(wa_id, conv)     # the photos are kept and used once a language is chosen
            return
        rt = self.rt(wa_id)
        if rt.busy:
            rt.dirty = True                          # the running diagnosis looks again with these photos
            return
        await self._start_try(wa_id, conv, photos[-1]["msg_id"], new_photo=True)

    async def _on_message(self, msg: InboundMessage) -> None:
        """Everything except photos. Runs under the customer's lock."""
        wa_id = msg.wa_id
        text = msg.text if msg.type in TEXT_TYPES else ""
        conv = self._load(wa_id)

        if msg.type in TEXT_TYPES and is_greeting(text, self.settings.get("conversation.greetings")):
            if conv:
                await self._end(wa_id, conv, "greeting")
            conv = self._new(wa_id)
            self.storage.set_message_case(msg.id, conv.case)
            await self._ask_language(wa_id, conv)
            return

        if conv is None:
            conv = self._new(wa_id)
        self.storage.set_message_case(msg.id, conv.case)
        conv.reply_at = None

        word_lang = change_language_request(text) if msg.type == "text" else None
        if word_lang:
            # "language" / "भाषा": the two language buttons, in the language of the word typed. Not a try.
            self._save(wa_id, conv)
            await self._send(wa_id, conv, replies.change_language(word_lang), buttons=BUTTONS)
            return

        choice = language_choice(text, msg.reply_id) if msg.type in TEXT_TYPES else None
        if choice:
            first = conv.lang is None
            conv.lang = choice
            self._save(wa_id, conv)
            if first:
                await self._after_language(wa_id, conv, msg.id)
            else:
                await self._send(wa_id, conv, replies.language_changed(choice))
            return

        if conv.lang is None:                        # waiting for the language: keep what they wrote, ask again
            if text.strip():
                conv.texts.append({"msg_id": msg.id, "text": text, "try": None})
            self._save(wa_id, conv)
            await self._ask_language(wa_id, conv)
            return

        lang = conv.lang
        if msg.type in VOICE_VIDEO:
            await self._voice_or_video(wa_id, conv)
            return
        if msg.type not in TEXT_TYPES:
            self._save(wa_id, conv)
            await self._send(wa_id, conv, replies.type_not_supported(msg.type, lang))
            return
        if conv.answered:                            # free questions are not answered yet
            self._save(wa_id, conv)
            await self._send(wa_id, conv, replies.after_answer(lang))
            return

        conv.texts.append({"msg_id": msg.id, "text": text, "try": None})
        self._save(wa_id, conv)
        rt = self.rt(wa_id)
        if rt.busy:
            rt.dirty = True                          # the running diagnosis looks again with this text
            return
        if rt.batch:
            return                                   # photos are being grouped; the text goes with them
        if not conv.usable_photos():
            await self._send(wa_id, conv, replies.need_photo(lang))
            return
        # text after a request for a closer photo: look again at the photos we have, with the text (a try)
        await self._start_try(wa_id, conv, msg.id, new_photo=False)

    async def _after_language(self, wa_id: str, conv: Conversation, trigger_id: str) -> None:
        if conv.usable_photos():
            await self._start_try(wa_id, conv, trigger_id, new_photo=True)
        else:
            await self._send(wa_id, conv, replies.ask_photo(conv.lang))

    async def _ask_language(self, wa_id: str, conv: Conversation) -> None:
        await self._send(wa_id, conv, replies.language_question(), buttons=BUTTONS)

    async def _voice_or_video(self, wa_id: str, conv: Conversation) -> None:
        if conv.answered:
            self._save(wa_id, conv)
            await self._send(wa_id, conv, replies.voice_or_video(conv.lang))
            return
        conv.tries += 1                              # team decision: a voice note or video counts as a try
        self._save(wa_id, conv)
        if conv.tries >= self.max_tries and not self.rt(wa_id).busy:
            await self._send(wa_id, conv, replies.tries_used_up(conv.lang, voice=True), real=False)
            await self._end(wa_id, conv, "tries")
        else:
            await self._send(wa_id, conv, replies.voice_or_video(conv.lang))

    # ------------------------------------------------------------ diagnosis
    async def _start_try(self, wa_id: str, conv: Conversation, trigger_id: str, new_photo: bool) -> None:
        conv.tries += 1
        self._save(wa_id, conv)
        rt = self.rt(wa_id)
        rt.busy, rt.dirty = True, False
        await self._send(wa_id, conv, replies.please_wait(conv.lang), real=False)   # does not start the timer
        # the customer sees "typing…" while the model works (WhatsApp hides it after 25 s or when we reply)
        await self.client.mark_read(trigger_id, typing=True)
        self.spawn(self._run_try(wa_id, conv.case, conv.tries, trigger_id, new_photo))

    async def _run_try(self, wa_id: str, case: str, try_no: int, trigger_id: str, new_photo: bool) -> None:
        rt = self.rt(wa_id)
        max_images = int(self.settings.get("core.max_images_per_item", 5))
        try:
            while True:
                async with rt.lock:
                    conv = self._load(wa_id)
                    if not conv or conv.case != case:
                        rt.busy = False
                        return
                    rt.dirty = False
                    for item in conv.photos + conv.texts:
                        if item.get("try") is None:
                            item["try"] = try_no
                    self._save(wa_id, conv)
                    photos = conv.usable_photos()[-max_images:]
                    texts = [t for t in conv.texts if t["text"].strip()]
                    text = "\n".join(t["text"] for t in texts)
                    images = []
                    for p in photos:
                        path = self.storage.media_path(p["media_id"])
                        if path and Path(path).exists():
                            images.append(Path(path).read_bytes())
                message_ids = [p["msg_id"] for p in photos] + [t["msg_id"] for t in texts]
                media_ids = [p["media_id"] for p in photos]

                result, error = None, None
                try:
                    if not images:
                        raise RuntimeError("no photo files found for this conversation")
                    result = await self.service.diagnose(images, text)
                except Exception as e:  # noqa: BLE001 - any failure is logged and reported in the chat
                    log.exception("diagnosis failed")
                    error = f"{type(e).__name__}: {e}"

                async with rt.lock:
                    conv = self._load(wa_id)
                    if not conv or conv.case != case:          # fresh start / closed while the model worked
                        self.storage.log_usage(result, error)
                        rt.busy = False
                        return
                    diag_id = self.storage.add_diagnosis(wa_id, message_ids, media_ids, result, error,
                                                         case_id=case, try_no=try_no, lang=conv.lang,
                                                         customer_text=text or None)
                    if rt.dirty:
                        # a new photo or text arrived while the model was working: look again (same try)
                        await self.client.mark_read(trigger_id, typing=True)
                        continue
                    rt.busy = False
                    await self._apply(wa_id, conv, result, error, diag_id, try_no, new_photo)
                    return
        finally:
            rt.busy = False

    async def _apply(self, wa_id: str, conv: Conversation, result: dict | None, error: str | None,
                     diag_id: int, try_no: int, new_photo: bool) -> None:
        lang = conv.lang
        if error:
            conv.tries = max(0, conv.tries - 1)        # our failure, not the customer's: doesn't count as a try
            body = replies.error(None, lang)
            self.storage.set_diagnosis_reply(diag_id, body)
            await self._send(wa_id, conv, body)
            return

        action = result["decision"]["action"]
        if (result["fields"].get("image_status") or {}).get("value") in SKIP_PHOTO:
            for p in conv.photos:                      # leave these photos out of the next try
                if p.get("try") == try_no:
                    p["skip"] = True

        if action in ("accept", "cobbler"):
            conv.answered = True
            body = replies.diagnosis(result, lang, new_photo)
            self.storage.update_case(conv.case, outcome="solved" if action == "accept" else "cobbler")
            self.storage.set_diagnosis_reply(diag_id, body)
            await self._send(wa_id, conv, body)
        elif conv.tries >= self.max_tries:
            body = replies.tries_used_up(lang)
            self.storage.update_case(conv.case, outcome="tries_used_up")
            self.storage.set_diagnosis_reply(diag_id, body)
            await self._send(wa_id, conv, body, real=False)
            await self._end(wa_id, conv, "tries")     # closes right away, no separate closing message
        else:
            body = replies.diagnosis(result, lang, new_photo)
            self.storage.set_diagnosis_reply(diag_id, body)
            await self._send(wa_id, conv, body)

    # ------------------------------------------------------------ sending
    def within_service_window(self, wa_id: str) -> bool:
        last = self.storage.last_inbound_ts(wa_id)
        return last is not None and time.time() - last <= SERVICE_WINDOW_SECONDS

    async def _send(self, wa_id: str, conv: Conversation | None, body: str, real: bool = True,
                    buttons: list[tuple[str, str]] | None = None) -> None:
        """Sends a message. real=True (an answer or a question) starts the 5-minute timer; "please wait" and
        closing messages use real=False."""
        if not self.within_service_window(wa_id):
            log.warning("not replying to %s: outside the 24-hour window (would need a template message)", wa_id)
            return
        payload = buttons_message(wa_id, body, buttons) if buttons else text_message(wa_id, body)
        try:
            msg_id = await (self.client.send_buttons(wa_id, body, buttons) if buttons
                            else self.client.send_text(wa_id, body))
        except WhatsAppError as e:
            log.error("sending reply failed: %s", e)
            return
        self.storage.add_message(msg_id or f"out-{uuid.uuid4().hex}", wa_id, "out", payload["type"],
                                 int(time.time()), payload, case_id=conv.case if conv else None)
        if real and conv is not None:
            conv.reply_at = time.time()
            self._save(wa_id, conv)

    async def reply(self, wa_id: str, body: str) -> None:
        """Plain text reply outside the journey (kept for scripts and tests)."""
        await self._send(wa_id, self._load(wa_id), body, real=False)
