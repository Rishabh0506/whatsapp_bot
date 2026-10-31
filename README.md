# Footwear helpline bot

Send a photo of damaged footwear in a WhatsApp-style chat and get back the **10 diagnosis fields**, each with a
**confidence score**, plus the decision from the confidence rules. The backend speaks the real WhatsApp Cloud
API format, so moving from the simulator to WhatsApp is a settings change. Design: [docs/DESIGN.md](docs/DESIGN.md).

## First-time setup (Windows)

1. **Python 3.11+** must be installed.
2. Copy `.env.example` to `.env` and put your Google AI Studio key after `GEMINI_API_KEY=`.
3. Double-click **`run.bat`**. The first run creates `.venv`, installs the packages and imports the reference
   workbooks. Or in a Command Prompt in this folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   python scripts\import_reference.py
   python run.py
   ```
4. Open **http://127.0.0.1:8000** — attach a photo, press send.

Check that your key works and which models you can use:
```
python scripts\check_gemini.py
```
If the model in `config/settings.yaml` (`gemini.model`) isn't in that list, change it to one that is.

Diagnose photos straight from the command line (no chat):
```
python scripts\check_gemini.py path\to\photo.jpg [more photos of the same item] [--raw]
```

## Using the simulator

- **Left:** the user's phone. Attach one or more photos (the paperclip), optionally type a caption, send.
  Photos sent within 6 seconds of each other are treated as one item. Ticks turn blue when the bot reads them.
- **Right:** the debug panel: the 10 fields with value, confidence bar (marks at the two bands), status, the
  model's original answer where a rule changed it, the decision, warnings, and the raw model output.
- **User number / New user:** simulate different WhatsApp users; each has their own chat and history.

## Common changes

| To… | Edit |
|---|---|
| change the prompt | `config/prompts/diagnosis_v1.md` (applies to the next photo, no restart) |
| change confidence bands, model, wait time | `config/settings.yaml` (restart) |
| change field descriptions or allowed fixed values | `config/fields.yaml` (restart) |
| update Lists / Universe | edit the workbooks in `config/reference/`, run `python scripts\import_reference.py`, restart |
| try without an API key | `core.provider: mock` in `config/settings.yaml` |

## Tests

```
python -m pytest -q
```
Runs without network or API key (uses the mock model and a fake Gemini server).

## Folder layout

```
app/core/         diagnosis core: reference data, prompt + schema, Gemini/mock providers, validation, rules
app/whatsapp/     WhatsApp Cloud API: webhook, message formats, client
app/simulator/    fake Meta API + chat page (only in simulator mode)
app/conversation.py  per-user handling: duplicates, photo grouping, replies, 24h window
config/           settings, fields, prompts, reference workbooks
data/             logs (bot.db), photos, simulator data — created at runtime
scripts/          import_reference.py, check_gemini.py
```
