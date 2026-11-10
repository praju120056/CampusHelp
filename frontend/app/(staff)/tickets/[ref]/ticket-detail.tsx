"use client";
// B5, B6, B12: the in-charge's view of one ticket. The AI triage is shown as a suggestion next
// to the original text, and every field can be overridden.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useCurrentUser } from "@/components/shell";
import { Icon, Loading, Notice, PriorityTag, StatusTag, Tag } from "@/components/ui";
import { api, apiBase, errorText } from "@/lib/api";
import { CATEGORIES, dateTimeLabel, label, PRIORITIES, relative } from "@/lib/format";
import { useLive } from "@/lib/live";

type Ticket = {
  ref: string;
  status: string;
  status_label: string;
  category: string;
  priority: string;
  summary: string;
  description: string;
  photo_url: string | null;
  location: { code: string; room_name: string; block: string; floor: number };
  assigned_to: string | null;
  assigned_to_id: number | null;
  worker: string | null;
  report_count: number;
  deadline_at: string;
  created_at: string;
  resolved_at: string | null;
  overdue: boolean;
  escalated: boolean;
  escalated_at: string | null;
  rejection_reason: string | null;
  ai: { category: string | null; priority: string | null; confidence: number | null; source: string | null; overridden: boolean };
  reporter: { name: string | null; phone: string | null; email: string | null };
  events: { actor: string; action: string; note: string | null; at: string }[];
  can_edit: boolean;
  demo_mode: boolean;
};

