"use client";
// Hand-drawn SVG charts (no chart library). Every chart has a tooltip, a table view, and a legend
// when it shows 2+ series. Status (overloaded/underused) is always icon + text, never colour alone.
import { useState, type ReactNode } from "react";

const C = {
  s1: "#2a78d6",
  s2: "#eb6834",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  ink: "#1c1b19",
  ink2: "#52514e",
  muted: "#7a776f",
  surface: "#fdfcfa",
  band: "#ecebe5",
  bad: "#a32626",
  warn: "#7a5000",
};

type Tip = { x: number | string; y: number | string; content: ReactNode } | null;

export function ChartFrame({
  title,
  subtitle,
  legend,
  table,
  children,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  legend?: { color: string; label: string; kind?: "bar" | "line" | "band" }[];
  table: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="min-w-0">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <figcaption>
          <div className="heading">{title}</div>
          {subtitle && <div className="text-xs text-ink-2">{subtitle}</div>}
        </figcaption>
        <div className="no-print flex flex-wrap items-center gap-2">
          {actions}
          <button className="btn btn-ghost btn-sm" onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}>
            {showTable ? "Show chart" : "Show table"}
          </button>
        </div>
      </div>
      {legend && legend.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          {legend.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1.5">
              {l.kind === "line" ? (
                <svg width="18" height="10" aria-hidden="true"><line x1="1" y1="5" x2="17" y2="5" stroke={l.color} strokeWidth="2" strokeLinecap="round" /><circle cx="9" cy="5" r="3" fill={l.color} /></svg>
              ) : l.kind === "band" ? (
                <span className="inline-block h-3 w-4 rounded-sm" style={{ background: l.color }} />
              ) : (
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: l.color }} />
              )}
              {l.label}
            </span>
          ))}
        </div>
      )}
      {showTable ? <div className="overflow-x-auto">{table}</div> : children}
    </figure>
  );
}

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 min-w-36 rounded-md border border-rule-strong bg-surface px-3 py-2 text-xs shadow-sm"
      style={{ left: tip.x, top: tip.y, transform: "translate(-50%, calc(-100% - 10px))" }}
    >
      {tip.content}
    </div>
  );
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

/** Path for a horizontal bar with a 4px rounded data end and a square baseline end. */
function hBar(x: number, y: number, w: number, h: number, r = 4): string {
  if (w <= 0) return "";
  const rr = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
}

/** Path for a vertical column with a 4px rounded top and square baseline. */
function vBar(x: number, baseY: number, w: number, h: number, r = 4): string {
  if (h <= 0) return "";
  const rr = Math.min(r, h, w / 2);
  const top = baseY - h;
  return `M${x},${baseY}V${top + rr}Q${x},${top} ${x + rr},${top}H${x + w - rr}Q${x + w},${top} ${x + w},${top + rr}V${baseY}Z`;
}

// ------------------------------------------------------------------ A9: load vs department mean

export type LoadRow = { name: string; load: number; flag: string; burnout: boolean; substitutions: number; duties: number };

