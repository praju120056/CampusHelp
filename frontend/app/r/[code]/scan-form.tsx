"use client";
// B3/B4: the no-login report form a QR code opens. Scan → describe → send.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Icon, Notice, PriorityTag } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { CATEGORIES, label } from "@/lib/format";

type Location = { code: string; block: string; floor: number; room_name: string; kind: string; assets: string[] };
type Result = {
  ref: string | null;
  duplicate: boolean;
  report_count?: number;
  category?: string;
  priority?: string;
  summary?: string;
  message: string;
};

/** Phone photos are often 4–8 MB; shrink to ≤1600 px JPEG before upload. */
async function shrink(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve) => canvas.toBlob((b) => resolve(b ?? file), "image/jpeg", 0.82));
  } catch {
    return file;
  }
}

export default function ScanForm() {
  const { code } = useParams<{ code: string }>();
  const [loc, setLoc] = useState<Location | null>(null);
  const [loadError, setLoadError] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [showContact, setShowContact] = useState(false);
  const [contact, setContact] = useState({ name: "", phone: "", email: "" });
  const [honeypot, setHoneypot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    api<Location>(`/locations/${encodeURIComponent(code)}`, { auth: false })
      .then(setLoc)
      .catch((e) => setLoadError(errorText(e)));
  }, [code]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData();
    form.set("location_code", code);
    form.set("description", description);
    if (category) form.set("category", category);
    if (contact.name) form.set("reporter_name", contact.name);
    if (contact.phone) form.set("reporter_phone", contact.phone);
    if (contact.email) form.set("reporter_email", contact.email);
    if (honeypot) form.set("website", honeypot);
    if (photo) form.set("photo", await shrink(photo), "photo.jpg");
    try {
      setResult(await api<Result>("/tickets", { form, auth: false }));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-md px-4 py-10">
        <Notice tone="bad">{loadError}</Notice>
      </main>
    );
  }
  if (!loc) return <p className="p-6 text-sm text-muted">Loading location…</p>;

  if (result) {
    return (
      <main className="mx-auto max-w-md px-4 py-10">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-good-soft text-good-ink">
          <Icon name="check" size={26} />
        </div>
        <h1 className="text-2xl font-semibold">{result.duplicate ? "Already reported" : "Report sent"}</h1>
        <p className="mt-2 text-ink-2">{result.message}</p>
        {result.ref && (
          <div className="mt-6 space-y-3 border-y border-rule py-4">
            <div>
              <div className="eyebrow">Ticket number</div>
              <div className="mono text-3xl font-semibold tracking-wider">{result.ref}</div>
            </div>
            {result.duplicate && result.report_count && (
              <p className="text-sm text-ink-2">{result.report_count} people have reported this. It is already with the team.</p>
            )}
            {!result.duplicate && result.category && (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-ink-2">Sent to</span>
                <strong>{label(CATEGORIES, result.category)}</strong>
                {result.priority && <PriorityTag priority={result.priority} />}
              </div>
            )}
          </div>
        )}
        {result.ref && (
          <Link href={`/t/${result.ref}`} className="btn btn-primary mt-6 w-full">Track this ticket</Link>
        )}
        <p className="mt-4 text-center text-xs text-muted">Save or screenshot the ticket number to check later.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-md px-4 pb-28 pt-6">
      <div className="eyebrow">Report a problem</div>
      <div className="mt-2 border-y border-rule py-3">
        <div className="text-xl font-semibold">{loc.room_name}</div>
        <div className="mt-0.5 text-sm text-ink-2">
          Block {loc.block} · Floor {loc.floor} · <span className="mono">{loc.code}</span>
        </div>
      </div>

      <form id="report" onSubmit={submit} className="mt-5 space-y-5">
        <div>
          <label className="label" htmlFor="desc">What is wrong?</label>
          <textarea
            id="desc"
            className="field"
            rows={4}
            required
            minLength={5}
            maxLength={2000}
            placeholder="e.g. Tap leaking near the second basin"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <fieldset>
          <legend className="label">Type (optional)</legend>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="chip" aria-pressed={category === ""} onClick={() => setCategory("")}>
              <Icon name="spark" size={14} /> Let AI decide
            </button>
            {CATEGORIES.map((c) => (
              <button key={c.value} type="button" className="chip" aria-pressed={category === c.value}
                onClick={() => setCategory(c.value)}>
                {c.label}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          <span className="label">Photo (optional)</span>
          <label className="btn w-full cursor-pointer">
            <Icon name="camera" />
            {photo ? `Photo added: ${photo.name.slice(0, 24)}` : "Take or choose a photo"}
            <input type="file" accept="image/*" capture="environment" className="sr-only"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </label>
        </div>

        <div>
          <button type="button" className="text-sm font-medium text-accent underline underline-offset-2"
            onClick={() => setShowContact((v) => !v)} aria-expanded={showContact}>
            {showContact ? "Hide contact details" : "Add your contact (optional)"}
          </button>
          {showContact && (
            <div className="mt-3 space-y-3">
              <input className="field" placeholder="Name" autoComplete="name" value={contact.name}
                onChange={(e) => setContact({ ...contact, name: e.target.value })} />
              <input className="field" placeholder="Phone" inputMode="tel" autoComplete="tel" value={contact.phone}
                onChange={(e) => setContact({ ...contact, phone: e.target.value })} />
              <input className="field" placeholder="Email (we tell you when it is fixed)" type="email" autoComplete="email"
                value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} />
            </div>
          )}
        </div>

        {/* Honeypot: hidden from people, bots fill it in. */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
          <label>Website<input tabIndex={-1} autoComplete="off" value={honeypot} onChange={(e) => setHoneypot(e.target.value)} /></label>
        </div>

        {error && <Notice tone="bad">{error}</Notice>}
      </form>

      <div className="fixed inset-x-0 bottom-0 border-t border-rule bg-surface/95 px-4 py-3 backdrop-blur">
        <button form="report" className="btn btn-primary mx-auto flex w-full max-w-md" disabled={busy || description.trim().length < 5}>
          {busy ? "Sending…" : "Send report"}
        </button>
      </div>
    </main>
  );
}
