# Footwear helpline bot: project log

Read this file first. It says what the project is, where things stand, where every kind of data is kept,
and what has been done so far and why. Add a dated entry to the change log whenever something changes.

- How to install, run and use it: [README.md](README.md)
- How the code is built (architecture, model output, confidence rules): [docs/DESIGN.md](docs/DESIGN.md)
- Standing instructions for Claude (read automatically): [CLAUDE.md](CLAUDE.md)

---

## 1. What this is

A WhatsApp helpline that fixes footwear problems. A customer sends a photo of a damaged shoe, sandal or
slipper. The bot asks a vision model (Gemini, through OpenRouter) to fill in **10 diagnosis fields**, each with a **confidence
score**, applies confidence rules to decide what to do next, and replies to the customer in plain language.

**Phase 1 scope (now):** photos only, footwear only. Solutions/products, text, voice and video input, and
follow-up conversations come later. They are planned to fit into the same structure (see DESIGN.md section 7).

The 10 fields: Image Status, Footwear Type, Part, Issue Category, Damage Mode, Secondary Issue,
Receiving Substrate, Applied Substrate, Damage Extent, Glue Fix Possible. They are defined in
`config/fields.yaml`, and their allowed values come from the Shoe Fixing Lists / Universe workbooks.

## 2. Where we are now

*Last updated: 2 Nov 2026*

- The bot runs locally with `run.bat`, which starts two pages:
  - **http://127.0.0.1:8000/sim/**: the customer's WhatsApp, laid out like WhatsApp Web (the **simulator**).
  - **http://127.0.0.1:8001/**: the **backend dashboard**, showing the latest diagnosis with all 10 fields,
    scores, the decision, the raw model output, and what the customer was told.
- The customer sees only plain-language replies. Scores and field names appear only on the dashboard.
- The model is `google/gemini-3.5-flash`, called **through OpenRouter** (key `OPENROUTER_API_KEY` in `.env`),
  with prompt `diagnosis_v1`. Google AI Studio directly is still available as an option (`core.provider: gemini`).
  Confidence bands are 0.80 (accept) and 0.50
  (unknown). These are proposed values; the final ones come from the test plan.
