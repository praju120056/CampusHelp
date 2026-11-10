import { Suspense, type ReactNode } from "react";
import { Shell } from "@/components/shell";

export default function StaffLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted">Loading…</p>}>
      <Shell>{children}</Shell>
    </Suspense>
  );
}
