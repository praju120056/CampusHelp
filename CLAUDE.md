# EduCrew (campus)

Faculty dashboard for the RNSIT Faculty Hackathon 2026. Three modules: Daily Work Log + HOD Monitor, QR Maintenance Ticketing, Smart Class Adjustment.

**`spec.md` is the source of truth.** Read it before starting any task. If code and spec disagree, ask the user which is right, then update the spec.

## Stack

- Backend: FastAPI (Python 3.10+; the laptop runs 3.10, so avoid 3.11-only features), SQLAlchemy, SQLite (keep schema Postgres-compatible), APScheduler, Pydantic
- Frontend: Next.js (App Router) + React + TypeScript, installable PWA, Tailwind
- Live updates: Server-Sent Events from FastAPI
- AI triage: Google Gemini API; model ID from env `GEMINI_MODEL` (default `gemini-3.7-flash`). Must have a rule-based fallback.
- Email: SMTP (Gmail app password). If it fails, write to the local outbox table/page. No WhatsApp (out of scope).
- Runs on one Windows laptop (repo at `D:\Code\projects\campus`), served over local Wi-Fi to phones.

## Layout (create as needed)

```
backend/app/        FastAPI app: routers/, models/, services/, schemas/
backend/tests/      pytest
frontend/           Next.js app
data/               seed scripts, the real timetable .xlsx (do not commit real names; see Privacy)
.env.example        all env vars, no secrets
spec.md  CLAUDE.md
```

## Commands

Windows. Use PowerShell-compatible commands; avoid bash-only syntax in scripts and docs.

```
# backend (from backend/)
python -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest -q

# frontend (from frontend/)
npm install
npm run dev -- -H 0.0.0.0
npm run lint ; npm run build
npm run start -- -H 0.0.0.0          # demo day: faster on phones than dev mode

# seed demo data (from backend/; resets the database; an empty database is seeded on first start)
python -m app.seed
```

Demo logins: password `demo1234` for all. `hod@educrew.local`, `faculty1@educrew.local` … `faculty12@`, `electrical@` / `plumbing@` / `housekeeping@` / `it@` / `civil@`, `estate@educrew.local`.

Keep these commands accurate. If you change one, update this section.

## How to work

- Build in small steps in this order: DB schema + auth + seed data, then Module B (tickets + live map), then Module C (adjustments), then Module A (log + analytics). If time is short, cut per the priority list in spec.md.
- Use plan mode for anything touching more than one file or a new module.
- Every task must finish with a check you ran: tests, `npm run build`, or a request against the running API. Show the output. Do not say "done" without it.
- Write pytest tests for: swap/substitute clash-checking (must never double-book a faculty member), ticket routing and escalation, duplicate detection, fairness score.
- Keep modules separate: business logic in `services/`, no logic in routers or React components beyond wiring.
- Prefer simple and demo-ready over clever. This is a one-day hackathon prototype with a possible pilot afterwards.

## Rules

- Never commit secrets. API keys, SMTP passwords and JWT secrets live in `.env` (gitignored). Maintain `.env.example`.
- Public endpoints (ticket submission, status page) are rate limited and need no login. Everything else needs a JWT and a role check.
- The QR encodes only a location ID. Never put block/floor/room details in the QR URL.
- AI triage output is a suggestion. The in-charge can override it. Ticket creation must succeed even if Gemini is down.
- Weights for the workload formula come from config (defaults in spec.md A3), never hard-coded in logic.
- Do not install new heavy dependencies without saying why. Prefer what is already in the stack.

## UI and design

*Proposed. Built this way so there is something to react to; Saj to approve or change (spec §8a).*

- **Feel:** a campus notice board, not a SaaS template. Warm paper background, ink text, hairline rules between sections. No shadows-on-cards grids, gradients or hero banners.
- **One loud element:** the Live Ticket Map, a dark panel (`#1a1a19`) with bright room tiles. Everything else stays calm.
- **Colour tokens** (in `frontend/app/globals.css`): paper `#f7f5f0`, surface `#fdfcfa`, ink `#1c1b19`, muted `#7a776f`, rule `#e2ddd3`, accent teal `#1f5c63` (actions and links only).
- **Status colours are reserved for state:** good `#0ca30c`, warning `#fab219`, critical `#d03b3b`. Every status shows an icon and a text label as well, never colour alone (map, lists, charts).
- **Charts:** series blue `#2a78d6`, second series orange `#eb6834` (validated for colour-blind safety). Thin bars (≤24px), 2px lines, hairline grid. Every chart has a tooltip, a legend when it has 2+ series, and a "Show table" view. Hand-drawn SVG; no chart library.
- **Type:** system sans (no web fonts, so it works offline). Ticket refs and room codes in monospace. Tabular figures in tables.
- **Mobile first** for the scan form and faculty log: 360px wide, 44px touch targets, the main button pinned at the bottom. Laptop/projector layouts for the HOD dashboard and the map.
- **Words:** plain, short labels ("Confirm day", "Find cover", "Already reported"). Sentence case.

## Privacy

Real faculty names and the real timetable are sensitive. Keep the real timetable file out of git (`data/*.xlsx`, `data/*.csv`, `data/*.pdf` in `.gitignore`). The AI timetable reader sends the whole PDF, real names included, to Google; it runs only when the HOD picks it or the local parser cannot read a cell. Demo and tests use anonymised data (Faculty 1…N) unless the user says otherwise.

## Asking the user

The user (Saj) is a CSE (AI & ML) faculty member, not a full-time web developer. Explain decisions briefly in plain language. Make reasonable assumptions and list them in your reply. Ask the user only when a choice changes the data model, the demo story or what gets deleted, and ask in one batch rather than one at a time.
