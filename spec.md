# EduCrew — Spec

Smart Faculty Dashboard for Daily Work Logging, QR Campus Maintenance Ticketing, and Class Adjustment.
RNSIT Faculty Hackathon 2026 · Category: Software

## 1. Decisions

| Item | Decision |
|---|---|
| Stack | FastAPI (Python) + Next.js/React PWA |
| Database | SQLite via SQLAlchemy (laptop demo); schema stays Postgres-compatible |
| Live updates | Server-Sent Events (SSE) from FastAPI to the PWA |
| Hosting | Laptop only, served on local Wi-Fi; phones open `http://<laptop-ip>:3000` |
| Scope | The 3 modules only: requirements and acceptance criteria |
| Wow features | Live ticket map, AI triage, workload fairness analytics |
| LLM | Google Gemini Flash via the Gemini API. Model ID is an env var (`GEMINI_MODEL`), default `gemini-3.7-flash`; confirm the exact ID in Google AI Studio before the build. Internet available on demo day. |
| Timetable | Build and test on a synthetic, anonymised CSE-AIML timetable first. The real RNSIT department timetable is imported from the department's PDF timetables (or Excel), with faculty names replaced by Faculty 1…N on import. Sections are labelled semester + letter (3A, 5B). Lab batches (A1/A2) run in parallel, so a timetable row has an optional batch. NSS/PE/Yoga, library hour, tea and lunch are not stored; societal and mini project have no single faculty and are skipped. PDFs are read by a local parser first and by Gemini (a scan, or cells the parser cannot read); the HOD reviews the draft (names behind faculty codes) before saving |
| Python | 3.10+ (the laptop runs 3.10); avoid 3.11-only features |
| Floor plan | None available yet: generate a simple grid-based SVG from the locations table (see B14) |

## 2. Roles

| Role | Can do |
|---|---|
| Public (no login) | Scan a QR and submit a ticket; view a ticket status page |
| Faculty | Log work, request class adjustments, accept/decline substitute requests |
| HOD | View all department data, analytics, approve/override adjustments |
| Dept. In-charge | See and update tickets for their category (Electrical, Plumbing, Housekeeping, IT, Civil) |
| Estate Officer | Receives escalations; sees all tickets |

Auth: email + password with JWT. Seeded demo users, one per role.

## 3. Module A — Daily Work Log + HOD Monitor

### Requirements
- A1. Faculty can log a day's entries (class, lab, duty, meeting) in under 1 minute.
- A2. The form is pre-filled from the faculty member's timetable for that day. Faculty only confirm, edit, or add topic text.
- A3. Entry types carry a weight, used to turn a mix of activities into one workload number. Proposed defaults (configurable in an admin screen, to be confirmed with the HOD): theory period 1.0, lab period 1.5 (a 2-period lab block = 3.0), invigilation/duty slot 1.0, meeting/committee hour 0.5, substitution period 1.0 (counts in addition to own classes).
- A4. HOD dashboard shows today's status per faculty (logged / not logged), with a reminder list of faculty who have not logged.
- A5. Weekly and monthly load charts per faculty and department.
- A6. Excel export of logs for a date range and department.
- A7. Audit trail: every create/edit is stored with user and timestamp.

### Wow: Workload Fairness Analytics
- A8. Fairness score for the department: a Gini-style index of weighted load across faculty, shown as a single number with a trend.
- A9. Per-faculty load bar against the department mean; flag anyone above mean + 1 SD (overloaded) or below mean − 1 SD (underused).
- A10. Rolling 4-week view with a "burnout watch" badge when someone is overloaded for 3 consecutive weeks.
- A11. One-click report export (Excel + PDF) with load, duty and adjustment statistics for NAAC/NBA.

### Acceptance criteria
- A faculty member with a seeded timetable can submit a full day's log in ≤ 4 taps/clicks after login.
- HOD sees the entry on the dashboard within 2 seconds, without a page reload.
- Fairness score and flags recompute when a new entry is saved.
- Excel export opens in Excel with correct columns and totals matching the dashboard.

## 4. Module B — QR Maintenance Ticketing

