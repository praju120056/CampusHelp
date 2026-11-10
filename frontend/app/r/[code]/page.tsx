import { Suspense } from "react";
import ScanForm from "./scan-form";

export default function ScanPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted">Loading…</p>}>
      <ScanForm />
    </Suspense>
  );
}
