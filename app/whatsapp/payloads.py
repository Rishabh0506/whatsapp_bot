"""WhatsApp Cloud API message formats: parsing incoming webhooks and building outgoing messages.
Both the simulator and real WhatsApp use exactly these formats."""
from __future__ import annotations

from dataclasses import dataclass, field

# Limits Meta enforces on outgoing messages
TEXT_MAX = 4096
INTERACTIVE_BODY_MAX = 1024
BUTTONS_MAX, BUTTON_TITLE_MAX = 3, 20
LIST_ROWS_MAX, LIST_ROW_TITLE_MAX, LIST_BUTTON_MAX = 10, 24, 20


@dataclass
class InboundMessage:
    id: str
    wa_id: str
    name: str
    timestamp: int
    type: str                      # text | image | audio | video | document | sticker | interactive | ...
    text: str = ""
    media_id: str = ""
    mime: str = ""
    caption: str = ""
    reply_id: str = ""             # interactive replies: id of the tapped button / list row
    raw: dict = field(default_factory=dict)


def parse_webhook(payload: dict) -> tuple[list[InboundMessage], list[dict]]:
    """Returns (messages, statuses) from a Cloud API webhook body. Meta may batch several in one call."""
    messages, statuses = [], []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", []) or []}
            for m in value.get("messages", []) or []:
                t = m.get("type", "unknown")
                msg = InboundMessage(id=m.get("id", ""), wa_id=m.get("from", ""), name=names.get(m.get("from"), ""),
                                     timestamp=int(m.get("timestamp") or 0), type=t, raw=m)
                if t == "text":
                    msg.text = (m.get("text") or {}).get("body", "")
                elif t in ("image", "audio", "video", "document", "sticker"):
                    media = m.get(t) or {}
                    msg.media_id, msg.mime, msg.caption = media.get("id", ""), media.get("mime_type", ""), media.get("caption", "")
                elif t == "interactive":
                    inter = m.get("interactive") or {}
                    rep = inter.get("button_reply") or inter.get("list_reply") or {}
                    msg.reply_id, msg.text = rep.get("id", ""), rep.get("title", "")
                elif t == "button":   # reply to a template button
                    msg.text = (m.get("button") or {}).get("text", "")
                messages.append(msg)
            statuses.extend(value.get("statuses", []) or [])
    return messages, statuses


def _base(to: str, type_: str) -> dict:
    return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": type_}


def text_message(to: str, body: str) -> dict:
    if len(body) > TEXT_MAX:
        raise ValueError(f"Text message longer than {TEXT_MAX} characters")
    return {**_base(to, "text"), "text": {"preview_url": False, "body": body}}


def buttons_message(to: str, body: str, buttons: list[tuple[str, str]]) -> dict:
    if not 1 <= len(buttons) <= BUTTONS_MAX:
        raise ValueError(f"Reply buttons: 1 to {BUTTONS_MAX} allowed")
    if len(body) > INTERACTIVE_BODY_MAX or any(len(t) > BUTTON_TITLE_MAX for _, t in buttons):
        raise ValueError("Reply buttons: body or button title too long")
    return {**_base(to, "interactive"), "interactive": {
        "type": "button", "body": {"text": body},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t}} for i, t in buttons]}}}


def list_message(to: str, body: str, button: str, rows: list[tuple[str, str]], section_title: str = "Options") -> dict:
    if not 1 <= len(rows) <= LIST_ROWS_MAX:
        raise ValueError(f"List message: 1 to {LIST_ROWS_MAX} rows allowed")
    if len(button) > LIST_BUTTON_MAX or any(len(t) > LIST_ROW_TITLE_MAX for _, t in rows):
        raise ValueError("List message: button or row title too long")
    return {**_base(to, "interactive"), "interactive": {
        "type": "list", "body": {"text": body},
        "action": {"button": button, "sections": [{"title": section_title,
                                                   "rows": [{"id": i, "title": t} for i, t in rows]}]}}}


def read_receipt(message_id: str, typing: bool = False) -> dict:
    """Blue ticks on the user's message. typing=True also shows "typing…" in the user's chat until the bot
    replies or 25 seconds pass (Cloud API typing indicator)."""
    p = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    if typing:
        p["typing_indicator"] = {"type": "text"}
    return p
