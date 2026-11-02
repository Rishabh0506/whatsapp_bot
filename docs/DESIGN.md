# Footwear helpline bot — design

**Phase 1 scope:** images only, footwear only. Each photo (or set of photos of one item) gets the
**10 diagnosis fields**, each with a **confidence score**, plus a decision from the confidence rules.
Solutions, text/voice/video input and follow-up conversations come later and plug into the same structure.

## 1. Principle: the channel is separate from the diagnosis

```
 Simulator chat page ─┐                                   ┌─ Gemini via OpenRouter (now)
 (later: real phone) ─┤                                   ├─ other models (for comparison)
                      ▼                                   │
        ┌──── "WhatsApp" ─────┐      ┌──────── Bot ───────┴──────────────────────────────┐
        │ simulator now,      │ ───► │ Webhook ─► Conversation manager ─► Diagnosis core │
        │ Meta Cloud API      │ ◄─── │ WhatsApp client ◄─ Reply composer ◄──────┘        │
        │ later (a setting)   │      │                    Storage (SQLite log)            │
        └─────────────────────┘      └────────────────────────────────────────────────────┘
```

The bot only ever speaks the **WhatsApp Cloud API**:
- incoming messages arrive as signed webhook POSTs (`/webhook`, checked with `X-Hub-Signature-256`);
- photos arrive as **media IDs** and are fetched in two steps (`GET /{media-id}` → short-lived URL → download);
- replies are sent separately through `POST /{phone-number-id}/messages`, not as the webhook's response;
- read receipts, sent/delivered statuses, duplicate deliveries and the 24-hour service window are handled.

- the typing indicator ("typing…") is sent with a read receipt while the model works, as the Cloud API allows.

In simulator mode the server also hosts a **fake Meta API** (`/sim/graph/...`) that behaves the same way,
plus a chat page laid out like WhatsApp Web that plays the customer's phone.

The bot's internal view (10 fields, confidences, decision, raw output) is a **separate dashboard app on its own
port** (`dashboard.port`, default 8001, bound to 127.0.0.1; `app/debug.py`). It shares the database but is never
served on the bot's port, so it stays private when the bot port is made public for Meta's webhook.
Switching to real WhatsApp = `channel.mode: whatsapp` + the `WHATSAPP_*` values in `.env` + registering the
webhook URL with Meta. No bot code changes.

## 2. Request flow (one photo)

1. User sends a photo in the simulator → simulator re-compresses it like WhatsApp, stores it under a media ID,
   POSTs a signed Cloud API webhook to `/webhook`.
2. Webhook checks the signature, answers `200` at once, hands the message to the conversation manager in the
   background.
3. Conversation manager: skips duplicates (message ID), records the session, sends a read receipt, downloads
   the photo by media ID, and waits `channel.batch_wait_seconds` for more photos of the same item
   (WhatsApp sends each photo as a separate message; spec: several photos of one item = one record).
4. Diagnosis core (`app/core/pipeline.py`): prepare images → model → validation → rules → result.
   Before calling the model the bot sends a typing indicator, so the customer sees "typing…".
