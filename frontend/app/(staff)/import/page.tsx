"use client";
// C2: one-time timetable import with validation. Check first, then import.
import { useState } from "react";
import { Icon, Notice, PageHeader } from "@/components/ui";
import { api, download, errorText } from "@/lib/api";

type Report = { rows_read: number; valid_slots: number; errors: string[]; warnings: string[]; new_faculty: string[]; committed: boolean };

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [createMissing, setCreateMissing] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(commit: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.set("file", file);
    form.set("commit", String(commit));
    form.set("create_missing", String(createMissing));
    try {
      setReport(await api<Report>("/timetable/import", { form }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Module C · HOD" title="Import timetable">
        Upload the department timetable as Excel. Names are replaced by Faculty 1…N; the name list stays on this laptop only.
      </PageHeader>
      <Notice tone="warn">Importing replaces the whole timetable. Past work logs are kept.</Notice>
      <div className="mt-6 space-y-4">
        <button className="btn btn-sm" onClick={() => download("/timetable/template.xlsx", "timetable-template.xlsx").catch((e) => setError(errorText(e)))}>
          <Icon name="download" /> Download the template
        </button>
        <div>
          <label className="label" htmlFor="file">Timetable file (.xlsx)</label>
          <input id="file" type="file" accept=".xlsx" className="field py-2" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); }} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={createMissing} onChange={(e) => setCreateMissing(e.target.checked)} />
          Create accounts for faculty not seen before
        </label>
        <div className="flex gap-2">
          <button className="btn" disabled={!file || busy} onClick={() => run(false)}>Check file</button>
          <button className="btn btn-primary" disabled={!file || busy || !report || report.errors.length > 0 || report.committed} onClick={() => run(true)}>
            Import
          </button>
        </div>
        {error && <Notice tone="bad">{error}</Notice>}
        {report && (
          <section className="rule-top space-y-3">
            {report.committed ? (
              <Notice tone="good">Imported {report.valid_slots} periods.</Notice>
            ) : report.errors.length === 0 ? (
              <Notice tone="good">{report.valid_slots} of {report.rows_read} rows are valid. Press Import to replace the timetable.</Notice>
            ) : (
              <Notice tone="bad">{report.errors.length} problem(s) found. Fix them in Excel and check again.</Notice>
            )}
            {report.new_faculty.length > 0 && <p className="text-sm">New faculty accounts: {report.new_faculty.join(", ")}</p>}
            {report.errors.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm text-bad-ink">{report.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
            )}
            {report.warnings.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm text-warn-ink">{report.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
