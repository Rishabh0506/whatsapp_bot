"""The customer journey (docs/USER_JOURNEY.md), driven through the conversation manager with a fake WhatsApp
client and a scripted model, so every rule can be checked exactly. No network, no API key."""
import asyncio
import io
import json
import re
import time
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.config import Settings
from app.conversation import ConversationManager
from app.core.pipeline import DiagnosisService
from app.core.providers.base import Provider, ProviderOutput
from app.core.reference import Reference
from app.storage import Storage
from app.whatsapp.payloads import InboundMessage

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def answer(**over):
    base = {
        "visible_evidence": "Brown leather formal shoe, sole lifting at the toe.",
        "image_status": {"value": "Usable", "confidence": 0.95},
        "footwear_type": {"value": "Formal Shoes", "confidence": 0.9},
        "part": {"value": "Sole", "confidence": 0.92},
        "issue_category": {"value": "Breakage / Crack / Gaps", "confidence": 0.9},
        "damage_mode": {"value": "Sole Separation - Partial", "confidence": 0.88},
        "secondary_issue": {"issue_category": "None", "damage_mode": "None", "confidence": 0.8},
        "receiving_substrate": {"value": "Leather", "confidence": 0.85},
        "applied_substrate": {"value": "Rubber", "confidence": 0.82},
        "damage_extent": {"value": "Small / Localised", "confidence": 0.81},
        "glue_fix_possible": {"value": "Yes", "confidence": 0.9},
        "observation_note": "",
    }
    base.update(over)
    return base


ACCEPT = answer()
BLURRY = answer(image_status={"value": "Blurry", "confidence": 0.9})
NOT_FOOTWEAR = answer(image_status={"value": "Not Footwear", "confidence": 0.9})
FOLLOW_UP = answer(receiving_substrate={"value": "Leather", "confidence": 0.6})
COBBLER = answer(glue_fix_possible={"value": "No – Weight-Bearing Part", "confidence": 0.9},
                 receiving_substrate={"value": "Leather", "confidence": 0.3})


class Scripted(Provider):
    """A model that answers from a list (the last answer repeats) and records what it was given."""
    name = model = "scripted"

    def __init__(self, *answers, delay=0.0):
        self.answers, self.calls, self.delay = list(answers) or [ACCEPT], [], delay

    async def diagnose(self, images, instructions, schema, text=""):
        self.calls.append({"images": len(images), "text": text})
        await asyncio.sleep(self.delay)
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return ProviderOutput(a, json.dumps(a), self.model, {"total_tokens": 10, "cost_usd": 0.001})


class FakeClient:
    """Stands in for the WhatsApp Cloud API client: records what the bot sends."""

    def __init__(self):
        self.sent, self.reads, self.media = [], [], {}

    async def download_media(self, media_id):
        return self.media[media_id], "image/jpeg"

    async def send_text(self, to, body):
        self.sent.append({"kind": "text", "body": body})
        return f"wamid.OUT{len(self.sent)}"

    async def send_buttons(self, to, body, buttons):
        self.sent.append({"kind": "buttons", "body": body, "buttons": buttons})
        return f"wamid.OUT{len(self.sent)}"

    async def mark_read(self, message_id, typing=False):
        self.reads.append((message_id, typing))


