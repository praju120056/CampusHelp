"use client";
// A1/A2: the day's log, pre-filled from the timetable. Usually one tap: "Confirm day".
import { useCallback, useEffect, useState } from "react";
import { Icon, Loading, Notice, Tag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { dayLabel, LOG_TYPES, shiftISO, timeLabel, todayISO } from "@/lib/format";

type Entry = {
  id: number | null;
  type: string;
  topic: string;
  units: number;
  period: number | null;
  section: string | null;
  subject: string | null;
  source_slot_id: number | null;
  tag: string | null;
  saved: boolean;
  locked: boolean;
  when: string;
  key?: string;
};
type Day = {
  date: string;
  submitted: boolean;
  submitted_at: string | null;
  entries: Entry[];
  weights: Record<string, number>;
};

let counter = 0;
const withKeys = (entries: Entry[]) => entries.map((e) => ({ ...e, key: e.key ?? `e${++counter}` }));
const UNIT_LABEL: Record<string, string> = { meeting: "h", duty: "slot", theory: "period", lab: "period", substitution: "period", adjusted: "period" };

export default function LogPage() {
  const today = todayISO();
  const [date, setDate] = useState(today);
  const [day, setDay] = useState<Day | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [addType, setAddType] = useState("meeting");

  const load = useCallback((d: string) => {
    api<Day>(`/logs/prefill?date=${d}`)
      .then((res) => {
        setDay(res);
        setEntries(withKeys(res.entries));
        setError("");
      })
      .catch((e) => setError(errorText(e)));
  }, []);
  useEffect(() => load(date), [date, load]);

  const update = (key: string, patch: Partial<Entry>) =>
    setEntries((list) => list.map((e) => (e.key === key ? { ...e, ...patch } : e)));
  const remove = (key: string) => setEntries((list) => list.filter((e) => e.key !== key));
  const add = () =>
    setEntries((list) => [
      ...list,
      { id: null, type: addType, topic: "", units: 1, period: null, section: null, subject: null, source_slot_id: null,
        tag: null, saved: false, locked: false, when: "", key: `e${++counter}` },
    ]);

  async function submit() {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const res = await api<Day>("/logs", {
        body: {
          date,
          entries: entries.map((e) => ({
            id: e.id, type: e.type, topic: e.topic, units: e.units, period: e.period, section: e.section,
            subject: e.subject, source_slot_id: e.source_slot_id,
          })),
        },
      });
      setDay(res);
      setEntries(withKeys(res.entries));
      setSaved("Saved. Your HOD can see it now.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const load_units = day ? entries.reduce((sum, e) => sum + e.units * (day.weights[e.type] ?? 0), 0) : 0;

  return (
    <div className="mx-auto max-w-2xl pb-28">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <div className="eyebrow">Work log</div>
          <h1 className="text-2xl font-semibold tracking-tight">{date === today ? "Today" : dayLabel(date)}</h1>
          {date === today && <div className="text-sm text-ink-2">{dayLabel(date)}</div>}
        </div>
        <div className="flex gap-1">
          <button className="btn btn-sm" aria-label="Previous day" onClick={() => setDate(shiftISO(date, -1))}>
            <Icon name="left" />
          </button>
          <button className="btn btn-sm" aria-label="Next day" disabled={date >= today} onClick={() => setDate(shiftISO(date, 1))}>
            <Icon name="right" />
          </button>
        </div>
      </div>

      {error && <div className="mb-3"><Notice tone="bad">{error}</Notice></div>}
      {saved && <div className="mb-3"><Notice tone="good">{saved}</Notice></div>}
      {day?.submitted && !saved && (
        <div className="mb-3">
          <Notice tone="good">Submitted at {timeLabel(day.submitted_at)}. You can still edit and save again.</Notice>
        </div>
      )}
      {!day ? (
        <Loading />
      ) : (
        <>
          {!day.submitted && entries.length > 0 && (
            <p className="mb-3 text-sm text-ink-2">Filled in from your timetable. Add topics if you like, then confirm.</p>
          )}
          {entries.length === 0 && <p className="py-4 text-sm text-muted">No classes or duties on this day. Add anything you did below.</p>}
          <ul className="divide-y divide-rule border-y border-rule">
            {entries.map((e) => (
              <li key={e.key} className="py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Tag tone={e.type === "substitution" ? "accent" : e.type === "adjusted" ? "neutral" : "info"}>
                        {LOG_TYPES[e.type]}
                      </Tag>
                      {e.tag === "adjustment" && <Tag tone="neutral" icon="swap">Adjustment</Tag>}
                      {e.when && <span className="text-xs text-muted">{e.when}</span>}
                    </div>
                    {(e.section || e.subject) && (
                      <div className="mt-1 font-medium">{[e.section, e.subject].filter(Boolean).join(" · ")}</div>
                    )}
                  </div>
                  {!e.locked && (
                    <button className="btn btn-ghost btn-sm" aria-label="Remove entry" onClick={() => remove(e.key!)}>
                      <Icon name="x" />
                    </button>
                  )}
                </div>
                <div className="mt-2 flex gap-2">
                  {!e.locked && !e.source_slot_id && (
                    <select className="field w-36" aria-label="Type" value={e.type} onChange={(ev) => update(e.key!, { type: ev.target.value })}>
                      {Object.entries(LOG_TYPES).filter(([k]) => k !== "adjusted").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  )}
                  <input className="field" placeholder={e.type === "meeting" || e.type === "duty" ? "What was it?" : "Topic covered (optional)"}
                    value={e.topic} maxLength={200} onChange={(ev) => update(e.key!, { topic: ev.target.value })} />
                  {!e.locked && !e.source_slot_id && (
                    <div className="flex items-center gap-1">
                      <input className="field w-16 text-center" type="number" min={0.5} max={12} step={0.5} aria-label="Units"
                        value={e.units} onChange={(ev) => update(e.key!, { units: Number(ev.target.value) || 1 })} />
                      <span className="text-xs text-muted">{UNIT_LABEL[e.type]}</span>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <select className="field w-40" aria-label="Type of entry to add" value={addType} onChange={(e) => setAddType(e.target.value)}>
              <option value="meeting">Meeting / committee</option>
              <option value="duty">Duty</option>
              <option value="theory">Extra class</option>
              <option value="lab">Extra lab</option>
            </select>
            <button className="btn" onClick={add}><Icon name="plus" /> Add entry</button>
          </div>
          <p className="mt-4 text-xs text-muted">
            Weighted load for this day: <strong className="num text-ink">{load_units.toFixed(1)}</strong> (theory 1 per period,
            lab {day.weights.lab}, duty {day.weights.duty}, meeting {day.weights.meeting} per hour).
          </p>
        </>
      )}

      <div className="fixed inset-x-0 bottom-0 border-t border-rule bg-surface/95 px-4 py-3 backdrop-blur">
        <button className="btn btn-primary mx-auto flex w-full max-w-2xl" disabled={busy || !day} onClick={submit}>
          <Icon name="check" />
          {busy ? "Saving…" : day?.submitted ? "Save changes" : `Confirm day (${entries.length} ${entries.length === 1 ? "entry" : "entries"})`}
        </button>
      </div>
    </div>
  );
}