export function LoadBars({ rows, mean, lower, upper }: { rows: LoadRow[]; mean: number; lower: number; upper: number }) {
  const [tip, setTip] = useState<Tip>(null);
  const W = 720;
  const LABEL = 96;
  const RIGHT = 200;
  const ROW = 28;
  const BAR = 14;
  const TOP = 22;
  const plotW = W - LABEL - RIGHT;
  const max = niceMax(Math.max(upper, ...rows.map((r) => r.load)) * 1.05);
  const x = (v: number) => LABEL + (v / max) * plotW;
  const H = TOP + rows.length * ROW + 24;
  const ticks = [0, max / 4, max / 2, (3 * max) / 4, max];

  const table = (
    <table className="ruled-table">
      <thead><tr><th>Faculty</th><th>Weighted load</th><th>Flag</th><th>Burnout watch</th><th>Substitution periods</th><th>Duty slots</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name}>
            <td>{r.name}</td><td>{r.load}</td><td>{r.flag === "normal" ? "—" : r.flag}</td>
            <td>{r.burnout ? "Yes" : "—"}</td><td>{r.substitutions}</td><td>{r.duties}</td>
          </tr>
        ))}
        <tr><td>Department mean</td><td>{mean}</td><td colSpan={4}>Normal range {lower} – {upper}</td></tr>
      </tbody>
    </table>
  );

  return (
    <ChartFrame
      title="Load against the department mean"
      subtitle="Weighted load, last 7 days. Above mean + 1 SD is flagged overloaded; below mean − 1 SD, underused."
      legend={[
        { color: C.s1, label: "Weighted load" },
        { color: C.band, label: "Normal range (mean ± 1 SD)", kind: "band" },
      ]}
      table={table}
    >
      <div className="relative" onMouseLeave={() => setTip(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Bar chart of weighted load per faculty member">
          <rect x={x(lower)} y={TOP - 6} width={Math.max(0, x(upper) - x(lower))} height={rows.length * ROW + 6} fill={C.band} />
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={TOP - 6} y2={TOP + rows.length * ROW} stroke={C.grid} strokeWidth={1} />
              <text x={x(t)} y={H - 6} textAnchor="middle" fontSize={11} fill={C.muted} className="num">{Math.round(t * 10) / 10}</text>
            </g>
          ))}
          <line x1={x(mean)} x2={x(mean)} y1={TOP - 10} y2={TOP + rows.length * ROW} stroke={C.ink2} strokeWidth={1.5} />
          <text x={x(mean)} y={TOP - 12} textAnchor="middle" fontSize={11} fill={C.ink2}>Mean {mean}</text>
          <line x1={LABEL} x2={LABEL} y1={TOP - 6} y2={TOP + rows.length * ROW} stroke={C.axis} strokeWidth={1} />
          {rows.map((r, i) => {
            const y = TOP + i * ROW + (ROW - BAR) / 2;
            const end = x(r.load);
            const flagText =
              (r.flag === "overloaded" ? "▲ Overloaded" : r.flag === "underused" ? "▼ Underused" : "") +
              (r.burnout ? " · burnout watch" : "");
            return (
              <g
                key={r.name}
                onMouseMove={(e) => {
                  const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  setTip({
                    x: e.clientX - box.left,
                    y: e.clientY - box.top,
                    content: (
                      <div>
                        <div className="font-semibold">{r.name}</div>
                        <div>Weighted load <strong className="num">{r.load}</strong> (mean {mean})</div>
                        <div>Substitutions {r.substitutions} · Duties {r.duties}</div>
                        {r.flag !== "normal" && <div>{flagText}</div>}
                        {r.burnout && <div>Burnout watch: overloaded 3 weeks running</div>}
                      </div>
                    ),
                  });
                }}
              >
                <rect x={0} y={TOP + i * ROW} width={W} height={ROW} fill="transparent" />
                <text x={LABEL - 8} y={y + BAR - 2} textAnchor="end" fontSize={12} fill={C.ink}>{r.name}</text>
                <path d={hBar(LABEL, y, end - LABEL, BAR)} fill={C.s1} />
                <text x={end + 6} y={y + BAR - 2} fontSize={12} fill={C.ink} className="num">{r.load}</text>
                {flagText && (
                  <text x={W - RIGHT + 40} y={y + BAR - 2} fontSize={12} fontWeight={600} fill={r.flag === "overloaded" ? C.bad : C.warn}>
                    {flagText}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        <Tooltip tip={tip} />
      </div>
    </ChartFrame>
  );
}

// ------------------------------------------------------------------ A8: fairness trend

export type TrendPoint = { start: string; end: string; score: number | null; gini: number | null };

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 360;
  const H = 150;
  const L = 30;
  const R = 34;
  const T = 12;
  const B = 26;
  const valid = points.map((p, i) => ({ ...p, i })).filter((p) => p.score !== null) as (TrendPoint & { i: number; score: number })[];
  const x = (i: number) => L + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (W - L - R));
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  const path = valid.map((p, k) => `${k === 0 ? "M" : "L"}${x(p.i)},${y(p.score)}`).join(" ");
  const fmt = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  const last = valid[valid.length - 1];
  const hp = hover !== null ? points[hover] : null;

  const table = (
    <table className="ruled-table">
      <thead><tr><th>Week ending</th><th>Fairness score</th><th>Gini index</th></tr></thead>
      <tbody>{points.map((p) => <tr key={p.end}><td>{fmt(p.end)}</td><td>{p.score ?? "no data"}</td><td>{p.gini ?? "—"}</td></tr>)}</tbody>
    </table>
  );

  return (
    <ChartFrame title="Fairness trend" subtitle="Score per 7-day window (100 = perfectly even load)" table={table}>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label="Line chart of the fairness score per week"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            const px = ((e.clientX - box.left) / box.width) * W;
            let best = 0;
            points.forEach((_, i) => {
              if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
            });
            setHover(best);
          }}
        >
          {[0, 50, 100].map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={C.grid} strokeWidth={1} />
              <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize={10} fill={C.muted}>{v}</text>
            </g>
          ))}
          {points.map((p, i) => (
            <text key={p.end} x={x(i)} y={H - 8} textAnchor="middle" fontSize={10} fill={C.muted}>{fmt(p.end)}</text>
          ))}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke={C.axis} strokeWidth={1} />}
          <path d={path} fill="none" stroke={C.s1} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {valid.map((p) => (
            <circle key={p.end} cx={x(p.i)} cy={y(p.score)} r={4} fill={C.s1} stroke={C.surface} strokeWidth={2} />
          ))}
          {last && <text x={x(last.i) + 8} y={y(last.score) + 4} fontSize={12} fontWeight={600} fill={C.ink}>{last.score}</text>}
        </svg>
        {hp && (
          <Tooltip
            tip={{
              x: `${(x(hover!) / W) * 100}%`,
              y: 10,
              content: (
                <div>
                  <div className="font-semibold">Week ending {fmt(hp.end)}</div>
                  <div>Score {hp.score ?? "no data"}{hp.gini !== null && ` · Gini ${hp.gini}`}</div>
                </div>
              ),
            }}
          />
        )}
      </div>
    </ChartFrame>
  );
}

