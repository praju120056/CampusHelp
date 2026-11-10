import { Suspense } from "react";
import Respond from "./respond";

export default function RespondPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted">Loading…</p>}>
      <Respond />
    </Suspense>
  );
}