- The bot already talks to the simulator exactly as it will talk to real WhatsApp (Meta's Cloud API).
  Going live later means changing a setting and adding keys, not rewriting the bot.
- Git: the work is on branch `rishabh/web-frontend`. The 2 Nov changes are **not committed yet**.
- Tests: `python -m pytest -q` (18 tests, no API key or internet needed).

## 3. Where things are stored, and why

Everything under `data/` is created when the bot runs. It is **not** in git (see `.gitignore`), so each
person on the team has their own local copy.

| What | Where | Why it is kept |
|---|---|---|
| Every message in and out, as the bot saw it | `data/bot.db` → table `messages` | Full record of each conversation, the same in simulator and real WhatsApp. Duplicate deliveries from WhatsApp are detected by message ID. |
| Every diagnosis: 10 fields, confidences, decision, raw model output, model + prompt version, time taken, errors | `data/bot.db` → table `diagnoses` | Feeds the dashboard (latest one only). The full history is kept for **model evaluation** and as future dataset material. |
| Photos the bot received | `data/media/<phone number>/<media id>.jpg` (+ `data/bot.db` → `media`) | The exact images the model saw, linked to each diagnosis, so results can be re-checked or re-run. |
| Per-customer state: name, last message time | `data/bot.db` → `sessions` | Needed for WhatsApp's 24-hour reply window and, later, for follow-up questions. |
| Sent / delivered / read updates | `data/bot.db` → `statuses` | Shows whether replies reached the customer (WhatsApp reports these back). |
| **Simulator only:** the chat shown on the 8000 page | `data/simulator.db` → `messages`, `media`; photos in `data/sim_media/` | Plays the role of "Meta's servers + the customer's phone". It goes away with real WhatsApp. Deleting it (with the bot stopped) clears the simulator chats; `bot.db` is not affected. |
| Settings: model, bands, ports, timing | `config/settings.yaml` | Change behaviour without touching code. |
| Field definitions | `config/fields.yaml` | One place that drives the prompt, the output format, validation, the rules and the dashboard. |
| Allowed values | `config/reference/*.xlsx` → `lists.json`, `universe.json` (via `scripts/import_reference.py`) | The workbooks are the source of truth; the JSON is what the bot reads. |
| Model instructions | `config/prompts/diagnosis_v1.md` | Re-read on every photo, so prompt edits apply without a restart. Version it by copying to `_v2`. |
| What the customer is told | `app/replies.py` | All customer wording in one file. |
| Secrets (OpenRouter key; Gemini key only if used directly; later WhatsApp keys) | `.env` (template: `.env.example`) | Never committed to git. |
| Cost and route of each model call | `data/bot.db` → `diagnoses.result` (`meta.usage`: tokens, `cost_usd`, `routed_to`) | Reported by OpenRouter; shown on the dashboard, and lets us compare models on cost later. |

## 4. Decisions and why

| Date | Decision | Why |
|---|---|---|
| Oct 2026 | Bot backend in **Python** (not n8n) | The same backend must work for real WhatsApp later without being redesigned. |
| Oct 2026 | **Gemini** via a Google AI Studio API key, behind a "provider" layer | The key was available; other models can be added in `app/core/providers/` to compare them. |
| Oct 2026 | Build a **local simulator** first, real WhatsApp last | Develop and test without a Meta business account, phone number or public server. |
| Oct 2026 | The simulator copies **Meta's Cloud API exactly** (signed webhooks, media IDs, two-step photo download, separate send calls, read receipts, statuses) | The bot can't tell the simulator from real WhatsApp, so switching needs no redesign. |
| Oct 2026 | Photos arriving within 6 s of each other = **one item** | WhatsApp sends each photo as a separate message; the spec says several photos of one item = one record. |
| Oct 2026 | Model output forced into a JSON schema built from `fields.yaml`, then **validated** | Values must come from the official lists; impossible combinations are flagged instead of trusted. |
| 2 Nov 2026 | Customers get **plain-language replies**, never scores | Scores are for building the backend. Customers need to know what's wrong and whether glue will fix it. |
| 2 Nov 2026 | Scores moved to a **separate dashboard on port 8001**, on 127.0.0.1 only | When port 8000 goes public for real WhatsApp, the internal scores must not be reachable from the internet. |
| 2 Nov 2026 | Dashboard shows **only the latest diagnosis** | Easier to read while working; history stays in `bot.db` for evaluation. |
| 2 Nov 2026 | Simulator redesigned to look like **WhatsApp Web** | It should look the way the customer will actually see it. |
| 2 Nov 2026 | Bot sends WhatsApp's real **typing indicator** instead of the page faking "typing…" | Behaves exactly like real WhatsApp: shown after the read receipt, gone when the reply arrives or after 25 s. |
| 2 Nov 2026 | The bot only states what it is **confident** about | A wrong diagnosis told to a customer is worse than asking for one more photo. |
| 2 Nov 2026 | Call Gemini **through OpenRouter** instead of Google AI Studio directly (default `google/gemini-3.5-flash`); the AI Studio connection stays as an option | Team decision to use an OpenRouter key from now on. One key reaches many models, so comparing models becomes a settings change, and each call's cost is reported. |
| 2 Nov 2026 | OpenRouter requests require routes that honour the JSON schema (`require_parameters`), with a one-time fallback to plain JSON | The answer must keep following the official lists; validation catches anything that slips through. |
| 2 Nov 2026 | Keep three docs (`PROJECT_LOG.md`, `docs/DESIGN.md`, `README.md`) current with every change, with the rule in **`CLAUDE.md`** | Anyone (or any new Claude session) can see where things stand and why, without being told. |

## 5. Change log (newest first)

### 2 Nov 2026: model calls through OpenRouter (branch `rishabh/web-frontend`, uncommitted)
- New provider `app/core/providers/openrouter.py` (OpenRouter Chat Completions: photos as data URLs, JSON
  schema output, retries, fallback to JSON mode, reports tokens/cost/route). Now the default
  (`core.provider: openrouter`, `openrouter.*` in `config/settings.yaml`, `OPENROUTER_API_KEY` in `.env`).
- Google AI Studio provider kept as an option (`core.provider: gemini`).
- `scripts/check_gemini.py` now checks the OpenRouter key (usage and limit), lists Gemini models that accept
  photos with their prices, and diagnoses photos from the command line.
- Dashboard shows each diagnosis's cost and which route served it.
- `run.bat` / `run.py` stops with a clear message if the model key is missing from `.env`.
- `.env.example`, tests (fake OpenRouter server, request/answer format, default provider) and all docs updated.

### 2 Nov 2026: customer-facing front end (branch `rishabh/web-frontend`, uncommitted)
- **Customer replies** (`app/replies.py`): replaced the test-mode message (10 fields + scores) with plain
  language. *Accept* → what's wrong + whether glue can fix it. *Follow-up* → asks for a close-up photo and only
  names the damage if confident. *Better photo* → says why (blurry / no footwear / several items).
  *No damage visible* → asks for a close-up of the problem. Errors → a short apology (the details go to the
  dashboard).
- **Backend dashboard on port 8001** (`app/debug.py`, `app/dashboard_static/`): moved from the right half of
  the chat page. Shows the latest diagnosis only, with who sent it and what the customer was told. The
  internal API was removed from port 8000.
- **`run.py`** starts both pages, and stops with a clear message if a port is already in use (an old copy of
  the bot still running).
- **Simulator redesigned like WhatsApp Web** (`app/simulator/static/`): chat list + conversation pane, photo
  preview with caption before sending, drag/paste photos, ticks, date chips, WhatsApp text formatting, reply
  buttons and list messages, a "test customer" panel to switch name/number.
- **Typing indicator** (`app/whatsapp/payloads.py`, `client.py`, `conversation.py`, simulator): the bot sends
  the Cloud API typing indicator when it starts diagnosing; the simulator shows it like WhatsApp.
- Pages are served with no-cache headers and versioned file names, so the browser always loads the latest
  version.
- Tests updated and added (customer wording, dashboard only on its own port, typing indicator).
- **Docs:** added this `PROJECT_LOG.md`; updated `docs/DESIGN.md` and `README.md` to match. Rule from now on:
  all three docs are updated with every change (section 7).
- **`CLAUDE.md`** added: standing instructions Claude reads automatically at the start of a session (read this
  log first, update all three docs after every change, ask before implementing when unclear, never commit,
  and the project's principles).

### 28–31 Oct 2026: first working version (commit `259a751`, "Initial commit")
- WhatsApp Cloud API webhook, client and message formats (`app/whatsapp/`).
- Built-in WhatsApp simulator (fake Meta API + chat page with a debug panel).
- Diagnosis core: prompt and schema from `fields.yaml`, Gemini (Google AI Studio) and mock providers, validation against the
  Lists/Universe, confidence rules and decision (`app/core/`).
- SQLite log of messages, photos and diagnoses (`app/storage.py`).
- Reference import from the Excel workbooks, Gemini check script, tests.

## 6. Open items / next steps

- **Slow replies:** a diagnosis takes about 40 s, and WhatsApp hides "typing…" after 25 s. Consider an
  instant "Got it, taking a look…" message when the photo arrives.
- **First real run through OpenRouter:** add `OPENROUTER_API_KEY` to `.env`, run `python scripts\check_gemini.py`,
  then send one photo (the OpenRouter connection was tested only against a fake server).
- **Final confidence bands** from the test plan (currently 0.80 / 0.50).
- **Follow-up questions** using reply buttons and list messages (the simulator already displays them).
- **Solutions / product step** after the diagnosis (`app/core/pipeline.py`, then `app/replies.py`).
- **Model evaluation script** over the labelled dataset, using the same code path as the bot.
- **Real WhatsApp:** host on a server with HTTPS, set `channel.mode: whatsapp`, fill the `WHATSAPP_*` values
  in `.env`, register the webhook URL with Meta. Keep port 8001 private.
- Interpretations still to confirm: see DESIGN.md section 6.

## 7. Keeping the docs current

The project has three docs, and **all three are updated whenever something changes**. The same rule is in
`CLAUDE.md`, which Claude reads automatically, so it applies without anyone pointing it out.

| File | Answers | Update it when… |
|---|---|---|
| `PROJECT_LOG.md` (this file) | What is this, where are we, what was done and why? | **Every change:** update section 2 if the current state changed, add a dated entry at the top of section 5, add a line to section 4 for any decision someone might later ask "why?" about, and adjust sections 3 and 6 if storage or next steps changed. |
| `docs/DESIGN.md` | How does the bot work inside? | The way the bot works changes: message flow, components, model output, rules, or where to change things. |
| `README.md` | How do I run and use it? | How to install, start, use or configure it changes: pages, addresses, settings, commands, folder layout. |

Before committing, check all three against the change. If a file truly needs nothing, that's fine, but check it.
