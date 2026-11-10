import type { ReactNode } from "react";

const PATHS: Record<string, ReactNode> = {
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  alert: (
    <>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4.5M12 17.5v.01" />
    </>
  ),
  octagon: (
    <>
      <path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z" />
      <path d="M12 7.5v5.5M12 16.5v.01" />
    </>
  ),
  circle: <circle cx="12" cy="12" r="7" />,
  dot: <circle cx="12" cy="12" r="4" fill="currentColor" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  x: <path d="M6 6l12 12M18 6L6 18" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  up: <path d="M12 19V5M6 11l6-6 6 6" />,
  down: <path d="M12 5v14M6 13l6 6 6-6" />,
  left: <path d="M15 5l-7 7 7 7" />,
  right: <path d="M9 5l7 7-7 7" />,
  bell: (
    <>
      <path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </>
  ),
  camera: (
    <>
      <path d="M4 8h3.5L9 5.5h6L16.5 8H20v11H4z" />
      <circle cx="12" cy="13.5" r="3.5" />
    </>
  ),
  swap: (
    <>
      <path d="M7 4L4 7l3 3M4 7h12" />
      <path d="M17 14l3 3-3 3M20 17H8" />
    </>
  ),
  spark: <path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6z" />,
  download: (
    <>
      <path d="M12 4v11M7 10.5l5 5 5-5" />
      <path d="M5 19.5h14" />
    </>
  ),
  print: (
    <>
      <path d="M7 9V4h10v5" />
      <path d="M5 9h14v7h-3v4H8v-4H5z" />
    </>
  ),
  flame: <path d="M12 21c-3.9 0-6.5-2.6-6.5-6.1 0-3.4 2.6-5.3 3.6-8.4 1.4 1.6 1.9 3 1.9 4.4 1.3-.8 2.2-2.5 2.2-4.9 2.9 2.4 5.3 5.5 5.3 8.9 0 3.5-2.6 6.1-6.5 6.1z" />,
  logout: (
    <>
      <path d="M14 4h5v16h-5" />
      <path d="M10 8l-4 4 4 4M6 12h10" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V5M7 9.5l5-5 5 5" />
      <path d="M5 19.5h14" />
    </>
  ),
};

export function Icon({ name, size = 16, className = "" }: { name: string; size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      {PATHS[name] ?? PATHS.circle}
    </svg>
  );
}

export type Tone = "good" | "warn" | "bad" | "info" | "neutral" | "accent";

const TONE_CLASS: Record<Tone, string> = {
  good: "bg-good-soft text-good-ink border-good/40",
  warn: "bg-warn-soft text-warn-ink border-warn/60",
  bad: "bg-bad-soft text-bad-ink border-bad/40",
  info: "bg-info-soft text-info-ink border-info-ink/25",
  neutral: "bg-paper text-ink-2 border-rule-strong",
  accent: "bg-accent-soft text-accent border-accent/30",
};

/** Status label: always icon + text, never colour alone. */
export function Tag({ tone, icon, children, title }: { tone: Tone; icon?: string; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      {icon && <Icon name={icon} size={12} />}
      {children}
    </span>
  );
}

export function PriorityTag({ priority }: { priority: string }) {
  if (priority === "critical") return <Tag tone="bad" icon="octagon">Critical</Tag>;
  if (priority === "high") return <Tag tone="warn" icon="alert">High</Tag>;
  return <Tag tone="neutral" icon="circle">Normal</Tag>;
}

export function StatusTag({ status, label }: { status: string; label?: string }) {
  const text = label ?? status.replace("_", " ").replace(/^./, (c) => c.toUpperCase());
  if (status === "resolved" || status === "accepted") return <Tag tone="good" icon="check">{text}</Tag>;
  if (status === "rejected" || status === "cancelled") return <Tag tone="neutral" icon="x">{text}</Tag>;
  if (status === "new" || status === "open") return <Tag tone="accent" icon="dot">{text}</Tag>;
  if (status === "exhausted") return <Tag tone="bad" icon="alert">No one left</Tag>;
  return <Tag tone="info" icon="clock">{text}</Tag>;
}

export function FlagTag({ flag }: { flag: string }) {
  if (flag === "overloaded") return <Tag tone="bad" icon="up">Overloaded</Tag>;
  if (flag === "underused") return <Tag tone="warn" icon="down">Underused</Tag>;
  return null;
}

export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  const icon = tone === "good" ? "check" : tone === "bad" ? "alert" : tone === "warn" ? "alert" : "circle";
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${TONE_CLASS[tone]}`}>
      <Icon name={icon} size={16} className="mt-0.5" />
      <div>{children}</div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {children && <div className="mt-1 text-sm text-ink-2">{children}</div>}
      </div>
      {actions && <div className="no-print flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Loading({ text = "Loading…" }: { text?: string }) {
  return <p className="py-8 text-sm text-muted">{text}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="border-y border-dashed border-rule-strong py-6 text-center text-sm text-muted">{children}</p>;
}

export function LiveDot({ state }: { state: "connecting" | "live" | "offline" }) {
  const text = state === "live" ? "Live" : state === "connecting" ? "Connecting" : "Offline, retrying";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span className={`inline-block h-2 w-2 rounded-full ${state === "live" ? "bg-good" : state === "connecting" ? "bg-warn" : "bg-bad"}`} />
      {text}
    </span>
  );
}

export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: Tone }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="text-2xl font-semibold leading-tight">{value}</div>
      {note && <div className="mt-0.5 text-xs">{tone ? <Tag tone={tone}>{note}</Tag> : <span className="text-muted">{note}</span>}</div>}
    </div>
  );
}
