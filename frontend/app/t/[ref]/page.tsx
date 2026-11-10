import { Suspense } from "react";
import TicketStatus from "./ticket-status";

export default function TicketStatusPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted">Loading…</p>}>
      <TicketStatus />
    </Suspense>
  );
}
