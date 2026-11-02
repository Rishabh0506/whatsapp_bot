# Instructions for Claude: footwear helpline bot

Read this at the start of every session, before working on anything in this folder.

## First, always
1. Read `PROJECT_LOG.md`. It has what the project is, the current state, where data is stored, the decisions
   made so far and why, and the next steps. Don't redo or contradict a decision listed there without asking.
2. For code changes, also read the relevant part of `docs/DESIGN.md` (how the bot works, which file to change).

## After every change (do this without being asked)
Update **all three docs** in the same piece of work:
- `PROJECT_LOG.md`, every time: section 2 (current state) if it changed, a dated entry at the top of section 5
  (change log), a line in section 4 for any decision with a "why", and sections 3 and 6 if storage or next
  steps changed.
- `docs/DESIGN.md`, if how the bot works changed (flow, components, model output, rules, where to change things).
- `README.md`, if how to install, run, use or configure it changed (pages, addresses, settings, commands, layout).

Check all three against the change every time, even if one ends up needing nothing. Section 7 of
`PROJECT_LOG.md` has the details. Also run the tests (`python -m pytest -q`) and make sure they pass.

## How the user wants to work
- **Ask before implementing** when anything in a request is unclear or could reasonably go two ways. Explain
  options in plain language, without jargon.
- **Never commit or push.** The user reviews the changes and commits them. Leave changes uncommitted on the
  current branch.
- Each team member works on their own branch (this user's is `rishabh/web-frontend`). Don't switch, merge or
  create branches unless asked.
- When reporting back, say what changed, what the user needs to do (for example restart `run.bat`), and what
  was checked.

## Principles of this project (keep them true)
- **Phase 1 scope:** footwear only, photos only. Solutions/products, text/voice/video and follow-up
  conversations come later and must fit the existing structure (see DESIGN.md section 7).
- **The backend speaks the real WhatsApp Cloud API.** The simulator (port 8000, `app/simulator/`) is only a
  stand-in for Meta's servers and the customer's phone. Never add bot behaviour that works only in the
  simulator. Anything the bot does must be something real WhatsApp supports, so switching to WhatsApp stays a
  settings change (`channel.mode: whatsapp` + `.env`), not a redesign.
- **Customers never see scores, field names or decision codes.** All customer wording lives in `app/replies.py`.
  The bot only tells the customer things it is confident about.
- **Internal data is only on the backend dashboard** (port 8001, `app/debug.py`, `app/dashboard_static/`),
  bound to 127.0.0.1. Never serve it on the bot's port 8000, which becomes public with real WhatsApp. The
  dashboard shows only the latest diagnosis; the full history stays in `data/bot.db` for model evaluation.
- **`config/fields.yaml` drives the 10 fields** (prompt, output schema, validation, rules, dashboard). Allowed
  values come from the workbooks in `config/reference/` via `scripts/import_reference.py`.
- **Model calls go through OpenRouter** (`core.provider: openrouter`, key `OPENROUTER_API_KEY`, model id like
  `google/gemini-3.5-flash`). Google AI Studio directly (`core.provider: gemini`) is only a fallback option.
  New providers go in `app/core/providers/` behind the same `diagnose()` interface.
- Settings belong in `config/settings.yaml` and secrets in `.env`, not in code.

## Practical notes
- The user runs Windows: `run.bat` starts both pages (chat on http://127.0.0.1:8000/sim/, dashboard on
  http://127.0.0.1:8001/). Python changes need a restart of `run.bat`; page files (HTML/CSS/JS) don't.
- After changing a page's CSS or JS, bump the `?v=` number in that page's `index.html`, so browsers load the
  new file.
- Never commit or print the contents of `.env`. `data/` (databases, photos) is local and not in git.
- Tests need no API key or internet (mock model + fake OpenRouter and Gemini servers). Use
  `core.provider: mock` to try things without spending money on model calls.