// ------------------------------------------------------------------ A5: weekly / monthly load

export type Series = {
  granularity: string;
  periods: { label: string; start: string; end: string }[];
  faculty: { faculty_id: number; name: string; values: number[] }[];
  department: number[];
  mean: number[];
};

export function LoadSeriesChart({
  data,
  focus,
  actions,
}: {
  data: Series;
  focus: number | null;
  actions?: ReactNode;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = 230;
  const L = 36;
  const R = 12;
  const T = 14;
  const B = 30;
  const person = data.faculty.find((f) => f.faculty_id === focus) ?? null;
  const max = niceMax(Math.max(1, ...data.mean, ...(person?.values ?? [])) * 1.1);
  const n = data.periods.length;
  const band = (W - L - R) / Math.max(n, 1);
  const barW = Math.min(24, band * 0.5);
  const cx = (i: number) => L + band * i + band / 2;
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const base = y(0);
  const ticks = [0, max / 2, max];
  const linePath = person ? person.values.map((v, i) => `${i === 0 ? "M" : "L"}${cx(i)},${y(v)}`).join(" ") : "";

  const legend = [{ color: C.s1, label: "Department mean per faculty" }];
  if (person) legend.push({ color: C.s2, label: person.name, kind: "line" } as never);

  const table = (
    <table className="ruled-table">
      <thead>
        <tr>
          <th>Faculty</th>
          {data.periods.map((p) => <th key={p.start}>{p.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {data.faculty.map((f) => (
          <tr key={f.faculty_id}><td>{f.name}</td>{f.values.map((v, i) => <td key={i}>{v}</td>)}</tr>
        ))}
        <tr className="font-semibold"><td>Department total</td>{data.department.map((v, i) => <td key={i}>{v}</td>)}</tr>
        <tr><td>Mean per faculty</td>{data.mean.map((v, i) => <td key={i}>{v}</td>)}</tr>
      </tbody>
    </table>
  );

  return (
    <ChartFrame
      title={data.granularity === "month" ? "Monthly load" : "Weekly load"}
      subtitle="Weighted load per calendar period. Pick a faculty member to compare with the department mean."
      legend={legend}
      table={table}
      actions={actions}
    >
      <div className="relative" onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Column chart of load per period">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={C.grid} strokeWidth={1} />
              <text x={L - 6} y={y(t) + 4} textAnchor="end" fontSize={10} fill={C.muted} className="num">{Math.round(t * 10) / 10}</text>
            </g>
          ))}
          {data.periods.map((p, i) => (
            <g key={p.start} onMouseEnter={() => setHover(i)}>
              <rect x={L + band * i} y={T} width={band} height={H - T - B} fill={hover === i ? "#f1efe9" : "transparent"} />
              <path d={vBar(cx(i) - barW / 2, base, barW, base - y(data.mean[i]))} fill={C.s1} />
              <text x={cx(i)} y={H - 10} textAnchor="middle" fontSize={10} fill={C.muted}>{p.label.replace("Wk of ", "")}</text>
            </g>
          ))}
          <line x1={L} x2={W - R} y1={base} y2={base} stroke={C.axis} strokeWidth={1} />
          {person && (
            <>
              <path d={linePath} fill="none" stroke={C.s2} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" pointerEvents="none" />
              {person.values.map((v, i) => (
                <circle key={i} cx={cx(i)} cy={y(v)} r={4} fill={C.s2} stroke={C.surface} strokeWidth={2} pointerEvents="none" />
              ))}
            </>
          )}
        </svg>
        {hover !== null && (
          <Tooltip
            tip={{
              x: `${(cx(hover) / W) * 100}%`,
              y: 20,
              content: (
                <div>
                  <div className="font-semibold">{data.periods[hover].label}</div>
                  <div>Mean per faculty <strong className="num">{data.mean[hover]}</strong></div>
                  <div>Department total {data.department[hover]}</div>
                  {person && <div>{person.name} <strong className="num">{person.values[hover]}</strong></div>}
                </div>
              ),
            }}
          />
        )}
      </div>
    </ChartFrame>
  );
}
