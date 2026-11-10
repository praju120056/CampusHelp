"use client";
// A3 / B7: weights and deadlines are configuration, editable by the HOD (to be confirmed with them).
import { useEffect, useState } from "react";
import { Loading, Notice, PageHeader } from "@/components/ui";
import { api, errorText } from "@/lib/api";

type Settings = {
  workload_weights: Record<string, number>;
  deadline_hours: Record<string, number>;
  demo_deadline_minutes: Record<string, number>;
  reminder: Record<string, number>;
  fairness: Record<string, number>;
  demo_mode: boolean;
};

const GROUPS: { key: keyof Omit<Settings, "demo_mode">; title: string; help: string; labels: Record<string, string> }[] = [
  {
    key: "workload_weights",
    title: "Workload weights",
    help: "Load units per period, slot or hour. A 2-period lab counts 2 × the lab weight.",
    labels: { theory: "Theory period", lab: "Lab period", duty: "Duty / invigilation slot", meeting: "Meeting hour", substitution: "Substitution period", adjusted: "Class handed over" },
  },
  {
    key: "deadline_hours",
    title: "Ticket deadlines (hours)",
    help: "Time to resolve before escalation to the Estate Officer.",
    labels: { critical: "Critical", high: "High", normal: "Normal" },
  },
  {
    key: "demo_deadline_minutes",
    title: "Demo-mode deadlines (minutes)",
    help: "Used instead of hours when DEMO_MODE is on, so escalation can be shown on stage.",
    labels: { critical: "Critical", high: "High", normal: "Normal" },
  },
  {
    key: "reminder",
    title: "Reminders",
    help: "Remind the in-charge once this share of the time to the deadline has passed (0.75 = 75%).",
    labels: { fraction: "Remind at" },
  },
  {
    key: "fairness",
    title: "Fairness analytics",
    help: "Window length, how many windows the trend shows, and how many overloaded weeks in a row trigger burnout watch.",
    labels: { window_days: "Window (days)", trend_weeks: "Trend windows", burnout_weeks: "Burnout after (weeks)" },
  },
];

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  useEffect(() => {
    api<Settings>("/admin/settings").then(setS).catch((e) => setMsg({ tone: "bad", text: errorText(e) }));
  }, []);

  const set = (group: keyof Omit<Settings, "demo_mode">, field: string, value: string) =>
    setS((cur) => (cur ? { ...cur, [group]: { ...cur[group], [field]: value === "" ? 0 : Number(value) } } : cur));

  async function save() {
    if (!s) return;
    setBusy(true);
    setMsg(null);
    try {
      const { demo_mode: _ignored, ...body } = s;
      void _ignored;
      setS(await api<Settings>("/admin/settings", { method: "PUT", body }));
      setMsg({ tone: "good", text: "Saved. Loads and the fairness score now use these values." });
    } catch (e) {
      setMsg({ tone: "bad", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="HOD" title="Settings" actions={<button className="btn btn-primary" disabled={busy || !s} onClick={save}>Save</button>}>
        Proposed defaults from the spec. Confirm or change them with the department.
      </PageHeader>
      {msg && <div className="mb-4"><Notice tone={msg.tone}>{msg.text}</Notice></div>}
      {!s ? (
        <Loading />
      ) : (
        <div className="space-y-8">
          <p className="text-sm">Demo mode is <strong>{s.demo_mode ? "on" : "off"}</strong> (set DEMO_MODE in .env).</p>
          {GROUPS.map((g) => (
            <section key={g.key} className="rule-top">
              <h2 className="heading">{g.title}</h2>
              <p className="mb-3 text-xs text-ink-2">{g.help}</p>
              <div className="grid gap-3 sm:grid-cols-3">
                {Object.entries(g.labels).map(([field, text]) => (
                  <div key={field}>
                    <label className="label" htmlFor={`${g.key}-${field}`}>{text}</label>
                    <input id={`${g.key}-${field}`} className="field num" type="number" step="0.05" min={0}
                      value={s[g.key][field] ?? 0} onChange={(e) => set(g.key, field, e.target.value)} />
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
