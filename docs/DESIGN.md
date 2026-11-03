# Footwear helpline bot — design

**Phase 1 scope:** footwear only; photos plus the customer's typed text, in English or Hindi. Each case
(the photos and text of one conversation) gets the **10 diagnosis fields**, each with a **confidence score**,
plus a decision from the confidence rules. The conversation around it (language, tries, 5-minute close) follows
[USER_JOURNEY.md](USER_JOURNEY.md). Products / step-by-step guidance, cobbler rules, voice and video come later
and plug into the same structure.

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

## 2. Message flow (the customer journey)

The full journey, with every rule, is in [USER_JOURNEY.md](USER_JOURNEY.md). In the code:

1. The customer sends something (in the simulator: photos, a voice note / video, or text) → the simulator stores
   any file under a media ID and POSTs a signed Cloud API webhook to `/webhook`.
2. Webhook checks the signature, answers `200` at once, hands the message to the conversation manager
   (`app/conversation.py`) in the background.
3. Conversation manager: skips duplicates (message ID), records the session, sends a read receipt, and loads the
   customer's **open conversation** (`sessions.state` in `data/bot.db`: case id, language, photos, texts, tries,
   answered, time of the bot's last real reply). Each customer's messages are handled one at a time.
   - **Only a greeting** (`conversation.greetings`, `app/language.py`) → the old conversation ends, a new one
     starts, and the bot asks for the language.
   - **No language yet** → the language question (text + two reply buttons, English / हिंदी). Photos and text sent
     before choosing are kept. A tap on a button, or a message that is just "English" / "Hindi" / "हिंदी", sets the
     language, at any point in the conversation. A message that is just "language" / "भाषा" brings the two buttons
     back, with a short message in the language of the word typed (`CHANGE_LANGUAGE_WORDS` in `app/language.py`).
   - **Photos** are downloaded by media ID and grouped for `channel.batch_wait_seconds` (WhatsApp sends each
     photo separately; several photos of one item = one record). A caption counts as the customer's text.
   - **Text** before any usable photo → "please send a photo" (kept for the diagnosis). Text after a request for
     a closer photo → a new try on the photos already there, plus the text.
   - **Voice note / video** → "can't open these yet, please send a photo" (counts as a try).
   - **After the answer** → text gets "my answer is above, send a photo if there's another problem"; a new photo
     starts a new case in the same language.
4. A **try**: the bot sends "Got it, taking a look…" (does not start the timer) and a typing indicator, then the
   diagnosis core (`app/core/pipeline.py`) gets the usable photos (up to `core.max_images_per_item`, newest)
   and all the customer's text: prepare images → model → validation → rules → result. Photos judged Blurry,
   Not Footwear or More Than One Item are left out of later tries. If a photo or text arrives while the model
   is working, the bot looks again with it before replying (same try, one reply).
5. Reply composer (`app/replies.py`) turns the result into a plain-language message in the chosen language
   (English, or Hindi in Hindi letters): an answer (accept → what's wrong + glue + product placeholder; cobbler
   → suggest a cobbler) or a request for a better / closer photo. After the last try
   (`conversation.max_tries`) without an answer: "please try again with a clear picture", and the conversation
   closes. Scores never go to the customer; they are on the dashboard.
6. WhatsApp client sends it; everything is logged in `data/bot.db` with the case id.
7. **Closing:** every `conversation.check_every_seconds` the bot closes conversations where the customer has
   sent nothing for `conversation.close_after_seconds` since the bot's last real reply (an answer or a question).
   It sends the closing message and forgets the conversation and the language. WhatsApp doesn't report silence,
   so this regular check is the bot's own.
8. **Records:** when a conversation closes, its photos, messages and diagnoses are kept or deleted according
   to `records.keep_after_close` (`auto` = kept in simulator mode, deleted in whatsapp mode). The cost numbers of
   each model call (`usage_log`, no customer data) are always kept.

## 3. Components and where to change things

