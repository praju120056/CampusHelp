"use client";
// C4: each suggestion explains itself: free or not, subject match, weekly load, recent substitutions.
import { Icon, Tag } from "./ui";

export type Candidate = {
  id: number;
  faculty_id: number;
  name: string;
  designation: string;
  kind: "swap" | "substitute";
  rank: number;
  score: number;
  breakdown: {
    free?: boolean;
    free_note?: string;
    subject_match?: boolean | null;
    weekly_load?: number;
    recent_substitutions?: number;
    swap_note?: string;
    tier?: number;
    fit_formula?: string;
    assigned_by_hod?: boolean;
  };
  swap_label: string | null;
  swap_subject: string | null;
  state: string;
};

const STATE_TAG: Record<string, { tone: "good" | "info" | "neutral" | "bad"; icon: string; text: string }> = {
  requested: { tone: "info", icon: "clock", text: "Asked, waiting" },
  accepted: { tone: "good", icon: "check", text: "Accepted" },
  declined: { tone: "neutral", icon: "x", text: "Declined" },
  unavailable: { tone: "neutral", icon: "x", text: "No longer free" },
  withdrawn: { tone: "neutral", icon: "x", text: "Withdrawn" },
};

export function SuggestionList({
  candidates,
  canChoose,
  onChoose,
  busy,
  limit = 6,
}: {
  candidates: Candidate[];
  canChoose: boolean;
  onChoose?: (c: Candidate) => void;
  busy?: boolean;
  limit?: number;
}) {
  if (candidates.length === 0) return <p className="text-sm text-muted">Nobody is free for this class. The HOD has been told.</p>;
  const shown = candidates.slice(0, limit);
  return (
    <div>
      <ol className="divide-y divide-rule border-y border-rule">
        {shown.map((c) => {
          const b = c.breakdown;
          const state = STATE_TAG[c.state];
          return (
            <li key={c.id} className="flex flex-wrap items-start gap-3 py-3">
              <span className="num w-6 pt-0.5 text-right text-sm text-muted">{c.rank}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-semibold">{c.name}</span>
                  {c.kind === "swap" ? (
                    <Tag tone="accent" icon="swap">Swap</Tag>
                  ) : b.tier === 2 ? (
                    <Tag tone="warn" icon="alert">Substitute, other subject</Tag>
                  ) : (
                    <Tag tone="info">Substitute</Tag>
                  )}
                  {state && <Tag tone={state.tone} icon={state.icon}>{state.text}</Tag>}
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2">
                  <span className="inline-flex items-center gap-1"><Icon name="check" size={12} className="text-good-ink" />{b.free_note ?? "Free"}</span>
                  {b.subject_match !== null && b.subject_match !== undefined && (
                    <span className="inline-flex items-center gap-1">
                      <Icon name={b.subject_match ? "check" : "x"} size={12} className={b.subject_match ? "text-good-ink" : "text-bad-ink"} />
                      {b.subject_match ? "Teaches this subject" : "Not this subject"}
                    </span>
                  )}
                  {b.weekly_load !== undefined && <span>Load last 7 days: <strong className="num text-ink">{b.weekly_load}</strong></span>}
                  {b.recent_substitutions !== undefined && <span>Recent subs: <strong className="num text-ink">{b.recent_substitutions}</strong></span>}
                  {!b.assigned_by_hod && <span>Fit <strong className="num text-ink">{Math.round(c.score)}</strong></span>}
                </div>
                {b.swap_note && <p className="mt-1 text-xs text-ink-2">{b.swap_note}</p>}
              </div>
              {canChoose && c.state === "suggested" && onChoose && (
                <button className="btn btn-sm" disabled={busy} onClick={() => onChoose(c)}>Ask</button>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-xs text-muted">
        Order: swaps in the same section first, then free colleagues who teach the subject, then others; lowest recent load first.
        Fit = {candidates[0]?.breakdown.fit_formula ?? "100 − 2 × weekly load − 5 × recent substitutions"}.
        {candidates.length > limit && ` ${candidates.length - limit} more not shown.`}
      </p>
    </div>
  );
}
