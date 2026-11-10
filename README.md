# EduCrew

Smart faculty dashboard for the RNSIT Faculty Hackathon 2026, built for CSE (AI & ML):

- **Module A:** daily work log (pre-filled from the timetable) and an HOD monitor with workload fairness analytics.
- **Module B:** QR maintenance tickets with AI triage and a live ticket map.
- **Module C:** smart class adjustment (swap or substitute, never double-booking anyone).

Everything runs on one Windows laptop and is served to phones over local Wi-Fi. `spec.md` is the source of truth; `CLAUDE.md` has the working rules.

## Run it

Two terminals, both in PowerShell.

**Backend** (from `backend/`):

```
python -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On first start an empty database is filled with demo data. `python -m app.seed` resets it to fresh demo data at any time (stop the server first).

**Frontend** (from `frontend/`):

```
npm install
npm run build ; npm run start -- -H 0.0.0.0     # demo: fast on phones
npm run dev -- -H 0.0.0.0                        # while changing code
```

Open `http://localhost:3000` on the laptop, or `http://<laptop-wifi-ip>:3000` on a phone.

**Tests:** `pytest -q` in `backend/` (62 tests, including the "never double-book" checks). `npm run lint ; npm run build` in `frontend/`.

## Demo logins

Password for every account: `demo1234`. The login page also has one-tap demo buttons.

| Role | Email |
|---|---|
| Faculty (demo) | `faculty1@educrew.local` (also `faculty2` … `faculty12`) |
| HOD | `hod@educrew.local` |
| In-charges | `plumbing@`, `electrical@`, `housekeeping@`, `it@`, `civil@educrew.local` |
| Estate Officer | `estate@educrew.local` |

Data is synthetic and anonymised. Faculty 3 and 7 are overloaded on purpose; Faculty 11 and 12 are underused.

## Settings (`.env` in the repo root)

Copy `.env.example` to `.env`. A local `.env` with demo mode on already exists on this laptop. It is gitignored, so it never gets committed.

| Setting | What it does |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | AI triage. Empty means keyword rules only (tickets always get created either way). Confirm the model ID in Google AI Studio. |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Email (Gmail: `smtp.gmail.com`, port 587, an app password). Empty means emails wait on the Outbox page. |
| `PUBLIC_BASE_URL` | The address printed in QR codes and email links, e.g. `http://192.168.1.8:3000`. |
| `DEMO_MODE` | `true` shrinks ticket deadlines to minutes and shows the "make deadline 20 seconds" button. |

Restart the backend after changing `.env`.

## Phones on the Wi-Fi

1. Allow the two ports through Windows Firewall (once, in an **administrator** PowerShell), and make sure the Wi-Fi network is set to *Private*:
   `New-NetFirewallRule -DisplayName "EduCrew" -Direction Inbound -Protocol TCP -LocalPort 3000,8000 -Action Allow -Profile Private`
2. Set `PUBLIC_BASE_URL` to the laptop's Wi-Fi address, restart the backend, then print the QR sheet (HOD or Estate Officer → *QR codes* → Print). If the address changes, the printed QRs stop working, so use a fixed hotspot or reserve the IP on the router.
3. Installing as an app needs https. Everything works in the phone browser without installing. To show "install" on stage, open `chrome://flags` on the demo phone, find *Insecure origins treated as secure*, and add the laptop URL.

## Five-minute demo (spec §10)

1. **Phone:** scan a washroom QR → "Tap leaking" + photo → *Send report*. Triage says Plumbing / High.
2. **Projector**, logged in as Estate Officer → *Live map*: the room pulses. **Plumbing in-charge** opens the ticket and assigns a worker; the pulse stops.
3. On the ticket, press *Make deadline 20 seconds from now*. About 20 seconds later it escalates by itself and the room turns red.
4. **Faculty 1** → *Class cover* → tick a class → *Find cover*. Ranked, explained suggestions appear. Tap *Ask*. The colleague accepts on a second phone, from the Class cover page or the email link (the email sits on the Outbox page while SMTP is off).
5. **HOD** → *Dashboard*: the log updates live, the fairness score moves, and Faculty 3 / 7 are flagged overloaded with a burnout watch.
6. *NAAC/NBA report (Excel)*, or *Report (PDF)* → Print → Save as PDF.

## Where things are

```
backend/app/models/     database tables
backend/app/services/   all business logic (triage, tickets, timetable/clash checks, candidates, fairness …)
backend/app/routers/    API endpoints (wiring only)
backend/app/seed.py     demo data
backend/tests/          pytest
frontend/app/           pages (public: r/[code], t/[ref], respond/[token]; staff pages under (staff)/)
frontend/components/    shared UI, live map, charts
```

The real timetable goes in `data/` and is never committed. The importer (HOD → *Import*) replaces names with Faculty 1…N and keeps the name list in `data/faculty_name_map.csv`, which is also gitignored. It currently reads a simple one-row-per-period layout (download the template from the Import page) and will be adapted once the real file's layout is known.