### Requirements
- B1. Each room, washroom, lift and lab has a QR encoding a URL with only a location ID, e.g. `/r/BLK-A-F2-R204`. Block, floor, room name and assets come from the database, so details can change without reprinting.
- B2. Admin can bulk-generate QR codes as a printable PDF sheet (label + QR per location).
- B3. Scanning opens a no-login mobile form: location shown (read-only), category picker, description, optional photo, optional name/phone/email (email is used for the "resolved" notice in B8).
- B4. Submission creates a ticket and returns a ticket status page URL.
- B5. Auto-routing: category maps to a department in-charge. Assignment can be changed by the in-charge.
- B6. Ticket states: New → Assigned → In progress → Resolved (or Rejected with reason).
- B7. Priority deadlines per priority level (e.g. Critical 4 h, High 24 h, Normal 72 h). A scheduler sends reminders before the deadline and escalates to the Estate Officer after it.
- B8. Notifications: email is the primary channel (SMTP with an app password; Gmail is fine for the demo, with a daily sending limit). In-app notifications always. If SMTP is not configured or fails, messages are written to a local outbox page so the demo never breaks. Emails go out for: new ticket (to in-charge), pre-deadline reminder, escalation (to Estate Officer), ticket resolved (to the reporter, if an email was given), and substitute requests (see C5).
- B9. Abuse controls: per-IP rate limit and an honeypot field on the public form; in-charge can reject a ticket.

### Wow: AI Triage
- B10. On submission, the description and optional photo are sent to an LLM, which returns: category, priority, a one-line summary, and a confidence value.
- B11. Duplicate detection: if an open ticket exists for the same location and category (or a near-identical description), the user is told "already reported" and the new report is attached to the existing ticket as a +1.
- B12. The triage result is a suggestion shown to the in-charge with the original text; the in-charge can override it.
- B13. Offline fallback: if the LLM is unreachable, a rule-based keyword classifier assigns the category and priority, and the ticket is still created.

### Wow: Live Ticket Map
- B14. An SVG floor plan per block/floor, with each room as a clickable shape keyed by location ID. With no drawn plan, the map is auto-generated from the `locations` table as a labelled grid of room tiles (rows = corridor sides, order = room number), so the map works on day one. A traced plan can replace it later by filling in `map_shape_id`.
- B15. Room colour reflects the worst open ticket: green (none), amber (normal/high), red (critical or overdue), pulsing when new.
- B16. The map updates in real time via SSE when a ticket is created, changed or escalated, with no refresh.
- B17. Clicking a room shows its open tickets and history. Filter by category and by status.
- B18. Campus summary strip: open tickets, overdue, average resolution time, today's resolved.

### Acceptance criteria
- Scan to submitted ticket in ≤ 3 steps with no login on a phone.
- A new ticket appears on the Live Ticket Map as a pulsing room within 2 seconds on a second device.
- A ticket past its deadline escalates to the Estate Officer automatically (demo mode: deadlines can be shortened to minutes).
- Submitting a second report for the same location/category shows "already reported" and increments the count on the original.
- With the LLM disabled, ticket creation still succeeds with a rule-based category.

## 5. Module C — Smart Class Adjustment

### Requirements
- C1. Faculty submit a request: date, period(s), reason. Multi-period blocks (e.g. 2-period labs) are treated as one unit.
- C2. Timetable data model: faculty, section, subject, period, room, type (theory/lab). One-time Excel import with validation (clashes, missing fields, unknown faculty) and an error report.
- C3. Candidate search, in this order:
  1. Swap — a faculty member teaching the same section whose class can be exchanged with the requester's without creating a clash for either.
  2. Free substitute — a faculty member who is free in that period (not on leave, no class, no duty) and is qualified for the subject.
  3. Ranking by lowest weekly weighted load (from Module A).
- C4. Each suggestion shows an explainable score: free/not free, subject match, current weekly load, and number of recent substitutions.
- C5. Requester picks a suggestion, which sends an accept/decline request to the candidate by email (one-click accept and decline links with a single-use token) and in-app. Decline moves to the next candidate.
- C6. On accept: HOD is notified and the timetable view for that date shows the adjustment. Both entries appear in the work log (Module A) with an "adjustment" tag.
- C7. HOD can override or cancel an adjustment.
- C8. Fairness link: substitution counts feed the fairness analytics in A8–A10.

### Acceptance criteria
- For a seeded request, ranked suggestions appear in < 2 seconds.
- No suggestion ever creates a clash for the suggested faculty member (verified by tests on the seeded timetable).
- A decline automatically offers the next candidate; an accept updates the timetable and notifies the HOD.
- Multi-period lab requests only match candidates free for the full block.

## 6. Data Model (core tables)

List-valued fields (`qualified_subjects`, `periods`, `score_breakdown`, `settings.value`) are JSON columns, which behave the same on SQLite and Postgres.

