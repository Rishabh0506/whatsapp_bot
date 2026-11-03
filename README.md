# Footwear helpline bot

**New here? Read [PROJECT_LOG.md](PROJECT_LOG.md) first**: what this is, where things stand, where data is
stored, and what has been done and why.

Send a photo of damaged footwear in a WhatsApp-style chat and get a plain-language reply in English or Hindi.
The conversation follows the agreed customer journey ([docs/USER_JOURNEY.md](docs/USER_JOURNEY.md)): language
first, up to 3 tries, closes after 5 quiet minutes. Behind the scenes the
bot fills the **10 diagnosis fields**, each with a **confidence score**, and decides what to do from the confidence
rules (model: Gemini through OpenRouter); that internal view is on a separate backend dashboard. The backend speaks the real WhatsApp Cloud
API format, so moving from the simulator to WhatsApp is a settings change. Design: [docs/DESIGN.md](docs/DESIGN.md).

## First-time setup (Windows)

1. **Python 3.11+** must be installed.
2. Copy `.env.example` to `.env` and put your OpenRouter key after `OPENROUTER_API_KEY=`
   (create one at https://openrouter.ai/settings/keys). The bot uses Gemini models through OpenRouter.
3. Double-click **`run.bat`**. The first run creates `.venv`, installs the packages and imports the reference
   workbooks. Or in a Command Prompt in this folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   python scripts\import_reference.py
   python run.py
   ```
4. Open **http://127.0.0.1:8000** (the chat, what the customer sees) — say hi or attach a photo, pick a
   language, and send a photo.
   Open **http://127.0.0.1:8001** for the backend dashboard (fields, scores, decisions). Both start with `run.py`.

Check that your key works, how much it has used, and which Gemini models you can use:
```
python scripts\check_gemini.py
```
If the model in `config/settings.yaml` (`openrouter.model`) isn't in that list, change it to one that is.

Diagnose photos straight from the command line (no chat):
```
python scripts\check_gemini.py path\to\photo.jpg [more photos of the same item] [--raw]
```

## Using the simulator

- **Chat (port 8000):** the customer's WhatsApp, laid out like WhatsApp Web, showing only what the customer
  would see. Press **+** (or drag/paste photos in), add a caption, send. Photos sent within 6 seconds of each other
  are treated as one item. **+** also takes an audio or video file, sent as a voice note / video (the bot can't
  open those yet and says so). Ticks turn blue when the bot reads them, and the header shows "typing…" while the bot
  works (WhatsApp hides it after 25 seconds). WhatsApp formatting (*bold*, _italic_, ~strike~) renders as in the
  app. The bot answers in plain language (wording in `app/replies.py`).
- **The journey in short:** the bot first asks for the language (buttons **English / हिंदी**; typing "English" or
  "Hindi" also works, any time; typing "language" or "भाषा" brings the buttons back). It reads photos and what you type (Hinglish too). Each photo, text-only retry,
  voice note or video is a try; after 3 tries without an answer it asks you to try again with a clear picture and
  closes the chat. "hi" (on its own) starts afresh. If you don't reply for 5 minutes after the bot's answer or
  question, it sends a closing message and forgets the chat and the language. Full rules:
  [docs/USER_JOURNEY.md](docs/USER_JOURNEY.md).
- **To try the 5-minute close quickly,** set `conversation.close_after_seconds` lower (e.g. 30) and restart.
- **Test customer (avatar, bottom left):** change the name or phone number, or start a new test customer. Each
  number is a separate customer with their own chat history.
- **Why a simulator:** the bot talks to this page only through a fake copy of Meta's Cloud API (same webhook
  payloads, signatures, media download, send/read/typing calls). Switching to real WhatsApp is
  `channel.mode: whatsapp` plus the `WHATSAPP_*` values in `.env`; the bot's code doesn't change and this page
  simply isn't used any more.
- **Backend dashboard (port 8001):** the latest diagnosis only: the conversation it belongs to (try number,
  language, open or closed), the 10 fields with value, confidence bar (marks at the two bands), status, the
  model's original answer where a rule changed it, the decision, warnings, what the customer wrote, the raw model
  output and what the customer was told. In simulator mode closed conversations stay in `data/bot.db`; with real
  WhatsApp they are deleted when they close (`records.keep_after_close`), so the dashboard shows a case only while
  its conversation is open. It only listens on 127.0.0.1 and is
  never on the bot's port, so it stays private when the bot port goes public for real WhatsApp.

## Common changes

| To… | Edit |
|---|---|
| change the prompt | `config/prompts/diagnosis_v2.md` (applies to the next photo, no restart) |
| change the 5-minute close, number of tries, greetings | `conversation.*` in `config/settings.yaml` (restart) |
| keep or delete closed conversations | `records.keep_after_close` in `config/settings.yaml`: `auto` / `true` / `false` (restart) |
| change confidence bands, model, wait time, ports | `config/settings.yaml` (restart) |
| try another model | `openrouter.model` in `config/settings.yaml`, e.g. `google/gemini-3.5-flash-lite` (restart) |
| use Google AI Studio directly instead of OpenRouter | `core.provider: gemini` + `GEMINI_API_KEY` in `.env` (restart) |
| change what the bot says to customers (English and Hindi) | `app/replies.py` (restart) |
| change field descriptions or allowed fixed values | `config/fields.yaml` (restart) |
| update Lists / Universe | edit the workbooks in `config/reference/`, run `python scripts\import_reference.py`, restart |
| try without an API key | `core.provider: mock` in `config/settings.yaml` |

## Tests

```
python -m pytest -q
```
Runs without network or API key (uses the mock model and fake OpenRouter / Gemini servers).

## Folder layout

```
app/core/         diagnosis core: reference data, prompt + schema, model providers (OpenRouter, Gemini direct,
                  mock), validation, rules
app/whatsapp/     WhatsApp Cloud API: webhook, message formats, client
app/simulator/    fake Meta API + chat page (only in simulator mode)
app/debug.py      backend dashboard API (port 8001); page in app/dashboard_static/
PROJECT_LOG.md    what this is, current state, where data is stored, what was done and why (read first)
CLAUDE.md         standing instructions for Claude (keep docs current, ask first, never commit)
docs/             DESIGN.md (how the bot works), USER_JOURNEY.md (the customer journey and its rules)
app/conversation.py  the customer journey: language, photos + text, tries, 5-minute close, records
app/language.py   greetings and language words ("hi", "Hindi", ...)
app/replies.py    everything the customer reads, in English and Hindi
tests/            test_core.py (diagnosis), test_journey.py (the journey rules), test_e2e.py (through the simulator)
config/           settings, fields, prompts, reference workbooks
data/             logs (bot.db), photos, simulator data — created at runtime
scripts/          import_reference.py, check_gemini.py
```
