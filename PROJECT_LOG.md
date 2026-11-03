# Footwear helpline bot: project log

Read this file first. It says what the project is, where things stand, where every kind of data is kept,
and what has been done so far and why. Add a dated entry to the change log whenever something changes.

- How to install, run and use it: [README.md](README.md)
- How the code is built (architecture, model output, confidence rules): [docs/DESIGN.md](docs/DESIGN.md)
- The customer journey and its rules (agreed and built 3 Nov 2026): [docs/USER_JOURNEY.md](docs/USER_JOURNEY.md)
- Standing instructions for Claude (read automatically): [CLAUDE.md](CLAUDE.md)

---

## 1. What this is

A WhatsApp helpline that fixes footwear problems. A customer sends a photo of a damaged shoe, sandal or
slipper. The bot asks a vision model (Gemini, through OpenRouter) to fill in **10 diagnosis fields**, each with a **confidence
score**, applies confidence rules to decide what to do next, and replies to the customer in plain language.

**Phase 1 scope (now):** footwear only; photos plus the customer's typed text, in English or Hindi, following
the agreed customer journey (language first, up to 3 tries, closes after 5 quiet minutes). Solutions/products,
cobbler rules, voice and video input and a reviewer come later. They are planned to fit into the same structure (see DESIGN.md section 7).

The 10 fields: Image Status, Footwear Type, Part, Issue Category, Damage Mode, Secondary Issue,
Receiving Substrate, Applied Substrate, Damage Extent, Glue Fix Possible. They are defined in
`config/fields.yaml`, and their allowed values come from the Shoe Fixing Lists / Universe workbooks.

## 2. Where we are now

*Last updated: 3 Nov 2026*

- The bot runs locally with `run.bat`, which starts two pages:
  - **http://127.0.0.1:8000/sim/**: the customer's WhatsApp, laid out like WhatsApp Web (the **simulator**).
  - **http://127.0.0.1:8001/**: the **backend dashboard**, showing the latest diagnosis with all 10 fields,
    scores, the decision, the raw model output, what the customer wrote and was told, and its conversation
    (try number, language, open / closed).
- **The customer journey is built** (`docs/USER_JOURNEY.md`): language question with English / हिंदी buttons
  (photos sent before are kept), replies in English or Hindi (Hindi letters), Hinglish understood, photos +
  text used together, "Got it, taking a look…", up to 3 tries (photos, text-only retries, voice notes / videos),
  "hi" starts afresh, closing message after 5 quiet minutes. Cobbler step and product / steps are placeholders
  until the team's rules arrive. Hindi wording still needs a check by a Hindi speaker.