- `users(id, name, email, password_hash, role, dept_id)`
- `departments(id, name)`
- `faculty(id, user_id, designation, qualified_subjects JSON)`
- `timetable_slots(id, faculty_id, section, subject, day, period, room_id, type)`
- `leaves(id, faculty_id, date, period?)`
- `duties(id, faculty_id, date, period, kind)`: invigilation and other duty slots (needed by C3 "no duty" and the A3 weights)
- `work_logs(id, faculty_id, date, type, topic, units, weight, period?, section?, subject?, source_slot_id?, tag?, adjustment_id?, created_by, created_at, updated_at)`: `units` = periods, slots or hours; loads are always recomputed as units × the current weight, `weight` is a snapshot; `tag` is e.g. `adjustment` (C6); type `adjusted` records a class handed to someone else (weight 0)
- `log_days(id, faculty_id, date, submitted_at)`: marks a submitted day; drives the HOD logged / not logged view (A4)
- `settings(key, value JSON)`: workload weights (A3) and priority deadlines (B7); defaults are seeded, never hard-coded in logic
- `locations(id, code, block, floor, room_name, kind, side, sort_order, map_shape_id)`: `side`/`sort_order` lay out the generated grid map (B14)
- `assets(id, location_id, name)`
- `category_assignees(category, user_id)`: routing from category to in-charge (B5)
- `tickets(id, ref, location_id, category, priority, status, description, photo_url?, summary, ai_category, ai_priority, ai_confidence, ai_source, reporter_name?, reporter_phone?, reporter_email?, report_count, assigned_to, worker?, deadline_at, reminded_at?, escalated_at?, duplicate_of?, rejection_reason?, resolved_at?, created_at, updated_at)`: `ref` is the short unguessable public ID used in status URLs; `ai_*` keep the triage suggestion separate from the final values (B12), `ai_source` is `gemini` or `rules`; `report_count` holds the +1s (B11) and each +1 is kept as a child row with `duplicate_of` set; `resolved_at` feeds average resolution time (B18)
- `ticket_events(id, ticket_id, actor, action, note, created_at)`
- `notifications(id, user_id?, channel, to, subject, body, status, created_at)`: in-app messages and the email outbox (B8); `status` is `sent`, `outbox` or `failed`
- `adjustments(id, requester_id, date, periods JSON, section, subject, slot_type, reason, status, chosen_candidate_id?, overridden_by?, note?, created_at, updated_at)`: one class unit (a period, or a whole lab block) per row; status `open`, `pending`, `accepted`, `exhausted` or `cancelled`
- `adjustment_candidates(id, adjustment_id, candidate_id, kind, rank, score, score_breakdown JSON, swap_periods JSON?, swap_subject?, swap_type?, state, token_hash?, token_used_at?, requested_at?, responded_at?)`: the token backs the single-use accept/decline links (C5); for a swap, `swap_*` is the candidate's class the requester takes in return
- `audit_log(id, user_id, entity, entity_id, action, at)`

## 7. API Sketch (FastAPI)

As built (FastAPI also serves interactive docs at `/docs`):

- `POST /auth/login`, `GET /auth/me`
- `GET/POST /logs`, `GET /logs/prefill?date=`
- `GET /analytics/today`, `POST /analytics/remind`, `GET /analytics/fairness`, `GET /analytics/load`
- `GET /exports/logs.xlsx`, `GET /exports/report.xlsx`, `GET /exports/report.json` (the PDF is the printable `/report` page, saved as PDF from the browser)
- Public, rate limited: `GET /locations/{code}`, `GET /locations/{code}/qr.png`, `POST /tickets`, `GET /tickets/{ref}` (status page), `GET /adjustments/token/{token}`, `POST /adjustments/respond-token`
- `GET /tickets`, `GET /tickets/{ref}/full`, `PATCH /tickets/{ref}` (in-charge / Estate Officer), `POST /tickets/{ref}/demo-deadline` (demo mode only)
- `GET /map/floors`, `GET /map/summary`, `GET /map/{block}/{floor}`, `GET /locations`, `GET /locations/{code}/tickets`
- `GET /stream/{tickets|logs|adjustments}?token=` (SSE; the JWT goes in the query string because EventSource cannot send headers)
- `POST /adjustments`, `GET /adjustments/mine`, `GET /adjustments` (HOD), `GET /adjustments/{id}/candidates`, `POST /adjustments/{id}/choose`, `POST /adjustments/{id}/respond`, `POST /adjustments/{id}/cancel`, `GET /adjustments/{id}/free-faculty` + `POST /adjustments/{id}/override` (HOD)
- `GET /timetable/me`, `GET /timetable/day`, `POST /timetable/import`, `GET /timetable/template.xlsx`
- `GET/PUT /admin/settings`, `GET /notifications`, `GET /outbox`, `GET /health`

