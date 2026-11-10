"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Notice } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { HOME, saveSession, type User } from "@/lib/auth";

const DEMO = [
  { email: "faculty1@educrew.local", label: "Faculty 1" },
  { email: "hod@educrew.local", label: "HOD" },
  { email: "plumbing@educrew.local", label: "Plumbing in-charge" },
  { email: "electrical@educrew.local", label: "Electrical in-charge" },
  { email: "estate@educrew.local", label: "Estate Officer" },
];

export default function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function login(e?: FormEvent, asEmail?: string) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ token: string; user: User }>("/auth/login", {
        body: { email: asEmail ?? email, password: asEmail ? "demo1234" : password },
        auth: false,
      });
      saveSession(res.token, res.user);
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : HOME[res.user.role]);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-10">
      <div className="mb-8">
        <div className="text-3xl font-bold tracking-tight text-accent">EduCrew</div>
        <p className="mt-1 text-sm text-ink-2">Work log, maintenance tickets and class cover for CSE (AI &amp; ML).</p>
      </div>
      <form onSubmit={login} className="space-y-4">
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" className="field" type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" className="field" type="password" autoComplete="current-password" required
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <Notice tone="bad">{error}</Notice>}
        <button className="btn btn-primary w-full" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
      </form>
      <div className="rule-top mt-8">
        <div className="eyebrow mb-2">Demo accounts (one tap)</div>
        <div className="flex flex-wrap gap-2">
          {DEMO.map((d) => (
            <button key={d.email} type="button" className="chip" disabled={busy} onClick={() => login(undefined, d.email)}>
              {d.label}
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">All demo accounts use the password demo1234. Data is anonymised (Faculty 1–12).</p>
      </div>
    </main>
  );
}