class Harness:
    WA = "919800000100"

    def __init__(self, config_dir, tmp_path, provider, **overrides):
        self.settings = Settings.load(config_dir, tmp_path / "data", overrides={
            "core.provider": "mock", "channel.batch_wait_seconds": 0.05, **overrides})
        self.storage = Storage(tmp_path / "data" / "bot.db")
        self.client = FakeClient()
        self.provider = provider
        service = DiagnosisService(self.settings, Reference.load(config_dir), provider)
        self.mgr = ConversationManager(self.settings, self.storage, self.client, service)
        self.colour = 0

    def _msg(self, type_, **kw):
        return InboundMessage(id="wamid.IN" + uuid.uuid4().hex, wa_id=self.WA, name="Ravi",
                              timestamp=int(time.time()), type=type_, **kw)

    async def settle(self):
        for _ in range(500):
            if not self.mgr._tasks:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("background work did not finish")

    async def text(self, body, settle=True):
        await self.mgr.handle_inbound(self._msg("text", text=body))
        if settle:
            await self.settle()

    async def tap(self, reply_id, title):
        await self.mgr.handle_inbound(self._msg("interactive", reply_id=reply_id, text=title))
        await self.settle()

    async def photo(self, caption="", settle=True):
        self.colour += 40
        buf = io.BytesIO()
        Image.new("RGB", (200, 150), (self.colour % 255, 80, 40)).save(buf, "JPEG")
        media_id = uuid.uuid4().hex[:12]
        self.client.media[media_id] = buf.getvalue()
        await self.mgr.handle_inbound(self._msg("image", media_id=media_id, mime="image/jpeg", caption=caption))
        if settle:
            await self.settle()

    async def other(self, type_):
        await self.mgr.handle_inbound(self._msg(type_, media_id=uuid.uuid4().hex[:8]))
        await self.settle()

    async def english(self):
        await self.tap("lang_en", "English")

    @property
    def conv(self):
        return self.mgr._load(self.WA)

    @property
    def last(self):
        return self.client.sent[-1]["body"]

    def answers(self):
        """Bot messages that are not 'please wait'."""
        return [m["body"] for m in self.client.sent if "taking a look" not in m["body"] and "देख रहे हैं" not in m["body"]]

    def count(self, table, where="1=1", args=()):
        return self.storage._all(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", args)[0]["n"]


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def make(config_dir, tmp_path):
    return lambda provider=None, **o: Harness(config_dir, tmp_path, provider or Scripted(), **o)


# ---------------------------------------------------------------- language first
def test_photo_before_language_is_kept_then_diagnosed_in_hindi(make):
    h = make()

    async def go():
        await h.photo()
        assert h.client.sent[-1]["kind"] == "buttons"
        assert h.client.sent[-1]["buttons"] == [("lang_en", "English"), ("lang_hi", "हिंदी")]
        body = h.last
        assert "Which language" in body and "किस भाषा" in body and "English or Hindi" in body
        assert h.provider.calls == []                          # nothing diagnosed before the language
        await h.tap("lang_hi", "हिंदी")
        assert len(h.provider.calls) == 1 and h.provider.calls[0]["images"] == 1   # the kept photo
        final = h.last
        assert DEVANAGARI.search(final) and "फ़ोटो के लिए धन्यवाद" in final
        for internal in ("Glue Fix", "Damage Mode", "0.9", "accept", "Sole Separation"):
            assert internal not in final
        assert any("देख रहे हैं" in m["body"] for m in h.client.sent)          # please-wait, in Hindi
        c = h.conv
        assert c.lang == "hi" and c.tries == 1 and c.answered
    run(go())


def test_text_before_photo_asks_for_photo_and_is_used_later(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        assert "send a photo" in h.last
        await h.text("sole niche se nikal gaya hai")
        assert "send a photo" in h.last and h.conv.tries == 0 and h.provider.calls == []
        await h.text("what's your name?")                     # off-topic: same request, not a try
        assert "send a photo" in h.last and h.conv.tries == 0
        await h.photo()
        assert "sole niche se nikal gaya hai" in h.provider.calls[0]["text"]
        assert h.conv.tries == 1
    run(go())


def test_typing_language_name_switches_but_a_sentence_does_not(make):
    h = make()

    async def go():
        await h.text("hello")
        await h.text("Hindi")                                  # typed instead of tapping: accepted
        assert h.conv.lang == "hi" and DEVANAGARI.search(h.last)
        await h.text("english!")
        assert h.conv.lang == "en" and "reply in English" in h.last
        await h.photo()
        await h.text("I don't understand Hindi well")          # a sentence: no switch
        assert h.conv.lang == "en"
        await h.tap("lang_hi", "हिंदी")                          # an old button, tapped later: switches
        assert h.conv.lang == "hi" and "हिंदी में जवाब" in h.last and h.conv.answered
    run(go())


def test_typing_language_shows_the_buttons_in_the_language_of_the_word(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        tries = h.conv.tries
        await h.text("language")
        m = h.client.sent[-1]
        assert m["kind"] == "buttons" and m["body"] == "🌐 Change language"
        assert m["buttons"] == [("lang_en", "English"), ("lang_hi", "हिंदी")]
        await h.text("भाषा")
        assert h.client.sent[-1]["kind"] == "buttons" and h.last == "🌐 भाषा बदलें"
        assert h.conv.lang == "en" and h.conv.tries == tries      # nothing changes until a button is tapped
        await h.tap("lang_hi", "हिंदी")
        assert h.conv.lang == "hi" and "हिंदी में जवाब" in h.last
        await h.text("Language")                                   # English word -> English, even in Hindi
        assert h.last == "🌐 Change language"
    run(go())


def test_typing_language_before_choosing_shows_only_that_language(make):
    h = make()

    async def go():
        await h.text("भाषा")
        assert h.client.sent[-1]["kind"] == "buttons" and h.last == "🌐 भाषा बदलें"
        await h.tap("lang_hi", "हिंदी")
        assert h.conv.lang == "hi" and "फ़ोटो भेजें" in h.last
    run(go())


def test_anything_else_while_waiting_for_language_asks_again(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.text("my sandal broke")
        assert h.client.sent[-1]["kind"] == "buttons" and len(h.client.sent) == 2
        await h.english()
        assert "send a photo" in h.last                         # text kept, but a photo is still needed
        await h.photo()
        assert "my sandal broke" in h.provider.calls[0]["text"]
    run(go())


# ---------------------------------------------------------------- fresh start
def test_greeting_starts_a_fresh_conversation(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        old = h.conv.case
        await h.text("Hii!!")
        c = h.conv
        assert c.case != old and c.lang is None and c.tries == 0 and c.photos == []
        assert h.client.sent[-1]["kind"] == "buttons"
        assert h.storage.get_case(old)["end_reason"] == "greeting"
        await h.text("hi, my strap is broken")                  # not just a greeting: no fresh start
        assert h.conv.case == c.case
    run(go())


# ---------------------------------------------------------------- tries
def test_three_unusable_photos_then_try_again_and_close(make):
    h = make(Scripted(BLURRY, NOT_FOOTWEAR, BLURRY))

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        assert "blurry" in h.last and h.conv.tries == 1
        await h.photo()
        assert "couldn't find any footwear" in h.last and "not valid" not in h.last.lower()
        assert h.conv.tries == 2
        case = h.conv.case
        await h.photo()
        assert "try again with a clear picture" in h.last
        assert h.conv is None                                   # closed right away
        assert "closing this chat" not in h.last                 # no separate closing message
        assert h.storage.get_case(case)["end_reason"] == "tries"
        assert len(h.provider.calls) == 3
        # blurry / not-footwear photos are left out of later tries
        assert [c["images"] for c in h.provider.calls] == [1, 1, 1]
        await h.photo()                                         # next message: a new conversation
        assert h.client.sent[-1]["kind"] == "buttons"
    run(go())


def test_voice_and_video_count_as_tries(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        await h.other("audio")
        assert "can't open voice notes or videos" in h.last and h.conv.tries == 1
        await h.other("video")
        assert h.conv.tries == 2
        await h.other("audio")
        assert "voice notes" in h.last and "try again with a clear picture" in h.last and h.conv is None
        assert h.provider.calls == []
    run(go())


def test_sticker_is_not_a_try(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        await h.other("sticker")
        assert "can't open that kind of message" in h.last and h.conv.tries == 0
    run(go())


def test_text_after_closer_photo_request_retries_with_existing_photos(make):
    h = make(Scripted(FOLLOW_UP, ACCEPT))

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        assert "close up" in h.last and h.conv.tries == 1
        await h.text("it's the leather part")
        assert len(h.provider.calls) == 2
        assert h.provider.calls[1] == {"images": 1, "text": "it's the leather part"}
        assert h.conv.tries == 2 and h.conv.answered
        assert "Thanks!" in h.last and "Thanks for the photo" not in h.last
    run(go())


def test_photo_while_checking_is_added_to_the_same_try(make):
    h = make(Scripted(ACCEPT, delay=0.3))

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo(settle=False)
        await asyncio.sleep(0.15)                               # grouped, the model is now working
        assert h.mgr.rt(h.WA).busy
        await h.photo(settle=False)
        await h.settle()
        assert [c["images"] for c in h.provider.calls] == [1, 2]   # looked again with both photos
        assert h.conv.tries == 1
        assert len([m for m in h.answers() if "Here's what I can see" in m]) == 1   # one answer only
    run(go())


def test_model_error_is_not_a_try(make):
    class Broken(Scripted):
        async def diagnose(self, *a, **k):
            raise RuntimeError("model down")
    h = make(Broken())

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        assert "something went wrong" in h.last and "model down" not in h.last
        assert h.conv.tries == 0
    run(go())


# ---------------------------------------------------------------- answers
def test_clear_cobbler_case_asks_no_more_questions(make):
    h = make(Scripted(COBBLER))

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        assert "cobbler" in h.last and "close up" not in h.last and "[Product" not in h.last
        assert h.conv.answered and h.storage.get_case(h.conv.case)["outcome"] == "cobbler"
    run(go())


def test_after_the_answer(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        assert "[Product recommendation" in h.last              # placeholder until the solution rules arrive
        first = h.conv.case
        await h.text("which glue did you say?")
        assert "answer is in the message above" in h.last and h.conv.tries == 1
        await h.photo()                                          # another problem: new case, same language
        c = h.conv
        assert c.case != first and c.lang == "en" and c.tries == 1
        assert h.storage.get_case(first)["end_reason"] == "solved"
        assert not any(m["kind"] == "buttons" for m in h.client.sent[3:])
    run(go())


# ---------------------------------------------------------------- 5-minute close
def test_quiet_for_five_minutes_after_a_real_reply_closes(make):
    h = make(Scripted(ACCEPT, delay=0.3))

    async def go():
        await h.text("hi")
        await h.text("hindi")
        await h.photo(settle=False)
        await asyncio.sleep(0.15)
        # while the bot is still working ("please wait" sent), the timer is not running
        await h.mgr.close_idle(now=time.time() + 3600)
        assert h.conv is not None and h.conv.reply_at is None
        await h.settle()
        await h.mgr.close_idle(now=time.time() + 200)            # not yet 5 minutes
        assert h.conv is not None
        case = h.conv.case
        await h.mgr.close_idle(now=time.time() + 301)
        assert h.conv is None
        assert "चैट बंद" in h.last and "closing" not in h.last   # closing message in the chosen language
        assert h.storage.get_case(case)["end_reason"] == "timeout"
        await h.text("ok")                                       # language forgotten: asked again
        assert h.client.sent[-1]["kind"] == "buttons"
    run(go())


def test_closing_before_a_language_is_chosen_is_in_both_languages(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.mgr.close_idle(now=time.time() + 301)
        assert "closing this chat" in h.last and "चैट बंद" in h.last
    run(go())


# ---------------------------------------------------------------- records
def test_records_kept_while_testing(make):
    h = make()

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        case = h.conv.case
        await h.mgr.close_idle(now=time.time() + 301)
        assert h.count("diagnoses", "case_id=?", (case,)) == 1
        d = h.storage.list_diagnoses()[0]
        assert d["case_id"] == case and d["try_no"] == 1 and d["lang"] == "en" and "Here's what" in d["reply"]
        assert h.count("media", "case_id=?", (case,)) == 1
        assert h.count("messages", "case_id=? AND payload IS NOT NULL", (case,)) >= 5
        assert h.storage.get_case(case)["outcome"] == "solved"
    run(go())


def test_records_deleted_for_real_customers(make):
    h = make(**{"records.keep_after_close": "auto", "channel.mode": "whatsapp"})
    assert h.mgr.keep_records is False

    async def go():
        await h.text("hi")
        await h.english()
        await h.photo()
        case = h.conv.case
        photo = Path(h.storage._all("SELECT path FROM media")[0]["path"])
        assert photo.exists() and h.count("diagnoses") == 1
        await h.mgr.close_idle(now=time.time() + 301)
        assert h.count("diagnoses") == 0 and h.count("media") == 0 and not photo.exists()
        assert h.count("cases") == 0 and h.count("sessions") == 0
        assert h.count("messages", "payload IS NOT NULL OR wa_id IS NOT NULL") == 0
        assert h.count("usage_log") == 1                          # cost numbers kept, no customer data
        cols = {r["name"] for r in h.storage._all("PRAGMA table_info(usage_log)")}
        assert not cols & {"wa_id", "text", "media_ids", "result"}
        assert case
    run(go())
