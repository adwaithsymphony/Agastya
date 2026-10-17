import { useState } from "react";
import { Button, Dialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, Td, Textarea, Th, cn, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { invalidate, useApi, useMutation } from "../../lib/data";
import { addDays, fmtDate, fmtKg, fmtShort, todayISO } from "../../lib/format";
import type { Crop, Demand } from "../../lib/types";

function DemandDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const { data: crops } = useApi<Crop[]>("/crops");
  const t = todayISO();
  const [f, setF] = useState({ crop_id: "", grades: ["A", "B"], quantity_kg: "", valid_from: t, valid_until: addDays(t, 14), delivery_start: t, delivery_end: addDays(t, 7), max_distance_km: "", notes: "" });
  const m = useMutation(() => api("/buyer-demands", { body: { crop_id: Number(f.crop_id), accepted_grades: f.grades, quantity_kg: f.quantity_kg, valid_from: f.valid_from, valid_until: f.valid_until, delivery_start: f.delivery_start, delivery_end: f.delivery_end, max_distance_km: f.max_distance_km ? Number(f.max_distance_km) : null, notes: f.notes || null } }));
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} wide title="Post demand" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} disabled={!f.crop_id || !f.quantity_kg || !f.grades.length} onClick={async () => { if (await m.run(undefined)) { toast("Demand posted"); invalidate("/buyer-demands", "/dashboard"); onClose(); } }}>Post demand</Button></>}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Crop" htmlFor="dc"><Select id="dc" value={f.crop_id} onChange={(e) => setF({ ...f, crop_id: e.target.value })}><option value="">Choose</option>{crops?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Quantity (kg)" htmlFor="dq" error={errs.quantity_kg}><Input id="dq" type="number" min="1" value={f.quantity_kg} onChange={(e) => setF({ ...f, quantity_kg: e.target.value })} /></Field>
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-semibold">Grades accepted</legend>
          <div className="flex gap-2">
            {["A", "B", "C"].map((g) => {
              const on = f.grades.includes(g);
              return <button key={g} type="button" aria-pressed={on} onClick={() => setF({ ...f, grades: on ? f.grades.filter((x) => x !== g) : [...f.grades, g] })} className={cn("h-10 w-12 rounded-md border text-sm font-bold", on ? "border-forest bg-forest text-white" : "border-line-strong bg-white")}>{g}</button>;
            })}
          </div>
        </fieldset>
        <Field label="Listing valid from" htmlFor="dvf"><Input id="dvf" type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></Field>
        <Field label="Valid until" htmlFor="dvu" error={errs[""]}><Input id="dvu" type="date" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} /></Field>
        <Field label="Max distance (km)" htmlFor="dmd" optional><Input id="dmd" type="number" min="1" value={f.max_distance_km} onChange={(e) => setF({ ...f, max_distance_km: e.target.value })} /></Field>
        <Field label="Can receive from" htmlFor="dds"><Input id="dds" type="date" value={f.delivery_start} onChange={(e) => setF({ ...f, delivery_start: e.target.value })} /></Field>
        <Field label="Can receive until" htmlFor="dde"><Input id="dde" type="date" value={f.delivery_end} onChange={(e) => setF({ ...f, delivery_end: e.target.value })} /></Field>
        <div />
        <div className="sm:col-span-3"><Field label="Notes" htmlFor="dn" optional><Textarea id="dn" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field></div>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

export default function BuyerDemands() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Demand[]>("/buyer-demands");
  const [open, setOpen] = useState(false);
  const status = useMutation(({ id, s }: { id: number; s: string }) => api(`/buyer-demands/${id}/status`, { body: { status: s } }));
  return (
    <>
      <PageHeader title="Demand listings" subtitle="What you can take in. Farmers' rerouting matches against these." actions={<Button icon="Plus" onClick={() => setOpen(true)}>Post demand</Button>} />
      <FormError error={status.error} />
      <Panel pad={false}>
        {loading && !data ? <div className="p-5"><Loading /></div> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : !data?.length ? (
          <EmptyState icon="Store" title="No demand posted" body="Post what you can buy so batches needing a destination can be routed to you." action={<Button icon="Plus" onClick={() => setOpen(true)}>Post demand</Button>} />
        ) : (
          <Table>
            <thead><tr><Th>Crop</Th><Th>Grades</Th><Th>Filled</Th><Th>Receiving</Th><Th>Valid until</Th><Th>Status</Th><Th /></tr></thead>
            <tbody>
              {data.map((d) => {
                const filled = d.quantity_kg ? d.allocated_kg / d.quantity_kg : 0;
                return (
                  <tr key={d.id}>
                    <Td className="font-semibold">{d.crop.name}</Td>
                    <Td>{d.accepted_grades.join(", ")}</Td>
                    <Td className="min-w-44">
                      <div className="num text-[13px]">{fmtKg(d.allocated_kg)} of {fmtKg(d.quantity_kg)}</div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sage-pale"><div className="h-full bg-forest" style={{ width: `${Math.min(filled, 1) * 100}%` }} /></div>
                    </Td>
                    <Td>{fmtShort(d.delivery_start)} – {fmtShort(d.delivery_end)}{d.max_distance_km ? <div className="text-xs text-muted">within {d.max_distance_km} km</div> : null}</Td>
                    <Td>{fmtDate(d.valid_until)}</Td>
                    <Td><StatusBadge status={d.valid_until < todayISO() && d.status === "open" ? "closed" : d.status} label={d.valid_until < todayISO() && d.status === "open" ? "Expired" : undefined} /></Td>
                    <Td className="whitespace-nowrap">
                      {d.status === "open" && <Button size="sm" variant="quiet" onClick={async () => { if (await status.run({ id: d.id, s: "paused" })) { toast("Listing paused"); reload(); } }}>Pause</Button>}
                      {d.status === "paused" && <Button size="sm" variant="quiet" onClick={async () => { if (await status.run({ id: d.id, s: "open" })) { toast("Listing reopened"); reload(); } }}>Reopen</Button>}
                      {d.status !== "closed" && <Button size="sm" variant="quiet" onClick={async () => { if (await status.run({ id: d.id, s: "closed" })) { toast("Listing closed"); reload(); } }}>Close</Button>}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>
      {open && <DemandDialog onClose={() => { setOpen(false); reload(); }} />}
    </>
  );
}
