"use client";
// C5: the page behind the one-click Accept / Decline email links. Opening it changes nothing
// (email scanners open links); the faculty member confirms with one tap.
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, Notice } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { dayLabel } from "@/lib/format";

type RequestView = {
  requester: string;
  candidate_name: string;
  date: string;
  periods_label: string;
  section: string;
  subject: string;
  reason: string;
  kind: string;
  swap_label: string | null;
  swap_subject: string | null;
  used: boolean;
  state: string;
  adjustment_status: string;
};

export default function Respond() {
  const { token } = useParams<{ token: string }>();
  const preselected = useSearchParams().get("action");
  const [view, setView] = useState<RequestView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    api<RequestView>(`/adjustments/token/${encodeURIComponent(token)}`, { auth: false })
      .then(setView)
      .catch((e) => setError(errorText(e)));
  }, [token]);

  async function respond(action: "accept" | "decline") {
    setBusy(true);
    setError("");
    try {
      const res = await api<{ outcome: string; next_candidate?: string | null }>("/adjustments/respond-token", {
        body: { token, action },
        auth: false,
      });
      setDone(
        res.outcome === "accepted"
          ? "Thank you. You are taking this class. The HOD and your colleague have been told."
          : res.outcome === "no_longer_free"
            ? "You are no longer free at that time, so we asked the next colleague."
            : "Declined. We have asked the next colleague.",
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !view) return <main className="mx-auto max-w-md px-4 py-10"><Notice tone="bad">{error}</Notice></main>;
  if (!view) return <p className="p-6 text-sm text-muted">Loading request…</p>;

  return (
    <main className="mx-auto max-w-md px-4 py-10">
      <div className="eyebrow">Class cover request for {view.candidate_name}</div>
      <h1 className="mt-1 text-2xl font-semibold">{view.requester} asks you to {view.kind === "swap" ? "swap a class" : "take a class"}</h1>
      <dl className="mt-5 space-y-2 border-y border-rule py-4 text-sm">
        <div className="flex justify-between gap-4"><dt className="text-ink-2">When</dt><dd className="text-right font-medium">{dayLabel(view.date)}, {view.periods_label}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-ink-2">Class</dt><dd className="text-right font-medium">{view.section} · {view.subject}</dd></div>
        {view.kind === "swap" && (
          <div className="flex justify-between gap-4"><dt className="text-ink-2">In return</dt><dd className="text-right font-medium">{view.requester} takes your {view.swap_subject}, {view.swap_label}</dd></div>
        )}
        <div className="flex justify-between gap-4"><dt className="text-ink-2">Reason</dt><dd className="text-right">{view.reason || "—"}</dd></div>
      </dl>

      {done ? (
        <div className="mt-6"><Notice tone="good">{done}</Notice></div>
      ) : view.used || view.state !== "requested" ? (
        <div className="mt-6"><Notice tone="warn">This link has already been used or the request was closed.</Notice></div>
      ) : (
        <div className="mt-6 grid grid-cols-2 gap-3">
          <button className={`btn ${preselected === "decline" ? "btn-danger" : ""}`} disabled={busy} onClick={() => respond("decline")}>
            <Icon name="x" /> Decline
          </button>
          <button className="btn btn-primary" disabled={busy} onClick={() => respond("accept")}>
            <Icon name="check" /> Accept
          </button>
        </div>
      )}
      {error && view && <div className="mt-4"><Notice tone="bad">{error}</Notice></div>}
    </main>
  );
}
