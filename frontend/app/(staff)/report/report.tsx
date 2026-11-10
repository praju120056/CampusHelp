"use client";
// A11: NAAC/NBA report. Print → "Save as PDF" gives the PDF; the Excel version is one click away.
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, Loading, Notice } from "@/components/ui";
import { api, download, errorText } from "@/lib/api";
import { dayLabel, shiftISO, todayISO } from "@/lib/format";

type Row = { name: string; designation: string; theory: number; lab: number; duty: number; meeting: number; substitution: number; load: number; share: number; flag: string };
type Data = {
  range: { start: string; end: string };
  summary: Row[];
  totals: Record<string, number>;
  fairness: { score: number; gini: number; mean: number; sd: number };
  trend: { start: string; end: string; score: number | null }[];
  adjustments: { date: string; requester: string; section: string; subject: string; periods: string; kind: string; taken_by: string; status: string; reason: string }[];
  adjustment_counts: { total: number; accepted: number; swaps: number; substitutions: number };
  duties: { date: string; faculty: string; period: number; kind: string }[];
  weights: Record<string, number>;
};

export default function Report() {
  const params = useSearchParams();
  const router = useRouter();
  const end = params.get("end") ?? todayISO();
  const start = params.get("start") ?? shiftISO(end, -27);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Data>(`/exports/report.json?start=${start}&end=${end}`).then(setData).catch((e) => setError(errorText(e)));
  }, [start, end]);

  const setRange = (s: string, e: string) => router.replace(`/report?start=${s}&end=${e}`);

  return (
    <div className="mx-auto max-w-5xl">
      <div className="no-print mb-6 flex flex-wrap items-end gap-3">
        <div>
          <label className="label" htmlFor="from">From</label>
          <input id="from" type="date" className="field" value={start} onChange={(e) => setRange(e.target.value, end)} />
        </div>
        <div>
          <label className="label" htmlFor="to">To</label>
          <input id="to" type="date" className="field" value={end} onChange={(e) => setRange(start, e.target.value)} />
        </div>
        <button className="btn" onClick={() => download(`/exports/report.xlsx?start=${start}&end=${end}`, "naac-nba-report.xlsx")}>
          <Icon name="download" /> Excel
        </button>
        <button className="btn btn-primary" onClick={() => window.print()}><Icon name="print" /> Print / save as PDF</button>
      </div>
      {error && <Notice tone="bad">{error}</Notice>}
      {!data ? (
        <Loading />
      ) : (
        <article className="space-y-8 bg-surface p-6 print:p-0">
          <header className="border-b-2 border-ink pb-3">
            <div className="eyebrow">Department of CSE (AI &amp; ML)</div>
            <h1 className="text-2xl font-semibold">Faculty workload, duties and class adjustments</h1>
            <p className="text-sm text-ink-2">{dayLabel(data.range.start)} – {dayLabel(data.range.end)} · prepared for NAAC / NBA documentation</p>
          </header>

          <section className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <div><div className="text-xs text-ink-2">Fairness score</div><div className="text-3xl font-semibold">{data.fairness.score}</div><div className="text-xs text-muted">Gini {data.fairness.gini}</div></div>
            <div><div className="text-xs text-ink-2">Mean weighted load</div><div className="text-3xl font-semibold">{data.fairness.mean}</div><div className="text-xs text-muted">SD {data.fairness.sd}</div></div>
            <div><div className="text-xs text-ink-2">Class adjustments</div><div className="text-3xl font-semibold">{data.adjustment_counts.total}</div><div className="text-xs text-muted">{data.adjustment_counts.accepted} covered</div></div>
            <div><div className="text-xs text-ink-2">Duty slots</div><div className="text-3xl font-semibold">{data.totals.duty}</div></div>
          </section>

          <section>
            <h2 className="heading mb-2">1. Load summary</h2>
            <table className="ruled-table">
              <thead><tr><th>Faculty</th><th>Designation</th><th>Theory</th><th>Lab</th><th>Duty</th><th>Meetings (h)</th><th>Substitutions</th><th>Weighted load</th><th>Share</th><th>Flag</th></tr></thead>
              <tbody>
                {data.summary.map((r) => (
                  <tr key={r.name}>
                    <td>{r.name}</td><td>{r.designation}</td><td>{r.theory}</td><td>{r.lab}</td><td>{r.duty}</td><td>{r.meeting}</td>
                    <td>{r.substitution}</td><td className="font-semibold">{r.load}</td><td>{r.share}%</td>
                    <td>{r.flag === "overloaded" ? "▲ Overloaded" : r.flag === "underused" ? "▼ Underused" : "—"}</td>
                  </tr>
                ))}
                <tr className="font-semibold">
                  <td>Total</td><td></td><td>{data.totals.theory}</td><td>{data.totals.lab}</td><td>{data.totals.duty}</td><td>{data.totals.meeting}</td>
                  <td>{data.totals.substitution}</td><td>{data.totals.load}</td><td>100%</td><td></td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">Weights: {Object.entries(data.weights).map(([k, v]) => `${k} ${v}`).join(", ")}. Flags: above mean + 1 SD overloaded, below mean − 1 SD underused.</p>
          </section>

          <section>
            <h2 className="heading mb-2">2. Class adjustments</h2>
            <p className="mb-2 text-sm text-ink-2">{data.adjustment_counts.swaps} swaps · {data.adjustment_counts.substitutions} substitutions</p>
            {data.adjustments.length === 0 ? <p className="text-sm text-muted">None in this period.</p> : (
              <table className="ruled-table">
                <thead><tr><th>Date</th><th>Requested by</th><th>Class</th><th>Periods</th><th>Covered by</th><th>Type</th><th>Status</th><th>Reason</th></tr></thead>
                <tbody>
                  {data.adjustments.map((a, i) => (
                    <tr key={i}><td>{a.date}</td><td>{a.requester}</td><td>{a.section} {a.subject}</td><td>{a.periods}</td><td>{a.taken_by || "—"}</td><td>{a.kind || "—"}</td><td>{a.status}</td><td>{a.reason}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section>
            <h2 className="heading mb-2">3. Fairness trend</h2>
            <table className="ruled-table">
              <thead><tr><th>Week ending</th><th>Fairness score</th></tr></thead>
              <tbody>{data.trend.map((t) => <tr key={t.end}><td>{dayLabel(t.end)}</td><td>{t.score ?? "no data"}</td></tr>)}</tbody>
            </table>
          </section>

          <section>
            <h2 className="heading mb-2">4. Duties</h2>
            {data.duties.length === 0 ? <p className="text-sm text-muted">None in this period.</p> : (
              <table className="ruled-table">
                <thead><tr><th>Date</th><th>Faculty</th><th>Period</th><th>Duty</th></tr></thead>
                <tbody>{data.duties.map((d, i) => <tr key={i}><td>{d.date}</td><td>{d.faculty}</td><td>P{d.period}</td><td>{d.kind}</td></tr>)}</tbody>
              </table>
            )}
          </section>
          <footer className="border-t border-rule pt-2 text-xs text-muted">Generated by EduCrew. Faculty names are anonymised.</footer>
        </article>
      )}
    </div>
  );
}
