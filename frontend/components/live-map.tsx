"use client";
// B14–B18: the Live Ticket Map. Rooms are laid out as a grid from the locations table
// (one row per corridor side). Colour + icon + label for status; a pulse while a ticket is new.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, errorText } from "@/lib/api";
import { CATEGORIES, relative, STATUSES } from "@/lib/format";
import { useInterval, useLive } from "@/lib/live";
import { Icon, LiveDot, Notice, PriorityTag, StatusTag } from "./ui";

type Room = {
  code: string;
  room_name: string;
  kind: string;
  level: "green" | "amber" | "red";
  label: string;
  open_count: number;
  overdue: boolean;
  critical: boolean;
  is_new: boolean;
  escalated: boolean;
};
type Floor = { block: string; floor: number; rows: { side: string; rooms: Room[] }[] };
type Summary = {
  open: number;
  new: number;
  overdue: number;
  escalated: number;
  avg_resolution_hours: number | null;
  resolved_today: number;
};
type TicketRow = {
  ref: string;
  summary: string;
  priority: string;
  status: string;
  status_label: string;
  deadline_at: string;
  overdue: boolean;
  escalated: boolean;
  report_count: number;
  assigned_to: string | null;
  created_at: string;
  resolved_at: string | null;
};
type RoomDetail = {
  location: { code: string; room_name: string; block: string; floor: number; assets: string[] };
  open: TicketRow[];
  closed: TicketRow[];
};

// Tinted fills on the dark panel; the full status colour is the border and icon.
const LEVEL = {
  green: { fill: "#173a22", stroke: "#0ca30c", icon: "check", text: "No open tickets" },
  amber: { fill: "#43360f", stroke: "#fab219", icon: "alert", text: "Open ticket (normal or high)" },
  red: { fill: "#561d1d", stroke: "#d03b3b", icon: "octagon", text: "Critical or overdue" },
} as const;

const TILE_W = 156;
const TILE_H = 92;
const GAP = 10;
const CORRIDOR = 34;
const PAD = 12;

function TileIcon({ name, x, y, color }: { name: string; x: number; y: number; color: string }) {
  // Small inline glyphs (same shapes as the UI icons) so status never relies on colour.
  const common = { fill: "none", stroke: color, strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <g transform={`translate(${x} ${y}) scale(0.6)`}>
      {name === "check" && <path d="M5 12.5l4.5 4.5L19 7.5" {...common} />}
      {name === "alert" && (<><path d="M12 4l9 16H3z" {...common} /><path d="M12 10v4.5M12 17.5v.01" {...common} /></>)}
      {name === "octagon" && (<><path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z" {...common} /><path d="M12 7.5v5.5M12 16.5v.01" {...common} /></>)}
    </g>
  );
}

function FloorPlan({ floor, selected, onSelect }: { floor: Floor; selected: string | null; onSelect: (code: string) => void }) {
  const cols = Math.max(...floor.rows.map((r) => r.rooms.length), 1);
  const width = PAD * 2 + cols * TILE_W + (cols - 1) * GAP;
  const rowsY = floor.rows.map((_, i) => PAD + i * (TILE_H + CORRIDOR));
  const height = PAD * 2 + floor.rows.length * TILE_H + (floor.rows.length - 1) * CORRIDOR;

  const key = (e: KeyboardEvent, code: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(code);
    }
  };

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="group" aria-label={`Block ${floor.block}, floor ${floor.floor}`}>
      {floor.rows.length > 1 &&
        rowsY.slice(0, -1).map((y, i) => (
          <g key={`corridor-${i}`}>
            <rect x={PAD} y={y + TILE_H + 6} width={width - PAD * 2} height={CORRIDOR - 12} rx={4} fill="#262624" />
            <text x={width / 2} y={y + TILE_H + CORRIDOR / 2 + 4} textAnchor="middle" fontSize={11} fill="#898781" letterSpacing={2}>
              CORRIDOR
            </text>
          </g>
        ))}
      {floor.rows.map((row, ri) =>
        row.rooms.map((room, ci) => {
          const x = PAD + ci * (TILE_W + GAP);
          const y = rowsY[ri];
          const style = LEVEL[room.level];
          const isSel = selected === room.code;
          const name = room.room_name.length > 20 ? room.room_name.slice(0, 19) + "…" : room.room_name;
          return (
            <g
              key={room.code}
              role="button"
              tabIndex={0}
              aria-label={`${room.room_name}: ${room.label}${room.is_new ? ", new ticket" : ""}`}
              onClick={() => onSelect(room.code)}
              onKeyDown={(e) => key(e, room.code)}
              className="cursor-pointer outline-none focus-visible:[&>rect.tile]:stroke-white"
            >
              <title>{`${room.room_name} (${room.code}): ${room.label}`}</title>
              {room.is_new && (
                <rect className="pulse-ring" x={x} y={y} width={TILE_W} height={TILE_H} rx={8} fill="none" stroke={style.stroke} />
              )}
              <rect
                className="tile"
                x={x}
                y={y}
                width={TILE_W}
                height={TILE_H}
                rx={8}
                fill={style.fill}
                stroke={isSel ? "#ffffff" : style.stroke}
                strokeWidth={isSel ? 3 : 2}
              />
              <text x={x + 12} y={y + 24} fontSize={14} fontWeight={600} fill="#f0efec">{name}</text>
              <text x={x + 12} y={y + 42} fontSize={11} fill="#c3c2b7" fontFamily="ui-monospace, Consolas, monospace">
                {room.code.split("-").slice(-1)[0]}
              </text>
              <TileIcon name={style.icon} x={x + 10} y={y + 56} color={style.stroke} />
              <text x={x + 30} y={y + 72} fontSize={13} fontWeight={600} fill="#f0efec">{room.label}</text>
              {room.is_new && (
                <g>
                  <rect x={x + TILE_W - 50} y={y + 10} width={40} height={18} rx={9} fill="#f0efec" />
                  <text x={x + TILE_W - 30} y={y + 23} fontSize={11} fontWeight={700} textAnchor="middle" fill="#1a1a19">NEW</text>
                </g>
              )}
              {room.escalated && (
                <text x={x + TILE_W - 10} y={y + 72} fontSize={10} textAnchor="end" fill="#f0efec">↑ Estate</text>
              )}
            </g>
          );
        }),
      )}
    </svg>
  );
}

