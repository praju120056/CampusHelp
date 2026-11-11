"use client";
// C2: import class timetables from PDF. Read → review the draft → check → import. Nothing is saved until Import.
import { useState } from "react";
import { Notice } from "@/components/ui";
import { api, errorText } from "@/lib/api";

type Cell = { day: number; period: number; batch: string | null; subject: string; codes: string[]; type: string };
type Skipped = { day: number | null; period: number | null; text: string; reason: string };
type Draft = {
  source: string;
  pages: { semester: number; section: string; cells: Cell[]; skipped: Skipped[] }[];
  codes: Record<string, string>;
  warnings: string[];
  skipped_notes: string[];
};
type Report = { rows_read: number; valid_slots: number; sections: string[]; errors: string[]; warnings: string[]; new_faculty: string[]; committed: boolean };

const MODES = [
  { value: "auto", label: "Auto: read on this laptop, use AI only for what it can't read" },
  { value: "parser", label: "Local reader only: nothing leaves this laptop" },
  { value: "ai", label: "AI reader (Gemini): the whole PDF is sent to Google" },
];

export default function PdfImport() {
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState("auto");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [replaceAll, setReplaceAll] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function read() {
    setBusy("Reading the PDF… a scanned file goes to Gemini and takes 1 to 2 minutes. Keep this page open.");
    setError("");
    setDraft(null);
    setReport(null);
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.set("mode", mode);
    try {
      setDraft(await api<Draft>("/timetable/pdf/read", { form }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  async function run(commit: boolean) {
    if (!draft) return;
    setBusy(commit ? "Importing…" : "Checking…");
    setError("");
    try {
      setReport(await api<Report>("/timetable/pdf/import", { body: { draft, commit, create_missing: true, replace_all: replaceAll } }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  const codes = draft ? Object.keys(draft.codes).sort() : [];
  const used = new Set(draft?.pages.flatMap((p) => p.cells.flatMap((c) => c.codes)) ?? []);
  const unnamed = [...used].filter((c) => !draft?.codes[c]?.trim());

  return (
    <div className="space-y-4">
      <Notice tone="warn">
        The AI reader sends the whole PDF to Google, including the faculty names and phone numbers printed on it. The database only ever stores Faculty 1…N.
      </Notice>
      <div>
        <label className="label" htmlFor="pdfs">Timetable PDFs (one file per semester is fine)</label>
        <input id="pdfs" type="file" accept=".pdf,application/pdf" multiple className="field py-2"
          onChange={(e) => { setFiles(Array.from(e.target.files ?? [])); setDraft(null); setReport(null); }} />
      </div>
      <div>
        <label className="label" htmlFor="mode">How to read it</label>
        <select id="mode" className="field" value={mode} onChange={(e) => setMode(e.target.value)}>
          {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </div>
      <button className="btn btn-primary" disabled={files.length === 0 || !!busy} onClick={read}>Read PDF</button>
      {busy && <p className="text-sm text-muted" role="status">{busy}</p>}
      {error && <Notice tone="bad">{error}</Notice>}

      {draft && (
        <section className="rule-top space-y-4">
          <h2 className="text-base font-semibold">1. What was read ({draft.source})</h2>
          {draft.pages.length === 0 && (
            <Notice tone="bad">
              Nothing could be read. A scanned PDF can&apos;t be read on this laptop: choose &quot;Auto&quot; or &quot;AI reader&quot; above and read it again.
            </Notice>
          )}
          <table className="w-full text-sm">
            <thead><tr className="text-left text-muted"><th className="py-1">Class</th><th>Periods read</th><th>Skipped</th></tr></thead>
            <tbody>
              {draft.pages.map((p, i) => (
                <tr key={i} className="border-t border-rule">
                  <td className="mono py-1">{p.semester}{p.section}</td>
                  <td className="tabular-nums">{p.cells.length}</td>
                  <td className="tabular-nums">{p.skipped.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {draft.warnings.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm text-warn-ink">{draft.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
          {draft.skipped_notes.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer">{draft.skipped_notes.length} cell(s) skipped (no single faculty member, or unreadable)</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">{draft.skipped_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </details>
          )}

          <h2 className="text-base font-semibold">2. Who is who</h2>
          <p className="text-sm text-muted">
            The PDF uses short codes. Fix any wrong name. Two codes for one person (for example CS and DC) should have the same name. {unnamed.length > 0 && <strong className="text-bad-ink">Add a name for: {unnamed.join(", ")}.</strong>}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {[...new Set([...codes, ...unnamed])].sort().map((code) => (
              <label key={code} className="flex items-center gap-2 text-sm">
                <span className="mono w-12 shrink-0">{code}</span>
                <input className="field" value={draft.codes[code] ?? ""} placeholder="Name"
                  onChange={(e) => { setDraft({ ...draft, codes: { ...draft.codes, [code]: e.target.value } }); setReport(null); }} />
              </label>
            ))}
          </div>

          <h2 className="text-base font-semibold">3. Check and import</h2>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4" checked={replaceAll} onChange={(e) => { setReplaceAll(e.target.checked); setReport(null); }} />
            Replace the whole timetable (otherwise only the classes in these files are replaced)
          </label>
          <div className="flex gap-2">
            <button className="btn" disabled={!!busy} onClick={() => run(false)}>Check</button>
            <button className="btn btn-primary" disabled={!!busy || !report || report.errors.length > 0 || report.committed} onClick={() => run(true)}>Import</button>
          </div>
        </section>
      )}

      {report && (
        <section className="space-y-3">
          {report.committed ? (
            <Notice tone="good">Imported {report.valid_slots} periods for {report.sections.join(", ")}.</Notice>
          ) : report.errors.length === 0 ? (
            <Notice tone="good">{report.valid_slots} periods are valid for {report.sections.join(", ")}. Press Import to save.</Notice>
          ) : (
            <Notice tone="bad">{report.errors.length} problem(s). Fix the names above or the PDF, then check again.</Notice>
          )}
          {report.new_faculty.length > 0 && <p className="text-sm">New faculty accounts: {report.new_faculty.join(", ")}</p>}
          {report.errors.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm text-bad-ink">{report.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        </section>
      )}
    </div>
  );
}