5. Reply composer (`app/replies.py`) turns the result into a plain-language WhatsApp text message for the
   customer (what's wrong and whether glue can fix it, or a request for a better/closer photo). The bot only
   names things it is confident about. Scores never go to the customer; they are on the dashboard.
6. WhatsApp client sends it; everything is logged in `data/bot.db`.

## 3. Components and where to change things

| Component | File(s) | Change it to… |
|---|---|---|
| Field definitions | `config/fields.yaml` | add/rename a field, change allowed values or descriptions, mark product-deciding |
| Allowed values | `config/reference/*.xlsx` → `scripts/import_reference.py` → `lists.json`, `universe.json` | update the Lists or Universe |
| Model instructions | `config/prompts/diagnosis_v1.md` (re-read on every request) | improve the prompt; copy to `diagnosis_v2.md` and set `core.prompt` to version it |
| Bands, model, timing | `config/settings.yaml` | set final bands from the test plan, switch model |
| Model provider | `app/core/providers/` | `openrouter.py` (default: Gemini through OpenRouter), `gemini.py` (Google AI Studio directly), `mock.py`. Another OpenRouter model = change `openrouter.model`; a different API = a new class registered in `__init__.py` |
| Validation | `app/core/validation.py` | add consistency checks |
| Confidence rules | `app/core/rules.py` | change decision logic |
| Customer wording | `app/replies.py` | change what the customer reads (one place for all replies) |
| Backend dashboard | `app/debug.py`, `app/dashboard_static/` | change what the team sees about each diagnosis (port 8001) |
| Simulator chat page | `app/simulator/static/` | change the WhatsApp-Web-like test page (not part of the bot) |
| Conversation | `app/conversation.py` | follow-up questions, reviewer queue, text/voice handling |
| Channel | `app/whatsapp/` | (stable — follows Meta's API) |

## 4. The model output contract

The model is called through **OpenRouter** (`app/core/providers/openrouter.py`, key `OPENROUTER_API_KEY`):
`POST /chat/completions` with the instructions as the system message, the photos as base64 data URLs, and
`response_format` = the JSON schema below (`strict`). `provider.require_parameters: true` makes OpenRouter use only
routes that honour that schema; if none accepts it, the bot retries once in plain JSON mode (validation still
checks everything). OpenRouter reports tokens, cost and which route served the call; these are stored with the
diagnosis and shown on the dashboard. Setting `core.provider: gemini` calls Google AI Studio directly instead.

The model is constrained by a JSON schema built from `fields.yaml` (every value must come from its list):

```json
{
  "visible_evidence": "…",
  "image_status":      {"value": "Usable", "confidence": 0.95},
  "footwear_type":     {"value": "Formal Shoes", "confidence": 0.90},
  "part": …, "issue_category": …, "damage_mode": …,
  "secondary_issue":   {"issue_category": "None", "damage_mode": "None", "confidence": 0.80},
  "receiving_substrate": …, "applied_substrate": …, "damage_extent": …, "glue_fix_possible": …,
  "observation_note": "…"
}
```

The bot never trusts it blindly. Validation turns out-of-list values into Unknown and records warnings for:
damage mode not belonging to the issue category, Part + Issue + Damage Mode not in the Universe, the
combination not existing for that footwear type, an Unknown material with no observation note, bad confidences.

## 5. Confidence rules (spec section 4)

| Confidence | Status | Effect |
|---|---|---|
| ≥ `accept_threshold` (0.80) | accepted | value used |
| between the two | check | product-deciding field → follow-up |
| < `unknown_below` (0.50) | unknown | value becomes **Unknown** (model's answer kept as `model_value`) |

Decision, in order:
1. Image Status = Blurry / Not Footwear / More Than One Item → **better photo**
2. Image Status = Damage Not Visible → **ask what the problem is** (spec section 5)
3. Any product-deciding field not accepted → **follow-up** (lists the fields)
4. Otherwise → **accept**

Product-deciding: Part, Issue Category, Damage Mode, both substrates, Damage Extent, Glue Fix Possible.
Footwear Type, Image Status and Secondary Issue do not block.

## 6. Interpretations to confirm

- **Damage Not Visible** → "ask what the problem is" rather than "better photo" (the table says not-usable →
  better photo; section 5 says no visible damage → ask the problem). Easy to change in `rules.py`.
- **A matching pair** counts as one item, not "More Than One Item" (stated in the prompt).
- **Damage Extent and Glue Fix definitions** in `fields.yaml` are first drafts (the spec gives only the values).
- **Reviewer queue** needs one follow-up to have happened first, so it arrives with follow-up conversations.
- Bands 0.80 / 0.50 are the proposed values; final ones come from the test plan (5 Nov 2026).

## 7. Next extensions (planned to fit without rework)

- **Follow-up questions:** session state already exists per user (`sessions` table); add a state machine in
  the conversation manager and use reply buttons / list messages (`app/whatsapp/payloads.py` enforces limits).
- **Reviewer queue:** a new decision + a reviewer page reading `diagnoses`.
- **Text / voice / video:** new message types in the conversation manager; the core gets the text as context.
- **Solutions:** a new step after the rules in `pipeline.py`, reading the 10 fields.
- **Model evaluation:** a script that runs the dataset through `DiagnosisService` and compares with
  `metadata.csv` (same code path as production).
- **Real WhatsApp:** host on a server with HTTPS, set `channel.mode: whatsapp`, fill `.env`, register webhook.