export default function TicketDetail() {
  const { ref } = useParams<{ ref: string }>();
  const user = useCurrentUser();
  const [t, setT] = useState<Ticket | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [worker, setWorker] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [owners, setOwners] = useState<{ id: number; name: string }[]>([]);

  const load = useCallback(() => {
    api<Ticket>(`/tickets/${ref}/full`)
      .then(setT)
      .catch((e) => setError(errorText(e)));
  }, [ref]);
  useEffect(load, [load]);
  useEffect(() => {
    api<{ id: number; name: string; role: string }[]>("/users")
      .then((users) => setOwners(users.filter((u) => u.role === "incharge" || u.role === "estate")))
      .catch(() => {});
  }, []);
  useLive(["tickets"], (_type, data) => {
    if (data.ref === ref) load();
  });

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      setT(await api<Ticket>(`/tickets/${ref}`, { method: "PATCH", body }));
      setNote("");
      setShowReject(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function demoDeadline() {
    setBusy(true);
    try {
      setT(await api<Ticket>(`/tickets/${ref}/demo-deadline`, { method: "POST" }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!t) return error ? <Notice tone="bad">{error}</Notice> : <Loading />;
  const open = !["resolved", "rejected"].includes(t.status);
  const edit = t.can_edit && open;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <div>
        <Link href="/tickets" className="text-sm text-accent hover:underline">← Tickets</Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="mono text-sm font-semibold">{t.ref}</span>
          <StatusTag status={t.status} label={t.status_label} />
          <PriorityTag priority={t.priority} />
          {t.overdue && open && <Tag tone="bad" icon="alert">Overdue{t.escalated ? ", escalated" : ""}</Tag>}
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{t.summary}</h1>
        <p className="mt-1 text-sm text-ink-2">
          {t.location.room_name} · Block {t.location.block}, Floor {t.location.floor} ·{" "}
          <span className="mono">{t.location.code}</span>
        </p>

        <section className="rule-top mt-5">
          <div className="eyebrow mb-1">Reporter wrote</div>
          <blockquote className="border-l-4 border-rule-strong pl-3 text-base">{t.description}</blockquote>
          {t.photo_url && (
            <a href={`${apiBase()}${t.photo_url}`} target="_blank" rel="noreferrer" className="mt-3 block w-fit">
              <img src={`${apiBase()}${t.photo_url}`} alt="Photo from the reporter" className="max-h-72 rounded-md border border-rule" />
            </a>
          )}
          <p className="mt-2 text-xs text-muted">
            {t.reporter.name ?? "Anonymous"}
            {t.reporter.phone && ` · ${t.reporter.phone}`}
            {t.reporter.email && ` · ${t.reporter.email}`}
            {t.report_count > 1 && ` · reported by ${t.report_count} people`}
            {` · ${dateTimeLabel(t.created_at)}`}
          </p>
        </section>

        <section className="rule-top mt-6">
          <div className="mb-2 flex items-center gap-2">
            <Icon name="spark" className="text-accent" />
            <h2 className="heading">AI triage suggestion</h2>
            {t.ai.overridden && <Tag tone="neutral">Overridden</Tag>}
          </div>
          <p className="text-sm">
            {label(CATEGORIES, t.ai.category)} · {label(PRIORITIES, t.ai.priority)}
            {t.ai.confidence !== null && ` · ${Math.round(t.ai.confidence * 100)}% confident`}
            <span className="text-muted"> · {t.ai.source === "gemini" ? "Gemini" : "keyword rules (AI offline)"}</span>
          </p>
          {edit && (
            <div className="mt-3 flex flex-wrap gap-3">
              <div>
                <label className="label" htmlFor="cat">Category</label>
                <select id="cat" className="field w-44" value={t.category} disabled={busy}
                  onChange={(e) => patch({ category: e.target.value })}>
                  {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="pri">Priority</label>
                <select id="pri" className="field w-44" value={t.priority} disabled={busy}
                  onChange={(e) => patch({ priority: e.target.value })}>
                  {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
            </div>
          )}
        </section>

        <section className="rule-top mt-6">
          <h2 className="heading mb-3">History</h2>
          <ol className="space-y-3">
            {[...t.events].reverse().map((e, i) => (
              <li key={i} className="grid grid-cols-[110px_1fr] gap-3 text-sm">
                <span className="text-xs text-muted">{dateTimeLabel(e.at)}</span>
                <span>
                  <strong className="font-medium">{e.actor}</strong>{" "}
                  <span className="text-ink-2">{e.note ?? e.action}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <aside className="space-y-5 lg:border-l lg:border-rule lg:pl-6">
        <div>
          <div className="eyebrow">Deadline</div>
          <div className={`text-lg font-semibold ${t.overdue && open ? "text-bad-ink" : ""}`}>
            {open ? relative(t.deadline_at) : "Closed"}
          </div>
          <div className="text-xs text-muted">{dateTimeLabel(t.deadline_at)}</div>
          {t.escalated_at && <div className="mt-1 text-xs text-bad-ink">Escalated {dateTimeLabel(t.escalated_at)}</div>}
        </div>
        <div>
          <div className="eyebrow">Responsible</div>
          <div className="font-medium">{t.assigned_to ?? "—"}</div>
          {t.worker && <div className="text-sm text-ink-2">Worker: {t.worker}</div>}
        </div>

        {error && <Notice tone="bad">{error}</Notice>}
        {!t.can_edit && open && (
          <Notice tone="info">
            {user.role === "hod" ? "View only. The in-charge or Estate Officer updates tickets." : "Assigned to another in-charge."}
          </Notice>
        )}
        {t.status === "rejected" && <Notice tone="warn">Rejected: {t.rejection_reason}</Notice>}

        {edit && (
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="worker">Give work to</label>
              <div className="flex gap-2">
                <input id="worker" className="field" placeholder={t.worker ?? "e.g. Ravi (plumber)"} value={worker}
                  onChange={(e) => setWorker(e.target.value)} />
                <button className="btn" disabled={busy || !worker.trim()} onClick={() => patch({ worker })}>Assign</button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {t.status !== "in_progress" && (
                <button className="btn" disabled={busy} onClick={() => patch({ status: "in_progress" })}>
                  <Icon name="clock" /> Start work
                </button>
              )}
              <button className="btn btn-primary" disabled={busy} onClick={() => patch({ status: "resolved" })}>
                <Icon name="check" /> Resolved
              </button>
            </div>
            <div>
              <label className="label" htmlFor="owner">Reassign to</label>
              <select id="owner" className="field" value={t.assigned_to_id ?? ""} disabled={busy}
                onChange={(e) => patch({ assigned_to: Number(e.target.value) })}>
                {owners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="note">Add a note</label>
              <textarea id="note" className="field" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn btn-sm mt-2" disabled={busy || !note.trim()} onClick={() => patch({ note })}>Save note</button>
            </div>
            {showReject ? (
              <div>
                <label className="label" htmlFor="reason">Reason for rejecting</label>
                <input id="reason" className="field" value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. Not a maintenance issue" />
                <div className="mt-2 flex gap-2">
                  <button className="btn btn-danger btn-sm" disabled={busy || !reason.trim()}
                    onClick={() => patch({ status: "rejected", rejection_reason: reason })}>Reject ticket</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setShowReject(false)}>Cancel</button>
                </div>
              </div>
            ) : (
              <button className="text-sm text-bad-ink underline underline-offset-2" onClick={() => setShowReject(true)}>
                Reject this ticket…
              </button>
            )}
          </div>
        )}

        {t.demo_mode && open && (
          <div className="rule-top">
            <div className="eyebrow mb-2">Demo</div>
            <button className="btn btn-sm w-full" disabled={busy} onClick={demoDeadline}>
              Make deadline 20 seconds from now
            </button>
            <p className="mt-1 text-xs text-muted">Escalation to the Estate Officer then happens on its own.</p>
          </div>
        )}
      </aside>
    </div>
  );
}
