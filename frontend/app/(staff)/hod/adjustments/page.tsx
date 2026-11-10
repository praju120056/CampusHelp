"use client";
// C7: the HOD sees every adjustment and can override (assign someone directly) or cancel.
import { useCallback, useEffect, useState } from "react";
import type { Candidate } from "@/components/suggestions";
import { Empty, LiveDot, Loading, Notice, PageHeader, StatusTag, Tag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { dayLabel, todayISO } from "@/lib/format";
import { useLive } from "@/lib/live";

type Adjustment = {
  id: number;
  requester: string;
  date: string;
  periods_label: string;
  section: string;
  subject: string;
  reason: string;
  status: string;
  overridden: boolean;
  note: string | null;
  chosen: Candidate | null;
  candidates: Candidate[];
};
type FreeRow = { faculty_id: number; name: string; free: boolean; busy_reason: string; subject_match: boolean };

export default function HodAdjustments() {
  const [rows, setRows] = useState<Adjustment[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [free, setFree] = useState<FreeRow[]>([]);
  const [pick, setPick] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<"upcoming" | "all">("upcoming");

  const load = useCallback(() => {
    api<Adjustment[]>("/adjustments").then(setRows).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);
  const live = useLive(["adjustments"], () => load());

  async function openOverride(id: number) {
    setOpen(id);
    setPick("");
    setNote("");
    try {
      setFree(await api<FreeRow[]>(`/adjustments/${id}/free-faculty`));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function post(path: string, body?: unknown) {
    setBusy(true);
    setError("");
    try {
      await api(path, { method: "POST", body: body ?? {} });
      setOpen(null);
      load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const today = todayISO();
  const shown = (rows ?? []).filter((a) => filter === "all" || a.date >= today);

  return (
    <>
      <PageHeader eyebrow="Module C · HOD" title="Class adjustments" actions={<LiveDot state={live} />}>
        Every request in the department. Override assigns someone directly (still clash-checked).
      </PageHeader>
      <div className="mb-4 flex gap-1">
        <button className="chip" aria-pressed={filter === "upcoming"} onClick={() => setFilter("upcoming")}>Today and later</button>
        <button className="chip" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
      </div>
      {error && <div className="mb-4"><Notice tone="bad">{error}</Notice></div>}
      {!rows ? (
        <Loading />
      ) : shown.length === 0 ? (
        <Empty>No adjustments.</Empty>
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {shown.map((a) => (
            <li key={a.id} className="py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{a.requester}: {a.section} · {a.subject}</div>
                  <div className="text-sm text-ink-2">{dayLabel(a.date)}, {a.periods_label}{a.reason && ` · ${a.reason}`}</div>
                  {a.chosen && (
                    <div className="mt-1 text-sm">
                      {a.status === "accepted" ? "Covered by " : "Waiting for "}
                      <strong>{a.chosen.name}</strong> ({a.chosen.kind === "swap" ? "swap" : "substitute"})
                    </div>
                  )}
                  {a.note && <div className="mt-1 text-xs text-muted">HOD note: {a.note}</div>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusTag status={a.status} />
                  {a.overridden && <Tag tone="neutral">Set by HOD</Tag>}
                  {a.status !== "cancelled" && (
                    <>
                      <button className="btn btn-sm" disabled={busy} onClick={() => openOverride(a.id)}>Override</button>
                      <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => post(`/adjustments/${a.id}/cancel`)}>Cancel</button>
                    </>
                  )}
                </div>
              </div>
              {open === a.id && (
                <div className="mt-3 rounded-md border border-rule-strong bg-surface p-3">
                  <label className="label" htmlFor={`pick-${a.id}`}>Assign directly</label>
                  <select id={`pick-${a.id}`} className="field" value={pick} onChange={(e) => setPick(e.target.value)}>
                    <option value="">Choose a faculty member…</option>
                    {free.map((f) => (
                      <option key={f.faculty_id} value={f.faculty_id} disabled={!f.free}>
                        {f.name} — {f.free ? (f.subject_match ? "free, teaches this subject" : "free") : `busy: ${f.busy_reason}`}
                      </option>
                    ))}
                  </select>
                  <input className="field mt-2" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                  <div className="mt-2 flex gap-2">
                    <button className="btn btn-primary btn-sm" disabled={busy || !pick}
                      onClick={() => post(`/adjustments/${a.id}/override`, { faculty_id: Number(pick), note })}>
                      Assign
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setOpen(null)}>Close</button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
