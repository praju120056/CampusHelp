"use client";
// A4, A5, A8–A11: HOD monitor. Updates live when anyone saves a log or an adjustment is accepted.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { LoadBars, LoadSeriesChart, TrendChart, type LoadRow, type Series, type TrendPoint } from "@/components/charts";
import { FlagTag, Icon, LiveDot, Loading, Notice, PageHeader, Tag } from "@/components/ui";
import { api, download, errorText } from "@/lib/api";
import { dayLabel, timeLabel } from "@/lib/format";
import { useLive } from "@/lib/live";

type Today = {
  date: string;
  logged: number;
  faculty: { faculty_id: number; name: string; logged: boolean; submitted_at: string | null; entries: number; classes_today: number }[];
  not_logged: { faculty_id: number; name: string }[];
};
type Fairness = {
  window: { start: string; end: string; days: number };
  score: number;
  gini: number;
  mean: number;
  sd: number;
  upper: number;
  lower: number;
  faculty: (LoadRow & { faculty_id: number; designation: string; weeks: { start: string; end: string; load: number; flag: string }[] })[];
  trend: TrendPoint[];
  counts: { overloaded: number; underused: number; burnout: number };
  burnout_weeks: number;
};

export default function HodDashboard() {
  const [today, setToday] = useState<Today | null>(null);
  const [fair, setFair] = useState<Fairness | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [granularity, setGranularity] = useState<"week" | "month">("week");
  const [focus, setFocus] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [changed, setChanged] = useState<string | null>(null);
  const lastScore = useRef<number | null>(null);

  const loadCore = useCallback(() => {
    Promise.all([api<Today>("/analytics/today"), api<Fairness>("/analytics/fairness")])
      .then(([t, f]) => {
        setToday(t);
        if (lastScore.current !== null && lastScore.current !== f.score) {
          setChanged(`Fairness score moved ${lastScore.current} → ${f.score}`);
        }
        lastScore.current = f.score;
        setFair(f);
        setError("");
      })
      .catch((e) => setError(errorText(e)));
  }, []);
  const loadSeries = useCallback(() => {
    api<Series>(`/analytics/load?granularity=${granularity}&count=${granularity === "week" ? 6 : 3}`)
      .then(setSeries)
      .catch(() => {});
  }, [granularity]);

  useEffect(loadCore, [loadCore]);
  useEffect(loadSeries, [loadSeries]);
  const live = useLive(["logs", "adjustments"], (type) => {
    if (type === "log.saved") {
      loadCore();
      loadSeries();
    }
  });

  async function remind() {
    try {
      const r = await api<{ reminded: number }>("/analytics/remind", { method: "POST" });
      setNote(`Reminder sent to ${r.reminded} faculty (in-app and email).`);
    } catch (e) {
      setError(errorText(e));
    }
  }

  const range = fair ? `start=${fair.window.start}&end=${fair.window.end}` : "";

  return (
    <>
      <PageHeader
        eyebrow="Module A · HOD monitor"
        title="Department dashboard"
        actions={
          <>
            <LiveDot state={live} />
            <button className="btn btn-sm" disabled={!fair} onClick={() => download(`/exports/logs.xlsx?${range}`, "work-logs.xlsx").catch((e) => setError(errorText(e)))}>
              <Icon name="download" /> Logs (Excel)
            </button>
            <button className="btn btn-sm" disabled={!fair} onClick={() => download(`/exports/report.xlsx?${range}`, "naac-nba-report.xlsx").catch((e) => setError(errorText(e)))}>
              <Icon name="download" /> NAAC/NBA report (Excel)
            </button>
            <Link className="btn btn-sm" href={`/report?${range}`}><Icon name="print" /> Report (PDF)</Link>
          </>
        }
      >
        {fair && `Fairness window ${dayLabel(fair.window.start)} – ${dayLabel(fair.window.end)}`}
      </PageHeader>

      {error && <div className="mb-4"><Notice tone="bad">{error}</Notice></div>}
      {note && <div className="mb-4"><Notice tone="good">{note}</Notice></div>}
      {changed && <div className="mb-4" aria-live="polite"><Notice tone="accent">{changed}</Notice></div>}

      {!today || !fair ? (
        <Loading />
      ) : (
        <div className="space-y-10">
          {/* Today */}
          <section className="grid gap-6 border-y border-rule py-5 lg:grid-cols-[260px_1fr]">
            <div>
              <div className="eyebrow">Today&apos;s log</div>
              <div className="mt-1 text-5xl font-semibold leading-none">
                {today.logged}<span className="text-2xl text-muted"> / {today.faculty.length}</span>
              </div>
              <div className="mt-1 text-sm text-ink-2">faculty have logged {dayLabel(today.date)}</div>
              {today.not_logged.length > 0 && (
                <button className="btn btn-sm mt-3" onClick={remind}><Icon name="bell" /> Remind the {today.not_logged.length} who haven&apos;t</button>
              )}
            </div>
            <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3 xl:grid-cols-4">
              {today.faculty.map((f) => (
                <li key={f.faculty_id} className="flex items-center justify-between gap-2 border-b border-rule py-1.5">
                  <span>{f.name}</span>
                  {f.logged ? (
                    <Tag tone="good" icon="check" title={`Submitted ${timeLabel(f.submitted_at)}`}>Logged {timeLabel(f.submitted_at)}</Tag>
                  ) : (
                    <Tag tone="neutral" icon="clock">Not yet</Tag>
                  )}
                </li>
              ))}
            </ul>
          </section>

          {/* Fairness */}
          <section className="grid gap-8 lg:grid-cols-[260px_1fr]">
            <div>
              <div className="eyebrow">Fairness score</div>
              <div className="mt-1 text-6xl font-semibold leading-none">{fair.score}</div>
              <div className="mt-1 text-sm text-ink-2">out of 100 (higher is fairer)</div>
              <div className="mt-1 text-xs text-muted">Gini index {fair.gini} · mean {fair.mean} · SD {fair.sd}</div>
              <dl className="mt-5 space-y-2 text-sm">
                <div className="flex items-center justify-between"><dt><FlagTag flag="overloaded" /></dt><dd className="num font-semibold">{fair.counts.overloaded}</dd></div>
                <div className="flex items-center justify-between"><dt><FlagTag flag="underused" /></dt><dd className="num font-semibold">{fair.counts.underused}</dd></div>
                <div className="flex items-center justify-between"><dt><Tag tone="bad" icon="flame">Burnout watch</Tag></dt><dd className="num font-semibold">{fair.counts.burnout}</dd></div>
              </dl>
              <div className="mt-6"><TrendChart points={fair.trend} /></div>
            </div>
            <LoadBars rows={fair.faculty} mean={fair.mean} lower={fair.lower} upper={fair.upper} />
          </section>

          {/* Rolling 4 weeks */}
          <section>
            <h2 className="heading">Rolling 4 weeks</h2>
            <p className="mb-3 text-xs text-ink-2">
              Burnout watch: overloaded {fair.burnout_weeks} weeks in a row. Each column is a 7-day window.
            </p>
            <div className="overflow-x-auto">
              <table className="ruled-table min-w-[640px]">
                <thead>
                  <tr>
                    <th>Faculty</th>
                    {fair.faculty[0]?.weeks.map((w) => <th key={w.end}>To {dayLabel(w.end)}</th>)}
                    <th>Watch</th>
                  </tr>
                </thead>
                <tbody>
                  {fair.faculty.map((f) => (
                    <tr key={f.faculty_id}>
                      <td className="font-medium">{f.name}</td>
                      {f.weeks.map((w) => (
                        <td key={w.end}>
                          <span className="num mr-2">{w.load}</span>
                          <FlagTag flag={w.flag} />
                        </td>
                      ))}
                      <td>{f.burnout ? <Tag tone="bad" icon="flame">Burnout watch</Tag> : <span className="text-muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Weekly / monthly */}
          <section>
            {series ? (
              <LoadSeriesChart
                data={series}
                focus={focus}
                actions={
                  <>
                    <div className="flex gap-1" role="group" aria-label="Period">
                      <button className="chip" aria-pressed={granularity === "week"} onClick={() => setGranularity("week")}>Weekly</button>
                      <button className="chip" aria-pressed={granularity === "month"} onClick={() => setGranularity("month")}>Monthly</button>
                    </div>
                    <select className="field w-40" aria-label="Compare faculty member" value={focus ?? ""}
                      onChange={(e) => setFocus(e.target.value ? Number(e.target.value) : null)}>
                      <option value="">Compare…</option>
                      {series.faculty.map((f) => <option key={f.faculty_id} value={f.faculty_id}>{f.name}</option>)}
                    </select>
                  </>
                }
              />
            ) : (
              <Loading />
            )}
          </section>
        </div>
      )}
    </>
  );
}
