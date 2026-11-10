"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useCurrentUser } from "@/components/shell";
import { Empty, Icon, LiveDot, Loading, Notice, PageHeader, PriorityTag, StatusTag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { CATEGORIES, label, relative, STATUSES } from "@/lib/format";
import { useLive } from "@/lib/live";

type Row = {
  ref: string;
  status: string;
  status_label: string;
  category: string;
  priority: string;
  summary: string;
  location: { code: string; room_name: string; floor: number };
  assigned_to: string | null;
  worker: string | null;
  report_count: number;
  deadline_at: string;
  created_at: string;
  overdue: boolean;
  escalated: boolean;
};

export default function TicketsPage() {
  const user = useCurrentUser();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [scope, setScope] = useState(user.role === "incharge" ? "mine" : "all");
  const [openOnly, setOpenOnly] = useState(true);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    const qs = new URLSearchParams({ scope, open_only: String(openOnly) });
    if (category) qs.set("category", category);
    if (status) qs.set("status", status);
    api<Row[]>(`/tickets?${qs}`)
      .then((r) => {
        setRows(r);
        setError("");
      })
      .catch((e) => setError(errorText(e)));
  }, [scope, openOnly, category, status]);

  useEffect(load, [load]);
  const live = useLive(["tickets"], () => load());

  return (
    <>
      <PageHeader
        eyebrow="Module B · Maintenance"
        title={user.role === "incharge" ? "My tickets" : "All tickets"}
        actions={<LiveDot state={live} />}
      >
        Newest first. Overdue tickets are escalated to the Estate Officer automatically.
      </PageHeader>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex gap-1" role="group" aria-label="Scope">
          {user.role === "incharge" && (
            <button className="chip" aria-pressed={scope === "mine"} onClick={() => setScope("mine")}>Mine</button>
          )}
          <button className="chip" aria-pressed={scope === "all"} onClick={() => setScope("all")}>All</button>
          <button className="chip" aria-pressed={scope === "escalated"} onClick={() => setScope("escalated")}>Escalated</button>
        </div>
        <select className="field w-40" aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
        <select className="field w-40" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} className="h-4 w-4" />
          Open only
        </label>
      </div>

      {error && <Notice tone="bad">{error}</Notice>}
      {!rows ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty>No tickets here.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="ruled-table min-w-[720px]">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Problem</th>
                <th>Where</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Due</th>
                <th>With</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.ref} className={t.status === "new" ? "bg-accent-soft/40" : ""}>
                  <td className="mono whitespace-nowrap">
                    <Link href={`/tickets/${t.ref}`} className="font-semibold text-accent hover:underline">{t.ref}</Link>
                  </td>
                  <td>
                    <Link href={`/tickets/${t.ref}`} className="hover:underline">{t.summary}</Link>
                    <div className="text-xs text-muted">
                      {label(CATEGORIES, t.category)}
                      {t.report_count > 1 && ` · ${t.report_count} reports`}
                    </div>
                  </td>
                  <td>
                    {t.location.room_name}
                    <div className="mono text-xs text-muted">{t.location.code}</div>
                  </td>
                  <td><PriorityTag priority={t.priority} /></td>
                  <td><StatusTag status={t.status} label={t.status_label} /></td>
                  <td className="whitespace-nowrap">
                    {t.status === "resolved" || t.status === "rejected" ? (
                      <span className="text-muted">—</span>
                    ) : t.overdue ? (
                      <span className="inline-flex items-center gap-1 font-semibold text-bad-ink">
                        <Icon name="alert" size={14} /> Overdue{t.escalated ? ", escalated" : ""}
                      </span>
                    ) : (
                      relative(t.deadline_at)
                    )}
                  </td>
                  <td className="text-ink-2">{t.worker ?? t.assigned_to ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
