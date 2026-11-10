"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Empty, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTimeLabel } from "@/lib/format";
import { useInterval } from "@/lib/live";

type Note = { id: number; subject: string; body: string; link: string | null; read: boolean; created_at: string };

export default function InboxPage() {
  const [items, setItems] = useState<Note[] | null>(null);
  const load = useCallback(() => {
    api<{ items: Note[] }>("/notifications").then((r) => setItems(r.items)).catch(() => {});
  }, []);
  useEffect(load, [load]);
  useInterval(load, 15000);

  async function readAll() {
    await api("/notifications/read-all", { method: "POST" });
    load();
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Inbox" actions={<button className="btn btn-sm" onClick={readAll}>Mark all read</button>}>
        In-app notifications. The same messages also go out by email when email is set up.
      </PageHeader>
      {!items ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty>Nothing yet.</Empty>
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {items.map((n) => (
            <li key={n.id} className="py-3">
              <div className="flex items-baseline justify-between gap-3">
                <div className={`font-medium ${n.read ? "text-ink-2" : ""}`}>
                  {!n.read && <span className="mr-2 inline-block h-2 w-2 rounded-full bg-accent align-middle" aria-label="Unread" />}
                  {n.link && !n.link.startsWith("/respond/") ? <Link href={n.link} className="hover:underline">{n.subject}</Link> : n.subject}
                </div>
                <span className="whitespace-nowrap text-xs text-muted">{dateTimeLabel(n.created_at)}</span>
              </div>
              <p className="mt-1 whitespace-pre-line text-sm text-ink-2">{n.body.split("\n\nAccept:")[0]}</p>
              {n.link?.startsWith("/respond/") && (
                <Link href="/adjust" className="mt-1 inline-block text-sm font-medium text-accent hover:underline">Answer on the Class cover page</Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