## 8. Non-functional

- Runs fully on one laptop with two commands (`uvicorn`, then `npm run dev` or `npm run start`). No Docker.
- PWA install and the service worker need https or localhost. Phones on `http://<laptop-ip>:3000` can use everything but cannot install; for the demo, add the laptop URL under Chrome's "Insecure origins treated as secure" flag on the demo phones.
- PWA installable on Android/iOS home screen; mobile-first layouts for the scan form and faculty log.
- All public endpoints are rate limited; uploads limited to images under 5 MB.
- Passwords hashed (bcrypt); JWT expiry 12 h; role checks on every protected route.
- LLM key read from an environment variable; never logged.

## 8a. UI and Design Principles

- The UI is designed for this tool, not templated: no generic SaaS-card layout, no stock gradient or hero banner. Full rules go in `CLAUDE.md` under "UI and design" once the design plan below is approved.
- Before any screen is built, a short design plan (colours, type, layout wireframes, principles) is written and approved by the user.
- One memorable element (the live ticket map); everything else calm and quiet.
- Status is never colour-only: icon or pattern plus a text label on the map, lists and charts.
- Mobile first for the scan form and faculty log (360px wide, 44px touch targets); laptop/projector layouts for the HOD dashboard and map.
- Every chart has a legend (2 or more series), a tooltip and a table view.

## 9. Demo Data

- Timetable: a synthetic CSE-AIML timetable (12 faculty, ~4 sections, a full week, labs as 2-period blocks) until the real PDFs are imported; then the real timetable, imported with names anonymised to Faculty 1…N. The real-name map stays local in `data/` and out of git.
- 1 block with 2 floors, ~20 locations, each with a QR.
- 15 tickets across categories and states, 2 overdue.
- 4 weeks of work logs with deliberately uneven loads, so the fairness view has something to show.

## 10. Demo Script (about 5 minutes)

1. Phone scans a QR on stage, then reports "tap leaking" with a photo. AI triage tags it Plumbing / High.
2. On the projector, the room pulses on the Live Ticket Map. The in-charge opens it and assigns it.
3. Shorten the deadline: it escalates to the Estate Officer on the map, in red.
4. A faculty member requests an adjustment. Ranked, explainable suggestions appear. The candidate accepts on a second phone.
5. HOD view: the log updated automatically. The fairness score moves, and an overloaded faculty member is flagged.
6. Export the NAAC/NBA report.

## 11. Out of Scope (for this version)

WhatsApp/SMS alerts, hosting beyond the laptop, SSO/LDAP, full timetable optimisation, native mobile apps.

## 12. Open Questions

- Real timetable file: format of the Excel (rows = faculty or rows = days?) so the importer matches it. Until then, work proceeds on the synthetic timetable.
- Gemini API key: create one in Google AI Studio and confirm the exact model ID there.
- Floor plan: sketch or photo of one floor later, to replace the generated grid.
- Workload weights: confirm or change the proposed defaults in A3 with the HOD.

Resolved:
- Privacy: faculty are anonymised (Faculty 1…N) in the demo, tests and git, including after the real timetable is imported.

## 13. Priority and Cut List

If time runs short, build in this order and cut from the bottom.

**Must (the demo fails without these)**
- Auth with seeded role users; seed data
- QR scan → ticket with rule-based triage; status page
- Live Ticket Map over SSE; deadline escalation to the Estate Officer
- Clash-safe candidate search (swap, then free substitute); accept/decline
- Timetable-prefilled work log; HOD today view (logged / not logged)
- Fairness score with overloaded/underused flags

**Should**
- Gemini triage, including the photo; in-charge override
- Duplicate detection (+1)
- SMTP email (the outbox page is always there as a fallback)
- Admin screen for workload weights and deadlines
- Burnout watch (A10) and fairness trend
- Weekly/monthly load charts; Excel log export
- Real timetable importer with validation report

**Cut first**
- PDF outputs: the NAAC/NBA report PDF (A11) and the printable QR sheet PDF (B2). Excel export stays, and QR codes are still generated as PNG images.
