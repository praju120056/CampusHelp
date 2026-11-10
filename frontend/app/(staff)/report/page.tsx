import { Suspense } from "react";
import Report from "./report";

export default function ReportPage() {
  return (
    <Suspense fallback={<p className="py-8 text-sm text-muted">Loading…</p>}>
      <Report />
    </Suspense>
  );
}
