import { useState } from "react";
import { UrgencyBadge } from "../components/domain";
import { Button, Dialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, Td, Textarea, Th, cn } from "../components/ui";
import { api } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { fmtDate, fmtKg, todayISO } from "../lib/format";
import { Link, useNavigate, useSearchParam } from "../lib/router";
import type { Batch, CycleBrief } from "../lib/types";

function BatchDialog({ onClose, preCycle }: { onClose: () => void; preCycle: string | null }) {
  const navigate = useNavigate();
  const { data: cycles } = useApi<CycleBrief[]>("/crop-cycles?status=open");
  const [f, setF] = useState({ crop_cycle_id: preCycle ?? "", quantity_value: "", unit: "kg", grade: "A", harvested_on: todayISO(), shelf_life_days: "", storage_condition: "", available_from: "", deliver_by: "", quality_notes: "" });
  const m = useMutation(() =>
    api<Batch>("/batches", {
      body: {
        crop_cycle_id: Number(f.crop_cycle_id || cycles?.[0]?.id), quantity_value: f.quantity_value, unit: f.unit, grade: f.grade, harvested_on: f.harvested_on,
        shelf_life_days: f.shelf_life_days ? Number(f.shelf_life_days) : null, storage_condition: f.storage_condition || null,
        available_from: f.available_from || null, deliver_by: f.deliver_by || null, quality_notes: f.quality_notes || null,
      },
    }),
  );
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} wide title="Record a harvested batch" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} disabled={!f.quantity_value || !cycles?.length} onClick={async () => { const r = await m.run(undefined); if (r) { invalidate("/batches", "/dashboard"); navigate(`/app/batches/${r.id}`); } }}>Save batch</Button></>}>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-3">
          <Field label="Crop cycle" htmlFor="bc">
            <Select id="bc" value={f.crop_cycle_id} onChange={(e) => setF({ ...f, crop_cycle_id: e.target.value })}>
              {cycles?.map((c) => <option key={c.id} value={c.id}>{c.crop.name} — {c.field.name}, {c.farm.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Quantity" htmlFor="bq" error={errs.quantity_value}><Input id="bq" type="number" min="0" step="0.01" value={f.quantity_value} onChange={(e) => setF({ ...f, quantity_value: e.target.value })} /></Field>
        <Field label="Unit" htmlFor="bu"><Select id="bu" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}><option value="kg">kg</option><option value="quintal">quintal (100 kg)</option><option value="tonne">tonne</option></Select></Field>
        <Field label="Grade" htmlFor="bg"><Select id="bg" value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })}>{["A", "B", "C"].map((g) => <option key={g}>{g}</option>)}</Select></Field>
        <Field label="Harvested on" htmlFor="bh" error={errs.harvested_on}><Input id="bh" type="date" max={todayISO()} value={f.harvested_on} onChange={(e) => setF({ ...f, harvested_on: e.target.value })} /></Field>
        <Field label="Shelf life (days)" htmlFor="bs" optional hint="Leave blank if unknown."><Input id="bs" type="number" min="1" value={f.shelf_life_days} onChange={(e) => setF({ ...f, shelf_life_days: e.target.value })} /></Field>
        <Field label="Storage" htmlFor="bst" optional><Input id="bst" value={f.storage_condition} onChange={(e) => setF({ ...f, storage_condition: e.target.value })} placeholder="e.g. Cool room, 10 °C" /></Field>
        <Field label="Available from" htmlFor="ba" optional><Input id="ba" type="date" value={f.available_from} onChange={(e) => setF({ ...f, available_from: e.target.value })} /></Field>
        <Field label="Deliver by" htmlFor="bd" optional><Input id="bd" type="date" value={f.deliver_by} onChange={(e) => setF({ ...f, deliver_by: e.target.value })} /></Field>
        <div className="sm:col-span-3"><Field label="Quality notes" htmlFor="bn" optional><Textarea id="bn" rows={2} value={f.quality_notes} onChange={(e) => setF({ ...f, quality_notes: e.target.value })} /></Field></div>
      </div>
      <p className="mt-3 text-xs text-muted">The harvest date is checked against recorded pre-harvest intervals for this crop cycle.</p>
      <div className="mt-3"><FormError error={m.error} /></div>
    </Dialog>
  );
}

export default function Batches() {
  const pre = useSearchParam("cycle");
  const [open, setOpen] = useState(!!pre);
  const [filter, setFilter] = useState<"active" | "all">("active");
  const { data, error, loading, reload } = useApi<Batch[]>(`/batches${filter === "active" ? "?status=active" : ""}`);
  return (
    <>
      <PageHeader title="Produce & buyers" subtitle="Harvested batches, their buyers and deliveries." actions={<Button icon="Plus" onClick={() => setOpen(true)}>Record batch</Button>} />
      <Panel pad={false} title="Batches" actions={
        <div role="tablist" className="flex rounded-full bg-cream p-0.5 text-[13px] font-semibold">
          {(["active", "all"] as const).map((k) => <button key={k} role="tab" aria-selected={filter === k} onClick={() => setFilter(k)} className={cn("rounded-full px-3 py-1", filter === k ? "bg-paper shadow-soft" : "text-muted")}>{k === "active" ? "Active" : "All"}</button>)}
        </div>
      }>
        {loading && !data ? <div className="p-5"><Loading /></div> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : !data?.length ? (
          <EmptyState icon="Package" title="No batches yet" body="Record a harvested batch to match it with buyers." action={<Button icon="Plus" onClick={() => setOpen(true)}>Record batch</Button>} />
        ) : (
          <Table>
            <thead><tr><Th>Batch</Th><Th>Quantity</Th><Th>Harvested</Th><Th>Shelf life</Th><Th>Destination</Th><Th>Status</Th></tr></thead>
            <tbody>
              {data.map((b) => (
                <tr key={b.id} className="hover:bg-cream/60">
                  <Td><Link to={`/app/batches/${b.id}`} className="font-semibold hover:text-forest">{b.code}</Link><div className="text-xs text-muted">{b.crop.name}, grade {b.grade}</div></Td>
                  <Td className="num">{fmtKg(b.quantity_kg)}</Td>
                  <Td>{fmtDate(b.harvested_on)}</Td>
                  <Td><UrgencyBadge urgency={b.urgency} daysLeft={b.days_left} /></Td>
                  <Td>{b.current_assignment?.buyer.display_name ?? <span className="text-muted">—</span>}</Td>
                  <Td><StatusBadge status={b.status} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      {open && <BatchDialog preCycle={pre} onClose={() => setOpen(false)} />}
    </>
  );
}