| Component | File(s) | Change it to… |
|---|---|---|
| Field definitions | `config/fields.yaml` | add/rename a field, change allowed values or descriptions, mark product-deciding |
| Allowed values | `config/reference/*.xlsx` → `scripts/import_reference.py` → `lists.json`, `universe.json` | update the Lists or Universe |
| Model instructions | `config/prompts/diagnosis_v2.md` (re-read on every request; v1 = photos only) | improve the prompt; copy to `diagnosis_v3.md` and set `core.prompt` to version it |
| Bands, model, timing | `config/settings.yaml` | set final bands from the test plan, switch model |
| Model provider | `app/core/providers/` | `openrouter.py` (default: Gemini through OpenRouter), `gemini.py` (Google AI Studio directly), `mock.py`. Another OpenRouter model = change `openrouter.model`; a different API = a new class registered in `__init__.py` |
| Validation | `app/core/validation.py` | add consistency checks |
| Confidence rules | `app/core/rules.py` | change decision logic |
| Customer wording | `app/replies.py` | change what the customer reads, in English and Hindi (one place for all replies) |
| Greetings, language words | `config/settings.yaml` (`conversation.greetings`), `app/language.py` | which messages start afresh / choose a language |
| Journey timing and tries | `config/settings.yaml` (`conversation.*`) | 5-minute close, how often it's checked, number of tries |
| Keeping records | `config/settings.yaml` (`records.keep_after_close`), `app/storage.py` | keep or delete a closed conversation's data |
| Backend dashboard | `app/debug.py`, `app/dashboard_static/` | change what the team sees about each diagnosis (port 8001) |
| Simulator chat page | `app/simulator/static/` | change the WhatsApp-Web-like test page (not part of the bot) |
| Conversation (the journey) | `app/conversation.py` | the customer journey: language, tries, timer, what happens to each kind of message |
| Channel | `app/whatsapp/` | (stable — follows Meta's API) |

## 4. The model output contract

The model is called through **OpenRouter** (`app/core/providers/openrouter.py`, key `OPENROUTER_API_KEY`):
`POST /chat/completions` with the instructions as the system message, the photos as base64 data URLs followed by
one line of text (plus, when the customer wrote anything, their words between `<<<` and `>>>`; prompt
`diagnosis_v2` says how to use them and never to follow instructions in them), and `response_format` = the JSON schema below (`strict`). `provider.require_parameters: true` makes OpenRouter use only
routes that honour that schema; if none accepts it, the bot retries once in plain JSON mode (validation still
checks everything). OpenRouter reports tokens, cost and which route served the call; these are stored with the
diagnosis and shown on the dashboard, and kept in `usage_log` even when the diagnosis itself is deleted.
Setting `core.provider: gemini` calls Google AI Studio directly instead (same text, same schema).

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
3. Clear cobbler case → **cobbler**: no more questions, even if smaller details (e.g. material) are unsure.
   **Placeholder** until the team's cobbler / "too extensive" rules arrive: Glue Fix Possible accepted as
   "No – Weight-Bearing Part", "No – Material Destroyed" or "No – Surface Glue Cannot Hold"
   (`is_cobbler_case()` in `rules.py`). "No – Not a Glue Problem" is cleaning / care, not a cobbler case.
4. Any product-deciding field not accepted → **follow-up** (lists the fields)
5. Otherwise → **accept** (the reply ends with a product / steps placeholder until those rules arrive)

The conversation manager turns better photo / ask the problem / follow-up into "send another photo" while tries
are left, and into "please try again with a clear picture" + close after the last one.

Product-deciding: Part, Issue Category, Damage Mode, both substrates, Damage Extent, Glue Fix Possible.
Footwear Type, Image Status and Secondary Issue do not block.

## 6. Interpretations to confirm

- **Damage Not Visible** → "ask what the problem is" rather than "better photo" (the table says not-usable →
  better photo; section 5 says no visible damage → ask the problem). Easy to change in `rules.py`.
- **A matching pair** counts as one item, not "More Than One Item" (stated in the prompt).
- **Damage Extent and Glue Fix definitions** in `fields.yaml` are first drafts (the spec gives only the values).
- **Reviewer queue:** skipped for now (3 Nov 2026); a 3-try limit replaces it. See `USER_JOURNEY.md`.
- **Smell / noise from text:** the model may use the customer's words for problems a photo can't show, but
  Image Status is about the photos only, so a clean-looking photo still gives "ask what the problem is".
- Bands 0.80 / 0.50 are the proposed values; final ones come from the test plan (5 Nov 2026).

## 7. Next extensions (planned to fit without rework)

The customer journey (language, conversation memory, 5-minute close, tries, text + photo) is built
(3 Nov 2026). Next:

- **Cobbler rules:** replace `is_cobbler_case()` in `app/core/rules.py` with the team's rules.
- **Solutions:** a step after the rules in `pipeline.py`, reading the 10 fields; the wording replaces
  `SOLUTION_PLACEHOLDER` in `replies.py` (both languages; pictures can be sent as WhatsApp image messages).
- **Answering free questions after the answer:** in `_on_message()` (now `replies.after_answer`).
- **Reviewer queue:** a new decision + a reviewer page reading `diagnoses`.
- **Voice / video:** new message types in the conversation manager (now a fixed reply that counts as a try).
- **Model evaluation:** a script that runs the dataset through `DiagnosisService` and compares with
  `metadata.csv` (same code path as production).
- **Real WhatsApp:** host on a server with HTTPS, set `channel.mode: whatsapp`, fill `.env`, register webhook.
