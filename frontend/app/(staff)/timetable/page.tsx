"use client";
// C6: the timetable for a date, with accepted adjustments shown in place.
import { useCallback, useEffect, useState } from "react";
import { Icon, Loading, Notice, PageHeader, Tag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { shiftISO, todayISO } from "@/lib/format";
import { useLive } from "@/lib/live";

type Cell = { subject: string; type: string; faculty: string; kind: string; original_faculty: string | null };
type Grid = {
  date: string;
  day: string;
  periods: { period: number; start: string; end: string }[];
  sections: { section: string; cells: Record<string, Cell> }[];
};

export default function TimetablePage() {
  const [date, setDate] = useState(todayISO());
  const [grid, setGrid] = useState<Grid | null>(null);
  const [error, setError] = useState("");

  const load = useCallback((d: string) => {
    api<Grid>(`/timetable/day?date=${d}`).then(setGrid).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(() => load(date), [date, load]);
  useLive(["adjustments"], () => load(date));

  return (
    <>
      <PageHeader eyebrow="Timetable" title={grid ? grid.day : "Timetable"} actions={
        <div className="flex items-center gap-1">
          <button className="btn btn-sm" aria-label="Previous day" onClick={() => setDate(shiftISO(date, -1))}><Icon name="left" /></button>
          <input type="date" className="field w-44" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date" />
          <button className="btn btn-sm" aria-label="Next day" onClick={() => setDate(shiftISO(date, 1))}><Icon name="right" /></button>
        </div>
      }>
        Adjusted classes are marked, with who is covering and for whom.
      </PageHeader>
      {error && <Notice tone="bad">{error}</Notice>}
      {!grid ? (
        <Loading />
      ) : grid.periods.length === 0 ? (
        <p className="text-sm text-muted">No classes on this day.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="ruled-table min-w-[860px] table-fixed">
            <thead>
              <tr>
                <th className="w-20">Section</th>
                {grid.periods.map((p) => (
                  <th key={p.period}>P{p.period}<div className="font-normal normal-case tracking-normal text-muted">{p.start}–{p.end}</div></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.sections.map((s) => (
                <tr key={s.section}>
                  <td className="font-semibold">{s.section}</td>
                  {grid.periods.map((p) => {
                    const c = s.cells[String(p.period)];
                    if (!c) return <td key={p.period} className="text-muted">—</td>;
                    const adjusted = c.kind !== "regular";
                    return (
                      <td key={p.period} className={adjusted ? "bg-accent-soft" : ""}>
                        <div className="text-sm font-medium leading-snug">{c.subject}</div>
                        <div className="text-xs text-ink-2">{c.faculty}</div>
                        {c.type === "lab" && <div className="text-xs text-muted">Lab</div>}
                        {adjusted && (
                          <div className="mt-1">
                            <Tag tone="accent" icon="swap">{c.kind === "swap" ? "Swap" : "Substitute"}{c.original_faculty ? ` for ${c.original_faculty}` : ""}</Tag>
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
