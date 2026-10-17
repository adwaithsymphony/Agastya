import { useState } from "react";
import { Button, ConfirmDialog, EmptyState, ErrorState, Field, Loading, PageHeader, Panel, StatusBadge, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { invalidate, useApi, useMutation } from "../../lib/data";
import { fmtDate, fmtDateTime, fmtKg, human } from "../../lib/format";
import type { Assignment } from "../../lib/types";

type Delivery = Assignment & { batch: { id: number; code: string; crop: string; grade: string; quantity_kg: number; harvested_on: string; source_district: string | null; status: string } };

function DeliveryRow({ d }: { d: Delivery }) {
  const toast = useToast();
  const [mode, setMode] = useState<null | "cancel" | "receive">(null);
  const [text, setText] = useState("");
  const cancel = useMutation(() => api(`/buyers/me/deliveries/${d.id}/cancel`, { body: { reason: text } }));
  const receive = useMutation(() => api(`/shipments/${d.shipment!.id}/status`, { body: { to: "delivered", note: text || null } }));
  const done = (m: string) => { setMode(null); toast(m); invalidate("/buyers/me", "/dashboard", "/buyer-demands"); };
  const active = d.status === "active";
  return (
    <li className="rounded-lg border border-line bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{d.batch.code}: {fmtKg(d.quantity_kg)} {d.batch.crop}</span><StatusBadge status={d.status} /></div>
          <div className="text-sm">Grade {d.batch.grade}, harvested {fmtDate(d.batch.harvested_on)}{d.batch.source_district ? `, from ${d.batch.source_district}` : ""}</div>
          {d.shipment && <div className="flex items-center gap-2 text-sm">Shipment <StatusBadge status={d.shipment.status} /> {d.shipment.status === "scheduled" && <span className="text-muted">for {fmtDate(d.shipment.scheduled_date)}</span>}</div>}
          {d.end_reason && !active && <p className="text-[13px] text-muted">{human(d.status)}: {d.end_reason} ({fmtDateTime(d.ended_at)})</p>}
        </div>
        {active && (
          <div className="flex flex-wrap gap-2">
            {d.shipment?.status === "dispatched" && <Button size="sm" onClick={() => { setText(""); setMode("receive"); }}>Confirm received</Button>}
            {d.shipment?.status !== "delivered" && <Button size="sm" variant="quiet" onClick={() => { setText(""); setMode("cancel"); }}>Cancel delivery</Button>}
          </div>
        )}
      </div>
      <ConfirmDialog open={mode === "cancel"} onClose={() => setMode(null)} title="Cancel this delivery?" confirmLabel="Cancel delivery" tone="danger" pending={cancel.pending} error={cancel.error}
        onConfirm={async () => { if (await cancel.run(undefined)) done("Delivery cancelled; the farmer has been notified"); }}>
        <p>The farmer will be asked to find another destination for this produce. Please give a reason.</p>
        <Field label="Reason" htmlFor={`cr${d.id}`}><Textarea id={`cr${d.id}`} rows={2} value={text} onChange={(e) => setText(e.target.value)} /></Field>
      </ConfirmDialog>
      <ConfirmDialog open={mode === "receive"} onClose={() => setMode(null)} title="Confirm you received this batch?" confirmLabel="Confirm received" pending={receive.pending} error={receive.error}
        onConfirm={async () => { if (await receive.run(undefined)) done("Delivery confirmed"); }}>
        <Field label="Condition on arrival" htmlFor={`rn${d.id}`} optional><Textarea id={`rn${d.id}`} rows={2} value={text} onChange={(e) => setText(e.target.value)} /></Field>
      </ConfirmDialog>
    </li>
  );
}

export default function BuyerDeliveries() {
  const { data, error, loading, reload } = useApi<Delivery[]>("/buyers/me/deliveries");
  const active = data?.filter((d) => d.status === "active") ?? [];
  const past = data?.filter((d) => d.status !== "active") ?? [];
  return (
    <>
      <PageHeader title="Deliveries" subtitle="Produce assigned to you, and what happened to earlier assignments." />
      {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="space-y-6">
          <Panel title="Incoming">{active.length ? <ul className="space-y-3">{active.map((d) => <DeliveryRow key={d.id} d={d} />)}</ul> : <EmptyState icon="Truck" title="No incoming deliveries" />}</Panel>
          <Panel title="Past">{past.length ? <ul className="space-y-3">{past.map((d) => <DeliveryRow key={d.id} d={d} />)}</ul> : <p className="text-sm text-muted">No past deliveries.</p>}</Panel>
        </div>
      )}
    </>
  );
}