export function LiveMap() {
  const [floors, setFloors] = useState<Floor[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RoomDetail | null>(null);
  const [error, setError] = useState("");
  const [flash, setFlash] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => {
    const qs = new URLSearchParams();
    if (category) qs.set("category", category);
    if (status) qs.set("status", status);
    api<{ block: string; floor: number }[]>("/map/floors")
      .then((list) =>
        Promise.all([
          Promise.all(list.map((f) => api<Floor>(`/map/${f.block}/${f.floor}?${qs}`))),
          api<Summary>("/map/summary"),
        ] as const),
      )
      .then(([maps, sum]) => {
        setFloors(maps);
        setSummary(sum);
        setError("");
      })
      .catch((e) => setError(errorText(e)));
  }, [category, status]);

  const loadDetail = useCallback((code: string) => {
    api<RoomDetail>(`/locations/${code}/tickets`).then(setDetail).catch(() => {});
  }, []);

  useEffect(load, [load]);
  useInterval(load, 30000); // deadlines can pass without any event

  const live = useLive(["tickets"], (type, data) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      load();
      if (selected) loadDetail(selected);
    }, 250);
    if (type === "ticket.created") setFlash(`New ticket at ${String(data.location ?? "")}`);
    if (type === "ticket.escalated") setFlash(`Escalated to the Estate Officer: ${String(data.ref ?? "")}`);
  });

  const select = (code: string) => {
    setSelected(code);
    loadDetail(code);
  };

  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else panel.current?.requestFullscreen?.();
  };

  return (
    <div>
      {summary && (
        <div className="mb-5 grid grid-cols-2 gap-x-6 gap-y-4 border-y border-rule py-4 sm:grid-cols-3 lg:grid-cols-6">
          <SummaryItem label="Open tickets" value={summary.open} />
          <SummaryItem label="New, not picked up" value={summary.new} />
          <SummaryItem label="Overdue" value={summary.overdue} tone={summary.overdue ? "bad" : undefined} />
          <SummaryItem label="Escalated" value={summary.escalated} tone={summary.escalated ? "bad" : undefined} />
          <SummaryItem label="Avg resolution" value={summary.avg_resolution_hours === null ? "—" : `${summary.avg_resolution_hours} h`} />
          <SummaryItem label="Resolved today" value={summary.resolved_today} />
        </div>
      )}

      <div className="no-print mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="label" htmlFor="cat">Category</label>
          <select id="cat" className="field w-44" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="st">Status</label>
          <select id="st" className="field w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All open</option>
            {STATUSES.filter((s) => !["resolved", "rejected"].includes(s.value)).map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <LiveDot state={live} />
          <button className="btn btn-sm" onClick={fullscreen}>Full screen</button>
        </div>
      </div>

      {error && <div className="mb-4"><Notice tone="bad">{error}</Notice></div>}
      {flash && (
        <div className="mb-4" aria-live="polite">
          <Notice tone="accent">{flash}</Notice>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div ref={panel} className="space-y-4 rounded-lg bg-map p-4 text-[#f0efec]">
          {floors.map((f) => (
            <section key={`${f.block}-${f.floor}`}>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-[0.12em] text-[#c3c2b7]">
                Block {f.block} · Floor {f.floor}
              </h2>
              <FloorPlan floor={f} selected={selected} onSelect={select} />
            </section>
          ))}
          <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-[#383835] pt-3 text-xs text-[#c3c2b7]">
            {(Object.keys(LEVEL) as (keyof typeof LEVEL)[]).map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span className="inline-block h-3 w-4 rounded-sm border-2" style={{ background: LEVEL[k].fill, borderColor: LEVEL[k].stroke }} />
                <span style={{ color: LEVEL[k].stroke }}><Icon name={LEVEL[k].icon} size={12} /></span>
                {LEVEL[k].text}
              </span>
            ))}
            <span className="inline-flex items-center gap-1.5">
              <span className="rounded-full bg-[#f0efec] px-1.5 text-[10px] font-bold text-[#1a1a19]">NEW</span>
              Pulsing: new, not yet picked up
            </span>
          </div>
        </div>

        <aside className="border-t border-rule pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0" aria-live="polite">
          {!detail ? (
            <p className="text-sm text-muted">Select a room to see its tickets.</p>
          ) : (
            <div>
              <div className="eyebrow">Block {detail.location.block} · Floor {detail.location.floor}</div>
              <h2 className="heading">{detail.location.room_name}</h2>
              <div className="mono text-xs text-muted">{detail.location.code}</div>
              {detail.location.assets.length > 0 && (
                <p className="mt-2 text-xs text-ink-2">{detail.location.assets.join(" · ")}</p>
              )}
              <h3 className="eyebrow mt-5 mb-2">Open ({detail.open.length})</h3>
              {detail.open.length === 0 && <p className="text-sm text-muted">Nothing open here.</p>}
              <ul className="space-y-3">
                {detail.open.map((t) => (
                  <li key={t.ref} className="border-b border-rule pb-3">
                    <Link href={`/tickets/${t.ref}`} className="font-medium text-accent hover:underline">{t.summary}</Link>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <span className="mono text-xs">{t.ref}</span>
                      <PriorityTag priority={t.priority} />
                      <StatusTag status={t.status} label={t.status_label} />
                      {t.report_count > 1 && <span className="text-xs text-ink-2">+{t.report_count - 1} reports</span>}
                    </div>
                    <div className={`mt-1 text-xs ${t.overdue ? "font-semibold text-bad-ink" : "text-ink-2"}`}>
                      {t.overdue ? `Overdue by ${relative(t.deadline_at).replace(" ago", "")}` : `Due ${relative(t.deadline_at)}`}
                      {t.escalated && " · escalated"}
                      {t.assigned_to && ` · ${t.assigned_to}`}
                    </div>
                  </li>
                ))}
              </ul>
              {detail.closed.length > 0 && (
                <>
                  <h3 className="eyebrow mt-5 mb-2">History</h3>
                  <ul className="space-y-1.5 text-sm">
                    {detail.closed.map((t) => (
                      <li key={t.ref} className="flex justify-between gap-2">
                        <Link href={`/tickets/${t.ref}`} className="truncate hover:underline">{t.summary}</Link>
                        <StatusTag status={t.status} label={t.status_label} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function SummaryItem({ label, value, tone }: { label: string; value: number | string; tone?: "bad" }) {
  return (
    <div>
      <div className="text-xs text-ink-2">{label}</div>
      <div className={`flex items-center gap-1.5 text-2xl font-semibold ${tone === "bad" ? "text-bad-ink" : ""}`}>
        {tone === "bad" && <Icon name="alert" size={18} />}
        {value}
      </div>
    </div>
  );
}
