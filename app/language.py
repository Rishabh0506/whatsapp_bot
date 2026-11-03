"""Recognising what the customer typed: a greeting (start a fresh conversation), a language choice, or a request
to change the language ("language" / "भाषा").

Only a message that is *just* a greeting, *just* a language name or *just* the word for language counts.
"hi, my strap broke" is not a greeting, and "I don't understand Hindi well" does not change the language."""
from __future__ import annotations

import re

LANGS = ("en", "hi")

# The two reply buttons of the language question (WhatsApp allows up to 3, titles up to 20 characters).
BUTTONS = [("lang_en", "English"), ("lang_hi", "हिंदी")]
BUTTON_IDS = {"lang_en": "en", "lang_hi": "hi"}

# Typed words that choose a language (compared after clean_up()).
LANGUAGE_WORDS = {
    "english": "en", "eng": "en", "इंग्लिश": "en", "अंग्रेज़ी": "en", "अंग्रेजी": "en",
    "hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi",
}

# Typed words that bring up the language buttons. The value is the language the word is written in, which is
# the language the buttons' message is shown in ("language" -> "Change language", "भाषा" -> "भाषा बदलें").
CHANGE_LANGUAGE_WORDS = {
    "language": "en", "languages": "en", "change language": "en",
    "भाषा": "hi", "भाषा बदलें": "hi", "भाषा बदलो": "hi", "bhasha": "hi", "bhasa": "hi",
}

DEFAULT_GREETINGS = ["hi", "hii", "hiii", "hello", "helo", "hlo", "hey", "heyy", "hai",
                     "namaste", "namaskar", "नमस्ते", "नमस्कार"]


def clean_up(text: str) -> str:
    """Lower case, no punctuation, emoji or extra spaces. Keeps Hindi letters and their vowel signs."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^\wऀ-ॿ\s]", " ", text)   # \w drops emoji and punctuation; Devanagari kept
    return " ".join(text.replace("_", " ").split())


def is_greeting(text: str, greetings: list[str] | None = None) -> bool:
    words = {clean_up(g) for g in (greetings or DEFAULT_GREETINGS)}
    t = clean_up(text)
    if t in words:
        return True
    # "hiiii", "heyyy", "hellooo": stretched greetings
    return bool(re.fullmatch(r"hi+|hey+|hel+o+|hii+", t))


def change_language_request(text: str) -> str | None:
    """'en' / 'hi' (the language the word was typed in) when the message is just "language" / "भाषा", else None."""
    return CHANGE_LANGUAGE_WORDS.get(clean_up(text))


def language_choice(text: str = "", reply_id: str = "") -> str | None:
    """'en' / 'hi' when the message is a language button tap or just a language name, else None."""
    if reply_id in BUTTON_IDS:
        return BUTTON_IDS[reply_id]
    return LANGUAGE_WORDS.get(clean_up(text))
