# Footwear helpline bot

**New here? Read [PROJECT_LOG.md](PROJECT_LOG.md) first**: what this is, where things stand, where data is
stored, and what has been done and why.

Send a photo of damaged footwear in a WhatsApp-style chat and get a plain-language reply. Behind the scenes the
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
4. Open **http://127.0.0.1:8000** (the chat, what the customer sees) — attach a photo, press send.
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
  are treated as one item. Ticks turn blue when the bot reads them, and the header shows "typing…" while the bot
  works (WhatsApp hides it after 25 seconds). WhatsApp formatting (*bold*, _italic_, ~strike~) renders as in the
  app. The bot answers in plain language (wording in `app/replies.py`).
- **Test customer (avatar, bottom left):** change the name or phone number, or start a new test customer. Each
  number is a separate customer with their own chat history.
- **Why a simulator:** the bot talks to this page only through a fake copy of Meta's Cloud API (same webhook
  payloads, signatures, media download, send/read/typing calls). Switching to real WhatsApp is
  `channel.mode: whatsapp` plus the `WHATSAPP_*` values in `.env`; the bot's code doesn't change and this page
  simply isn't used any more.
- **Backend dashboard (port 8001):** the latest diagnosis only (older ones stay in `data/bot.db`): the 10 fields with value,
  confidence bar (marks at the two bands), status, the model's original answer where a rule changed it, the
  decision, warnings, the raw model output and what the customer was told. It only listens on 127.0.0.1 and is
  never on the bot's port, so it stays private when the bot port goes public for real WhatsApp.

## Common changes

| To… | Edit |
|---|---|
| change the prompt | `config/prompts/diagnosis_v1.md` (applies to the next photo, no restart) |
| change confidence bands, model, wait time, ports | `config/settings.yaml` (restart) |
| try another model | `openrouter.model` in `config/settings.yaml`, e.g. `google/gemini-3.5-flash-lite` (restart) |
| use Google AI Studio directly instead of OpenRouter | `core.provider: gemini` + `GEMINI_API_KEY` in `.env` (restart) |
| change what the bot says to customers | `app/replies.py` (restart) |
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
app/conversation.py  per-user handling: duplicates, photo grouping, replies, 24h window
config/           settings, fields, prompts, reference workbooks
data/             logs (bot.db), photos, simulator data — created at runtime
scripts/          import_reference.py, check_gemini.py
```
