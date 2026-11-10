import { LiveMap } from "@/components/live-map";
import { PageHeader } from "@/components/ui";

export default function MapPage() {
  return (
    <>
      <PageHeader eyebrow="Module B · Maintenance" title="Live ticket map">
        Rooms change colour the moment a ticket is reported, picked up, escalated or fixed.
      </PageHeader>
      <LiveMap />
    </>
  );
}
