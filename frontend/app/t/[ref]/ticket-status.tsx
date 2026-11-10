"use client";
// Public ticket status page (no login). Refreshes every 20 seconds.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Icon, Notice, PriorityTag, StatusTag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { CATEGORIES, dateTimeLabel, label } from "@/lib/format";
import { useInterval } from "@/lib/live";

type PublicTicket = {
  ref: string;
  status: string;
  status_label: string;
  category: string;
  priority: string;
  summary: string;
  location: { code: string; room_name: string; block: string; floor: number };
  report_count: number;
  rejection_reason: string | null;
  created_at: string;
  resolved_at: string | null;
  events: { action: string; at: string; note: string | null }[];
  merged_from?: string;
};

const STEPS = [
  { key: "new", label: "Received" },
  { key: "assigned", label: "Assigned" },
  { key: "in_progress", label: "Being fixed" },
  { key: "resolved", label: "Fixed" },
];

const EVENT_TEXT: Record<string, string> = {
  created: "Report received",
  routed: "Sent to the maintenance team",
  status_changed: "Status changed",
  plus_one: "Someone else reported it too",
  escalated: "Escalated to the Estate Officer",
  worker: "Work assigned",
};

export default function TicketStatus() {
  const { ref } = useParams<{ ref: string }>();
  const [ticket, setTicket] = useState<PublicTicket | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<PublicTicket>(`/tickets/${encodeURIComponent(ref)}`, { auth: false })
      .then((t) => {
        setTicket(t);
        setError("");
      })
      .catch((e) => setError(errorText(e)));
  }, [ref]);
  useEffect(load, [load]);
  useInterval(load, 20000);

  if (error && !ticket) return <main className="mx-auto max-w-md px-4 py-10"><Notice tone="bad">{error}</Notice></main>;
  if (!ticket) return <p className="p-6 text-sm text-muted">Loading ticket…</p>;

  const stepIndex = STEPS.findIndex((s) => s.key === ticket.status);

  return (
    <main className="mx-auto max-w-md px-4 py-8">
      <div className="eyebrow">Ticket</div>
      <div className="mono text-3xl font-semibold tracking-wider">{ticket.ref}</div>
      {ticket.merged_from && (
        <p className="mt-1 text-sm text-ink-2">Your report {ticket.merged_from} was added to this ticket.</p>
      )}
      <div className="mt-4 border-y border-rule py-3">
        <div className="font-medium">{ticket.summary}</div>
        <div className="mt-1 text-sm text-ink-2">
          {ticket.location.room_name} · Block {ticket.location.block}, Floor {ticket.location.floor}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <StatusTag status={ticket.status} label={ticket.status_label} />
          <PriorityTag priority={ticket.priority} />
          <span className="text-xs text-ink-2">{label(CATEGORIES, ticket.category)}</span>
          {ticket.report_count > 1 && <span className="text-xs text-ink-2">· {ticket.report_count} reports</span>}
        </div>
      </div>

      {ticket.status === "rejected" ? (
        <div className="mt-5">
          <Notice tone="warn">Closed without work: {ticket.rejection_reason}</Notice>
        </div>
      ) : (
        <ol className="mt-6 space-y-0" aria-label="Progress">
          {STEPS.map((step, i) => {
            const done = i <= stepIndex;
            return (
              <li key={step.key} className="flex items-center gap-3 py-1.5">
                <span className={`flex h-7 w-7 items-center justify-center rounded-full border ${
                  done ? "border-good bg-good-soft text-good-ink" : "border-rule-strong text-muted"}`}>
                  {done ? <Icon name="check" size={14} /> : <span className="text-xs">{i + 1}</span>}
                </span>
                <span className={done ? "font-medium" : "text-muted"}>{step.label}</span>
              </li>
            );
          })}
        </ol>
      )}

      <div className="rule-top mt-6">
        <div className="eyebrow mb-2">History</div>
        <ul className="space-y-2 text-sm">
          {[...ticket.events].reverse().map((e, i) => (
            <li key={i} className="flex justify-between gap-3">
              <span>{EVENT_TEXT[e.action] ?? e.action}{e.note && e.action === "status_changed" ? `: ${e.note}` : ""}</span>
              <span className="whitespace-nowrap text-muted">{dateTimeLabel(e.at)}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-6 text-center text-xs text-muted">This page updates by itself.</p>
    </main>
  );
}
