"use client";
// C1, C3–C7 for faculty: ask for cover, pick a suggestion, answer requests from colleagues.
import { useCallback, useEffect, useState } from "react";
import { SuggestionList, type Candidate } from "@/components/suggestions";
import { Empty, Icon, LiveDot, Loading, Notice, PageHeader, StatusTag, Tag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { dayLabel, todayISO } from "@/lib/format";
import { useLive } from "@/lib/live";

type Unit = {
  periods: number[];
  label: string;
  section: string;
  subject: string;
  type: string;
  kind: string;
  request_id: number | null;
  request_status: string | null;
};
type MyDay = { date: string; day: string; units: Unit[] };
type Adjustment = {
  id: number;
  date: string;
  periods_label: string;
  section: string;
  subject: string;
  reason: string;
  status: string;
  overridden: boolean;
  chosen: Candidate | null;
  candidates: Candidate[];
};
type Incoming = {
  candidate_id: number;
  adjustment_id: number;
  requester: string;
  date: string;
  periods_label: string;
  section: string;
  subject: string;
  reason: string;
  kind: string;
  swap_label: string | null;
  swap_subject: string | null;
  state: string;
};

const REASONS = ["FDP / workshop", "Medical", "Exam duty", "Official work"];

export default function AdjustPage() {
  const [date, setDate] = useState(todayISO());
  const [day, setDay] = useState<MyDay | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [reason, setReason] = useState("");
  const [mine, setMine] = useState<{ requested: Adjustment[]; incoming: Incoming[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadDay = useCallback((d: string) => {
    api<MyDay>(`/timetable/me?date=${d}`).then(setDay).catch((e) => setError(errorText(e)));
  }, []);
  const loadMine = useCallback(() => {
    api<{ requested: Adjustment[]; incoming: Incoming[] }>("/adjustments/mine").then(setMine).catch(() => {});
  }, []);
  useEffect(() => loadDay(date), [date, loadDay]);
  useEffect(loadMine, [loadMine]);
  const live = useLive(["adjustments"], () => {
    loadMine();
    loadDay(date);
  });

  const toggle = (periods: number[]) =>
    setPicked((p) => (periods.every((x) => p.includes(x)) ? p.filter((x) => !periods.includes(x)) : [...p, ...periods]));

  async function findCover() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api<Adjustment[]>("/adjustments", { body: { date, periods: picked, reason } });
      setPicked([]);
      setMessage("Here are the best options. Tap Ask on one; they get an email and an in-app request.");
      loadMine();
      loadDay(date);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function act(path: string, body?: unknown, ok?: string) {
    setBusy(true);
    setError("");
    try {
      await api(path, { method: "POST", body: body ?? {} });
      if (ok) setMessage(ok);
      loadMine();
      loadDay(date);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const pendingIncoming = mine?.incoming.filter((i) => i.state === "requested") ?? [];
  const active = mine?.requested.filter((a) => a.status !== "cancelled") ?? [];

  return (
    <>
      <PageHeader eyebrow="Module C · Class adjustment" title="Class cover" actions={<LiveDot state={live} />}>
        Away for a class? EduCrew finds a colleague who is free and never double-books anyone.
      </PageHeader>

      {error && <div className="mb-4"><Notice tone="bad">{error}</Notice></div>}
      {message && <div className="mb-4"><Notice tone="good">{message}</Notice></div>}

      {pendingIncoming.length > 0 && (
        <section className="mb-8 rounded-md border-2 border-accent/40 bg-accent-soft/40 p-4">
          <h2 className="heading mb-3">Colleagues asking you</h2>
          <ul className="space-y-4">
            {pendingIncoming.map((r) => (
              <li key={r.candidate_id} className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-medium">
                    {r.requester}: {r.section} {r.subject}
                  </div>
                  <div className="text-sm text-ink-2">
                    {dayLabel(r.date)}, {r.periods_label}
                    {r.kind === "swap" && ` · swap: they take your ${r.swap_subject}, ${r.swap_label}`}
                    {r.reason && ` · ${r.reason}`}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="btn" disabled={busy}
                    onClick={() => act(`/adjustments/${r.adjustment_id}/respond`, { action: "decline" }, "Declined. The next colleague has been asked.")}>
                    <Icon name="x" /> Decline
                  </button>
                  <button className="btn btn-primary" disabled={busy}
                    onClick={() => act(`/adjustments/${r.adjustment_id}/respond`, { action: "accept" }, "Accepted. It is in your timetable and work log.")}>
                    <Icon name="check" /> Accept
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,420px)_1fr]">
        <section>
          <h2 className="heading mb-3">Ask for cover</h2>
          <label className="label" htmlFor="date">Date</label>
          <input id="date" type="date" className="field w-48" min={todayISO()} value={date}
            onChange={(e) => { setDate(e.target.value); setPicked([]); }} />
          <div className="mt-4">
            <div className="label">Your classes on {day ? day.day : "…"}</div>
            {!day ? (
              <Loading />
            ) : day.units.length === 0 ? (
              <p className="text-sm text-muted">No classes that day.</p>
            ) : (
              <ul className="divide-y divide-rule border-y border-rule">
                {day.units.map((u) => {
                  const taken = u.request_id !== null;
                  const checked = u.periods.every((p) => picked.includes(p));
                  return (
                    <li key={u.periods.join("-")}>
                      <label className={`flex min-h-12 items-center gap-3 py-2 ${taken ? "opacity-70" : "cursor-pointer"}`}>
                        <input type="checkbox" className="h-5 w-5" disabled={taken} checked={checked} onChange={() => toggle(u.periods)} />
                        <span className="flex-1">
                          <span className="font-medium">{u.section} · {u.subject}</span>
                          <span className="block text-xs text-ink-2">
                            {u.label}{u.type === "lab" && " · lab block, covered as one"}
                          </span>
                        </span>
                        {taken && <StatusTag status={u.request_status ?? "open"} />}
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div className="mt-4">
            <label className="label" htmlFor="reason">Reason</label>
            <div className="mb-2 flex flex-wrap gap-2">
              {REASONS.map((r) => (
                <button key={r} type="button" className="chip" aria-pressed={reason === r} onClick={() => setReason(r)}>{r}</button>
              ))}
            </div>
            <input id="reason" className="field" placeholder="Or type a reason" value={reason} maxLength={300}
              onChange={(e) => setReason(e.target.value)} />
          </div>
          <button className="btn btn-primary mt-4 w-full" disabled={busy || picked.length === 0} onClick={findCover}>
            {busy ? "Finding…" : "Find cover"}
          </button>
        </section>

        <section>
          <h2 className="heading mb-3">My requests</h2>
          {!mine ? (
            <Loading />
          ) : active.length === 0 ? (
            <Empty>No requests yet.</Empty>
          ) : (
            <ul className="space-y-8">
              {active.map((a) => (
                <li key={a.id}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="font-semibold">{a.section} · {a.subject}</div>
                      <div className="text-sm text-ink-2">{dayLabel(a.date)}, {a.periods_label}{a.reason && ` · ${a.reason}`}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusTag status={a.status} />
                      {a.overridden && <Tag tone="neutral">Set by HOD</Tag>}
                      {a.date >= todayISO() && (
                        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act(`/adjustments/${a.id}/cancel`, undefined, "Request cancelled.")}>
                          Cancel
                        </button>
                      )}
                    </div>
                  </div>
                  {a.status === "accepted" && a.chosen && (
                    <p className="mt-2 text-sm">
                      <Icon name="check" size={14} className="mr-1 inline text-good-ink" />
                      <strong>{a.chosen.name}</strong> {a.chosen.kind === "swap" ? `swaps with you (you take their ${a.chosen.swap_subject}, ${a.chosen.swap_label})` : "takes this class"}.
                    </p>
                  )}
                  {a.status === "pending" && a.chosen && (
                    <p className="mt-2 text-sm text-ink-2">Waiting for <strong className="text-ink">{a.chosen.name}</strong>. If they decline, the next person is asked automatically.</p>
                  )}
                  {a.status === "exhausted" && <p className="mt-2 text-sm text-bad-ink">Everyone declined or is busy. The HOD has been told.</p>}
                  {a.status !== "accepted" && (
                    <div className="mt-3">
                      <SuggestionList
                        candidates={a.candidates}
                        canChoose={a.status === "open" || a.status === "exhausted"}
                        busy={busy}
                        onChoose={(c) => act(`/adjustments/${a.id}/choose`, { candidate_id: c.id }, `Asked ${c.name}.`)}
                      />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