- The customer sees only plain-language replies. Scores and field names appear only on the dashboard.
- The model is `google/gemini-3.5-flash`, called **through OpenRouter** (key `OPENROUTER_API_KEY` in `.env`),
  with prompt `diagnosis_v2` (v1 + the customer's text). Google AI Studio directly is still available as an option (`core.provider: gemini`).
  Confidence bands are 0.80 (accept) and 0.50
  (unknown). These are proposed values; the final ones come from the test plan.
- The bot already talks to the simulator exactly as it will talk to real WhatsApp (Meta's Cloud API).
  Going live later means changing a setting and adding keys, not rewriting the bot.
- Records: closed conversations are **kept while testing** (simulator) and **deleted for real customers**
  (`records.keep_after_close: auto`); model cost numbers are always kept.
- Git: the journey work is on branch `rishabh/user-journey`, **not committed yet** (the 2 Nov changes are in the
  same working copy, also uncommitted).
- Tests: `python -m pytest -q` (45 tests, no API key or internet needed).

## 3. Where things are stored, and why

Everything under `data/` is created when the bot runs. It is **not** in git (see `.gitignore`), so each
person on the team has their own local copy.

| What | Where | Why it is kept |
|---|---|---|
| **What happens when a conversation closes** | setting `records.keep_after_close` | `auto` (default): kept in simulator mode (testing), **deleted** in whatsapp mode (real customers): photos (files too), messages' content, diagnoses, the case and the customer's name. Only bare message ids stay, to recognise late duplicate deliveries. Team decision, 3 Nov 2026. |
| Each conversation = one case: language, start / end, why it ended (timeout, tries, greeting, solved), outcome (solved, cobbler, tries used up), tries | `data/bot.db` → table `cases`; `case_id` on messages, media and diagnoses | See how many tries a case took and how it ended, for checking the model. |
| Every message in and out, as the bot saw it | `data/bot.db` → table `messages` | Full record of each conversation, the same in simulator and real WhatsApp. Duplicate deliveries from WhatsApp are detected by message ID. |
| Every diagnosis: 10 fields, confidences, decision, raw model output, model + prompt version, time taken, errors, try number, language, what the customer wrote, what they were told | `data/bot.db` → table `diagnoses` | Feeds the dashboard (latest one only). While testing, kept for **model evaluation** and as dataset material. |
| Photos the bot received | `data/media/<phone number>/<media id>.jpg` (+ `data/bot.db` → `media`) | The exact images the model saw, linked to each diagnosis, so results can be re-checked or re-run. |
| Per-customer state: name, last message time, **the open conversation** (case, language, photos, text, tries, time of the bot's last real reply) | `data/bot.db` → `sessions` (`state` column) | The 24-hour reply window, and the journey's memory: kept in the database so a restart doesn't lose open conversations. Cleared when the conversation closes. |
| Sent / delivered / read updates | `data/bot.db` → `statuses` | Shows whether replies reached the customer (WhatsApp reports these back). |
| **Simulator only:** the chat shown on the 8000 page | `data/simulator.db` → `messages`, `media`; photos in `data/sim_media/` | Plays the role of "Meta's servers + the customer's phone". It goes away with real WhatsApp. Deleting it (with the bot stopped) clears the simulator chats; `bot.db` is not affected. |
| Settings: model, bands, ports, timing | `config/settings.yaml` | Change behaviour without touching code. |
| Field definitions | `config/fields.yaml` | One place that drives the prompt, the output format, validation, the rules and the dashboard. |
| Allowed values | `config/reference/*.xlsx` → `lists.json`, `universe.json` (via `scripts/import_reference.py`) | The workbooks are the source of truth; the JSON is what the bot reads. |
| Model instructions | `config/prompts/diagnosis_v2.md` (v1 kept: photos only) | Re-read on every photo, so prompt edits apply without a restart. Version it by copying to `_v3`. |
| What the customer is told | `app/replies.py` | All customer wording in one file, English and Hindi. |
| Journey settings: 5-minute close, tries, greetings | `config/settings.yaml` → `conversation.*` | Change the journey's numbers without touching code. |
| Secrets (OpenRouter key; Gemini key only if used directly; later WhatsApp keys) | `.env` (template: `.env.example`) | Never committed to git. |
| Cost and route of each model call | `data/bot.db` → `usage_log` (always kept, no customer data) and `diagnoses.result` (`meta.usage`) | Reported by OpenRouter; shown on the dashboard, and lets us compare models on cost even when customer records are deleted. |

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
| 3 Nov 2026 | Customer journey written up in `docs/USER_JOURNEY.md` before building | Plan the whole conversation first, so the build follows one agreed flow. |
| 3 Nov 2026 | Two languages: **English and Hindi** (Hindi in Hindi letters). Hinglish typed by customers is understood and answered in the chosen language | Team decision; Hinglish is how many customers type, but replies stay in one clear language. |
| 3 Nov 2026 | Language asked first, with two buttons; a photo sent before choosing is **kept** and diagnosed after | Customers often send a photo straight away; they should not have to send it again. |
| 3 Nov 2026 | Bot **reads the customer's text together with the photos** | A description helps the diagnosis. Text alone still gets a request for a photo. |
| 3 Nov 2026 | Bot **remembers the open conversation**; a closer photo is added to the same case | So follow-up photos improve the same diagnosis instead of starting over. |
| 3 Nov 2026 | Conversation **closes after 5 min** without a customer message, counted from the bot's real reply ("please wait" messages don't count); a closing message is sent and the conversation **and language** are forgotten | Team decision; keeps each conversation short and separate. |
| 3 Nov 2026 | A message that is **only a greeting** (hi, hello, namaste…) starts a fresh conversation | The customer clearly wants to start again. |
| 3 Nov 2026 | **3 tries** (every diagnosed photo counts, including blurry / not footwear), then "please try again with a clear picture" and the conversation closes | Replaces the reviewer for now; stops endless photo requests. |
| 3 Nov 2026 | **Reviewer skipped** for now | Not needed for this phase; the 3-try limit covers unsure cases. |
| 3 Nov 2026 | Not footwear → ask for a footwear photo, never "not valid" | Friendlier, and gets the customer back on track. |
| 3 Nov 2026 | Clear cobbler case → suggest a cobbler with **no extra questions**; "too extensive" rules come with the solution step | A cobbler referral doesn't need every detail to be certain. |
| 3 Nov 2026 | A case counts as **solved once the repair steps are sent** (no "Did this help?" yet) | Simplest for now; feedback can be added later. |
| 3 Nov 2026 | After the repair steps or a cobbler suggestion the conversation **stays open** (normal 5-minute close) | The customer can still ask about the same case ("which glue did you say?"). |
| 3 Nov 2026 | Saving records becomes an **on/off setting**: **on while testing**, **off for real customers** (everything about a conversation deleted when it closes; only cost numbers kept) | The team decided not to keep customer records. A setting means it can be switched back on later without rebuilding. Model checking uses the separate labelled dataset. |
| 3 Nov 2026 | When saving is on, records are **one case per conversation** | Easy to see how many tries a case took and whether the answer was right. |
| 3 Nov 2026 | Bot does **not answer free questions** after the answer yet; points back to the steps | Free question-and-answer is a new ability beyond Phase 1; may come with the solution rules. |
| 3 Nov 2026 | Typing English / Hindi / हिंदी **at any point** switches language (mentioned in the language question) | Customers can change their mind without starting over. |
| 3 Nov 2026 | Text-only reply to a closer-photo request → **re-diagnose with existing photos + the text** (counts as a try), ask for a photo only if still needed | The description may be enough; saves the customer a photo. Counting it stops endless retries. |
| 3 Nov 2026 | Voice note or video → "can't open these yet, please send a photo", and it **counts as a try** | Team decision; keeps the 3-try limit firm. |
| 3 Nov 2026 | Language switches only when the message is **just the language name** | A sentence that mentions "Hindi" should not change the language. |
| 3 Nov 2026 | Typing **"language" / "भाषा"** shows the language buttons, with the message in the language of the word typed ("bhasha" counts as Hindi) | User request, from a reference bot; an easy way to change language without knowing the language names to type. |
| 3 Nov 2026 | Journey built in `app/conversation.py`, open conversation saved in `sessions.state` (database), not only in memory | A restart of the bot doesn't lose open conversations; the same code works for real WhatsApp. |
| 3 Nov 2026 | `records.keep_after_close: auto` = keep in simulator mode, delete in whatsapp mode | Matches the team decision (keep while testing, delete for real customers) without anyone having to remember to flip it. |
| 3 Nov 2026 | Cobbler step uses a **placeholder rule** (confident Glue Fix "No" for weight-bearing / material destroyed / surface) | The real rules come later; these are the cases the bot already sent to a cobbler. One function to replace (`is_cobbler_case()`). |
| 3 Nov 2026 | Confident answers end with a visible **product placeholder** line | So nobody mistakes the reply for finished before the product / steps rules arrive. |
| 3 Nov 2026 | Photos judged blurry / not footwear / more than one item are **left out of later tries** | They would confuse the next look at the same case. |
| 3 Nov 2026 | A photo after the answer starts a **new case in the same language**; a model failure doesn't use up a try | "Send a photo if there's another problem" means a new problem; our failures shouldn't count against the customer. |
| 3 Nov 2026 | A photo or text sent while the bot is still checking → the bot **looks again before replying** (same try) | The customer probably sent it to help; one reply instead of two. |
| 3 Nov 2026 | New prompt version **`diagnosis_v2`** for the customer's text (v1 kept) | Results stay comparable by prompt version; the text is fenced and the model is told never to follow instructions in it. |
| 3 Nov 2026 | Hindi replies written by Claude, to be **checked by a Hindi speaker** | Agreed in the plan; Hindi footwear names are written so the sentence grammar works for each type. |

## 5. Change log (newest first)

### 3 Nov 2026: "language" / "भाषा" brings up the language buttons
- Typing just "language" (also "languages", "change language") shows "🌐 Change language" with the English / हिंदी
  buttons; just "भाषा" (also "भाषा बदलें", "bhasha") shows "🌐 भाषा बदलें". Works any time, including before a
  language is chosen; nothing changes until a button is tapped; not a try.
- `app/language.py` (`CHANGE_LANGUAGE_WORDS`, `change_language_request()`), `app/replies.py`
  (`change_language()`), `app/conversation.py` (`_on_message()`). 2 new journey tests + a word test; 45 pass.
- Docs: USER_JOURNEY.md (rules and messages tables), DESIGN.md (message flow), README.md (journey in short).

### 3 Nov 2026: shorter photo request after choosing a language
- `app/replies.py` → `ask_photo()`: now only "Please send a photo of the footwear that needs fixing." (Hindi:
  "कृपया जिस जूते या चप्पल को ठीक करना है, उसकी फ़ोटो भेजें।"). The line "You can also tell me what the problem is in a
  message" was removed at the user's request. Typed text is still read and used. `docs/USER_JOURNEY.md` updated.

### 3 Nov 2026: customer journey built (branch `rishabh/user-journey`, uncommitted)
- **Journey** (`app/conversation.py`, rewritten): open conversation per customer saved in `sessions.state`;
  language question with English / हिंदी reply buttons, keeping photos / text sent before; typing a language name
  switches language any time; "hi" (and similar, `conversation.greetings`) starts afresh; "Got it, taking a
  look…" + typing indicator; photos and text of the case go to the model together; up to `conversation.max_tries`
  tries (photos, text-only retries, voice notes / videos), then "please try again with a clear picture" and close;
  closing message after `conversation.close_after_seconds` without a reply (checked every 15 s, started with the
  server); a photo / text while checking → looks again (same try); a photo after the answer → new case.
- **Language** (`app/language.py`, new): greetings and language words.
- **Replies** (`app/replies.py`): every message in English and Hindi; new messages (language question, language
  changed, ask for photo, please wait, voice / video, tries used up, after the answer, closing); cobbler answer;
  product placeholder line.
- **Model gets the customer's text:** `DiagnosisService.diagnose(images, text)`, all providers send it after the
  photos (`user_text()` in `providers/base.py`); new prompt `config/prompts/diagnosis_v2.md` (now the default).
- **Rules** (`app/core/rules.py`): new decision **cobbler** (placeholder rule, `is_cobbler_case()`), checked
  before follow-up.
- **Storage** (`app/storage.py`): `cases` and `usage_log` tables; `case_id` on messages, media, diagnoses; try
  number, language, customer text and the reply stored with each diagnosis; deleting a closed case; older
  databases get the new columns automatically.
- **Settings:** `conversation.*` (close after, check every, max tries, greetings) and `records.keep_after_close`.
- **Simulator:** **+** also sends audio / video files as voice notes / videos (`app/simulator/routes.py`,
  `static/app.js` v3, `styles.css` v3).
- **Dashboard:** shows try number, language, open / closed, what the customer wrote; cobbler decision; says
  whether records are kept (`dashboard.js` v5, `styles.css` v4).
- **Tests:** new `tests/test_journey.py` (17 tests: every journey rule, records kept / deleted); `test_core.py`
  (cobbler rule, Hindi replies, greetings / language words, prompt v2, customer text in the request);
  `test_e2e.py` (language buttons through the simulator, voice note). 43 tests pass.
- **Docs:** USER_JOURNEY.md (built, small choices made while building), DESIGN.md (message flow, rules,
  components), README.md (using it, settings, layout), CLAUDE.md (scope, wording in two languages, records rule).

### 3 Nov 2026: customer journey planned (no code changes)
- Added `docs/USER_JOURNEY.md`: the agreed customer journey from the team's flow diagram (flowchart, step by
  step, conversation rules, list of customer messages, built vs to build, records recommendation, what is
  waiting on rules). Decisions recorded in section 4.
- Later the same day: confirmed the conversation stays open after the answer, records = one case per
  conversation, and saving records is an on/off setting (on while testing, off for real customers, cost numbers
  always kept). This will change the "full history stays in `bot.db`" rule once built.
- Edge cases added: no free questions after the answer, language switch by typing, extra photo while checking,
  text-only replies, off-topic text.
- `docs/DESIGN.md` and `README.md` point to it. Nothing in how the bot works today has changed.

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

- **First real run through OpenRouter:** add `OPENROUTER_API_KEY` to `.env`, run `python scripts\check_gemini.py`,
  then send one photo (the OpenRouter connection was tested only against a fake server).
- **Final confidence bands** from the test plan (currently 0.80 / 0.50).
- **Try the journey with the real model** (OpenRouter key) in the simulator, in both languages, including
  Hinglish text and a text-only retry.
- **Hindi wording check** by a Hindi speaker (`app/replies.py`, the `_HI` tables and every `hi` text).
- **Cobbler / "too extensive" rules** from the team → replace `is_cobbler_case()` in `app/core/rules.py`.
- **Solutions / product step** after the diagnosis (`app/core/pipeline.py`, then `SOLUTION_PLACEHOLDER` in
  `app/replies.py`, both languages).
- **Records for real customers:** if saving is ever switched on (`records.keep_after_close: true`), decide first
  how long records are kept and how to delete them on request (personal data, DPDP Act).
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
