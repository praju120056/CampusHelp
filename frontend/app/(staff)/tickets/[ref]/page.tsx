import { Suspense } from "react";
import TicketDetail from "./ticket-detail";

export default function TicketDetailPage() {
  return (
    <Suspense fallback={<p className="py-8 text-sm text-muted">Loading…</p>}>
      <TicketDetail />
    </Suspense>
  );
}
