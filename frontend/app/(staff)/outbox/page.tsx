"use client";
// B8: every email the system has produced. When SMTP is not set up, emails wait here so the demo never breaks.
import { useCallback, useEffect, useState } from "react";
import { Empty, Loading, Notice, PageHeader, Tag } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTimeLabel } from "@/lib/format";
import { useInterval } from "@/lib/live";

type Mail = { id: number; to: string; subject: string; body: string; status: string; error: string | null; created_at: string };

export default function OutboxPage() {
  const [data, setData] = useState<{ smtp_configured: boolean; items: Mail[] } | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = useCallback(() => {
    api<{ smtp_configured: boolean; items: Mail[] }>("/outbox").then(setData).catch(() => {});
  }, []);
  useEffect(load, [load]);
  useInterval(load, 10000);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow="Notifications" title="Email outbox">Newest first.</PageHeader>
      {data && !data.smtp_configured && (
        <div className="mb-4">
          <Notice tone="warn">Email is not set up yet (SMTP settings in .env), so emails are kept here instead of being sent.</Notice>
        </div>
      )}
      {!data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <Empty>No emails yet.</Empty>
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {data.items.map((m) => (
            <li key={m.id} className="py-3">
              <button className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left" onClick={() => setOpen(open === m.id ? null : m.id)} aria-expanded={open === m.id}>
                <span>
                  <span className="font-medium">{m.subject}</span>
                  <span className="ml-2 text-sm text-ink-2">to {m.to}</span>
                </span>
                <span className="flex items-center gap-2">
                  {m.status === "sent" ? <Tag tone="good" icon="check">Sent</Tag> : m.status === "failed" ? <Tag tone="bad" icon="alert">Failed</Tag> : m.status === "queued" ? <Tag tone="info" icon="clock">Sending</Tag> : <Tag tone="neutral" icon="clock">In outbox</Tag>}
                  <span className="text-xs text-muted">{dateTimeLabel(m.created_at)}</span>
                </span>
              </button>
              {open === m.id && (
                <pre className="mt-2 whitespace-pre-wrap rounded-md bg-paper p-3 font-sans text-sm text-ink-2">{m.body}{m.error && `\n\nError: ${m.error}`}</pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
