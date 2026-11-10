"use client";
// B2: printable QR sheet. Each code holds only the location ID; print and "Save as PDF" from the browser.
import { useEffect, useState } from "react";
import { Icon, Loading, Notice, PageHeader } from "@/components/ui";
import { api, apiBase, errorText } from "@/lib/api";

type Loc = { code: string; block: string; floor: number; room_name: string; kind: string; qr_url: string };

export default function QrSheet() {
  const [locs, setLocs] = useState<Loc[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Loc[]>("/locations").then(setLocs).catch((e) => setError(errorText(e)));
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="Module B"
        title="QR codes"
        actions={<button className="btn btn-primary" onClick={() => window.print()}><Icon name="print" /> Print sheet</button>}
      >
        One label per room. The QR holds only the location code, so room details can change without reprinting.
      </PageHeader>
      {locs?.[0] && (
        <div className="no-print mb-4">
          <Notice tone="info">
            Codes point to <span className="mono">{locs[0].qr_url.replace(/\/r\/.*$/, "")}</span>. If the laptop&apos;s Wi-Fi address changes,
            update PUBLIC_BASE_URL in .env and print again.
          </Notice>
        </div>
      )}
      {error && <Notice tone="bad">{error}</Notice>}
      {!locs ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 print:grid-cols-3">
          {locs.map((l) => (
            <div key={l.code} className="break-inside-avoid rounded-md border border-rule-strong bg-white p-3 text-center">
              <img src={`${apiBase()}/locations/${l.code}/qr.png`} alt={`QR code for ${l.room_name}`} className="mx-auto w-full max-w-40" />
              <div className="mt-2 font-semibold leading-tight">{l.room_name}</div>
              <div className="text-xs text-ink-2">Block {l.block} · Floor {l.floor}</div>
              <div className="mono mt-1 text-[11px] text-muted">{l.code}</div>
              <div className="mt-2 text-[11px] font-medium text-accent">Scan to report a problem</div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
