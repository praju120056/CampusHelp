# EduCrew frontend

Next.js 16 (App Router, Turbopack, Cache Components) + Tailwind 4. See the root `README.md` for how to run the whole app and `CLAUDE.md` for the UI rules.

- `app/r/[code]`, `app/t/[ref]`, `app/respond/[token]`: public pages (QR report form, ticket status, email accept/decline).
- `app/(staff)/…`: pages behind login; `components/shell.tsx` handles login and role checks.
- `lib/api.ts`: talks to the FastAPI backend on the same host, port 8000 (override with `NEXT_PUBLIC_API_URL`).
- `lib/live.ts`: Server-Sent Events for live updates.

Pages that read URL params are a small server `page.tsx` wrapping a client component in `<Suspense>`; Cache Components requires this.
