import { useState } from "react";
import { KV, UrgencyBadge } from "../components/domain";
import { Icon } from "../components/icons";
import { Badge, Button, ConfirmDialog, ProvenanceBadge, Dialog, EmptyState, ErrorState, Field, FormError, Help, Input, Loading, PageHeader, Panel, StatusBadge, Textarea, cn, useToast } from "../components/ui";
import { api, idempotencyKey } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { fmtDate, fmtDateTime, fmtKg, fmtShort, human } from "../lib/format";
import { useParams } from "../lib/router";
import type { Batch, Match, RerouteRun } from "../lib/types";

const COMP = [
  { key: "timing", label: "Timing", max: 35, cls: "bg-forest" },
  { key: "distance", label: "Distance", max: 30, cls: "bg-sage" },
  { key: "fit", label: "Quantity fit", max: 25, cls: "bg-earth" },
  { key: "grade", label: "Grade", max: 10, cls: "bg-water" },
];

function ScoreBar({ m }: { m: Match }) {
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-[#ece6d8]" role="img" aria-label={`Score ${m.score} of 100`}>
        {COMP.map((c) => <div key={c.key} className={c.cls} style={{ width: `${m.components[c.key] ?? 0}%` }} />)}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-muted">
        {COMP.map((c) => <span key={c.key} className="flex items-center gap-1"><span className={cn("size-2 rounded-sm", c.cls)} />{c.label} {Math.round(m.components[c.key] ?? 0)}/{c.max}</span>)}
      </div>
    </div>
  );
}

function Recommendations({ run, onChoose }: { run: RerouteRun; onChoose: (m: Match) => void }) {
  const [showExcluded, setShowExcluded] = useState(false);
  const eligible = run.matches.filter((m) => m.eligible);
  const excluded = run.matches.filter((m) => !m.eligible);
  return (
    <Panel
      title="Recommended destinations"
      subtitle={`Computed ${fmtDateTime(run.created_at)}${run.trigger !== "unassigned" ? ` after ${human(run.trigger).toLowerCase()}` : ""}`}
      actions={<Help label="How buyers are ranked">Buyers must take this crop and grade, have enough open demand, a delivery window before the batch's sell-by date, and be within their distance limit. Eligible buyers are scored on timing, distance, how much of their demand this batch fills, and grade fit. This is a rule-based score, not a prediction.</Help>}
    >
      {eligible.length ? (
        <ol className="space-y-3">
          {eligible.map((m) => (
            <li key={m.id} className={cn("rounded-lg border p-4", m.rank === 1 ? "border-forest bg-white shadow-soft" : "border-line bg-white")}>
              <div className="flex flex-wrap items-start gap-4">
                <div className="grid size-10 shrink-0 place-items-center rounded-full bg-forest text-sm font-bold text-white">{m.rank}</div>
                <div className="min-w-0 flex-1 space-y-2.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <span className="font-semibold">{m.buyer.display_name}</span>
                      <span className="ml-2 text-xs text-muted">{m.buyer.buyer_type}, {m.buyer.district}</span>
                    </div>
                    <span className="num text-sm font-bold text-forest-ink">{m.score}<span className="font-medium text-muted">/100</span></span>
                  </div>
                  <ScoreBar m={m} />
                  <div className="grid gap-2 text-[13px] sm:grid-cols-2">
                    <ul className="space-y-1">{m.reasons.map((r) => <li key={r} className="flex gap-1.5"><Icon name="Check" size={14} className="mt-0.5 shrink-0 text-forest" />{r}</li>)}</ul>
                    {m.tradeoffs.length > 0 && <ul className="space-y-1 text-[#7a5212]">{m.tradeoffs.map((r) => <li key={r} className="flex gap-1.5"><Icon name="TriangleAlert" size={14} className="mt-0.5 shrink-0" />{r}</li>)}</ul>}
                  </div>
                  <div className="text-xs text-muted">Receives {fmtShort(m.demand.delivery_start)} – {fmtShort(m.demand.delivery_end)}; grades {m.demand.accepted_grades.join(", ")}; {human(m.buyer.delivery_preference).toLowerCase()}</div>
                </div>
                <Button size="sm" variant={m.rank === 1 ? "primary" : "secondary"} onClick={() => onChoose(m)}>Choose</Button>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState icon="Store" title="No buyer can take this batch right now" body="Every current demand listing fails at least one requirement. See the reasons below, or split the batch and try again later." />
      )}
      {excluded.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <button className="flex items-center gap-1.5 text-[13px] font-semibold text-muted hover:text-charcoal" aria-expanded={showExcluded} onClick={() => setShowExcluded((s) => !s)}>
            <Icon name={showExcluded ? "ChevronDown" : "ChevronRight"} size={14} /> {excluded.length} buyer{excluded.length > 1 ? "s" : ""} not eligible
          </button>
          {showExcluded && (
            <ul className="mt-2 space-y-1.5 text-[13px]">
              {excluded.map((m) => <li key={m.id}><span className="font-semibold">{m.buyer.display_name}</span> <span className="text-muted">— {m.exclusions.join("; ")}</span></li>)}
            </ul>
          )}
        </div>
      )}
      <p className="mt-4 text-xs text-muted">Distances are straight-line estimates from recorded locations. Transport costs and market prices are not included.</p>
    </Panel>
  );
}

export default function BatchDetail() {
  const { batchId } = useParams<{ batchId: string }>();
  const toast = useToast();
  const path = `/batches/${batchId}`;
  const { data: b, error, loading, reload } = useApi<Batch>(path);
  const [choice, setChoice] = useState<Match | null>(null);
  const [key, setKey] = useState(idempotencyKey());
  const [disruption, setDisruption] = useState(false);
  const [note, setNote] = useState("");
  const [closing, setClosing] = useState(false);
  const [closeReason, setCloseReason] = useState("");
  const refresh = () => invalidate("/batches", "/dashboard", "/notifications");

  const find = useMutation((body: { trigger: string; note?: string }) => api<RerouteRun>(`/batches/${batchId}/buyer-matches`, { body }));
  const confirm = useMutation(() => api<Batch>(`/batches/${batchId}/destination`, { body: { match_id: choice!.id, version: b!.version }, headers: { "Idempotency-Key": key } }));
  const ship = useMutation((shipmentId: number) => api(`/shipments/${shipmentId}/status`, { body: { to: "dispatched" } }));
  const close = useMutation(() => api(`/batches/${batchId}/close`, { body: { reason: closeReason } }));

  if (loading && !b) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!b) return null;
  const cur = b.current_assignment;
  const routable = ["unassigned", "needs_destination", "assigned", "in_transit"].includes(b.status);
  const needs = b.status === "unassigned" || b.status === "needs_destination";
  const run = b.latest_run && (needs || b.latest_run.trigger === "disruption") ? b.latest_run : null;
  const showRun = run && run.matches.length > 0 && (needs || b.status === "needs_destination");
  const trigger = b.status === "needs_destination" ? (b.assignments?.[0]?.status === "cancelled_by_buyer" ? "buyer_cancelled" : "disruption") : "unassigned";

  return (
    <>
      <PageHeader
        back={{ to: "/app/batches", label: "Produce & buyers" }}
        title={<span className="flex flex-wrap items-center gap-3">{b.code} <StatusBadge status={b.status} /></span>}
        subtitle={`${fmtKg(b.quantity_kg)} ${b.crop.name}, grade ${b.grade}${b.source ? ` — ${b.source.field}, ${b.source.farm}` : ""}`}
        actions={
          <>
            {(b.status === "assigned" || b.status === "in_transit") && <Button variant="secondary" icon="TriangleAlert" onClick={() => { setNote(""); setDisruption(true); }}>Report disruption</Button>}
            {needs && <Button icon="Search" loading={find.pending} onClick={async () => { if (await find.run({ trigger })) reload(); }}>{run ? "Refresh options" : "Find buyers"}</Button>}
          </>
        }
      />
      <FormError error={find.error} />
      {b.status === "needs_destination" && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">
          <Icon name="TriangleAlert" size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">This batch needs a new destination.</p>
            {b.assignments?.[0]?.end_reason && <p className="text-charcoal">{b.assignments[0].buyer.display_name}: {b.assignments[0].end_reason}</p>}
          </div>
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          {showRun ? (
            <Recommendations run={run!} onChoose={(m) => { setKey(idempotencyKey()); confirm.setError(null); setChoice(m); }} />
          ) : needs ? (
            <Panel><EmptyState icon="Search" title="Find buyers for this batch" body="AGASTYA checks every open demand listing against this batch and ranks the ones that fit." action={<Button icon="Search" loading={find.pending} onClick={async () => { if (await find.run({ trigger })) reload(); }}>Find buyers</Button>} /></Panel>
          ) : null}

          {cur && (
            <Panel title="Current destination">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-lg font-bold text-forest-ink">{cur.buyer.display_name}</div>
                  <div className="text-sm text-muted">{cur.buyer.buyer_type}, {cur.buyer.district} — {fmtKg(cur.quantity_kg)}</div>
                  <div className="mt-1 text-xs text-muted">Assigned {fmtDateTime(cur.assigned_at)} ({human(cur.reason).toLowerCase()})</div>
                </div>
                {cur.shipment?.status === "scheduled" && <Button icon="Truck" loading={ship.pending} onClick={async () => { if (await ship.run(cur.shipment!.id)) { toast("Marked as dispatched"); refresh(); } }}>Mark dispatched</Button>}
              </div>
              {cur.shipment && (
                <ol className="mt-5 flex flex-wrap gap-2">
                  {["scheduled", "dispatched", "delivered"].map((s, i) => {
                    const reached = ["scheduled", "dispatched", "delivered"].indexOf(cur.shipment!.status) >= i;
                    const ev = cur.shipment!.events.find((e) => e.status === s);
                    return (
                      <li key={s} className={cn("flex-1 rounded-md border px-3 py-2 text-[13px]", reached ? "border-forest bg-sage-pale" : "border-line bg-white text-muted")}>
                        <div className="font-semibold">{human(s)}</div>
                        <div className="text-xs">{ev ? fmtDateTime(ev.at) : s === "scheduled" ? fmtDate(cur.shipment!.scheduled_date) : "—"}</div>
                      </li>
                    );
                  })}
                </ol>
              )}
              <FormError error={ship.error} />
            </Panel>
          )}

          <Panel title="Destination history" subtitle="Earlier assignments are kept, never overwritten.">
            {b.assignments?.length ? (
              <ol className="space-y-3">
                {b.assignments.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-line/60 pb-3 last:border-0 last:pb-0">
                    <div className="text-sm">
                      <div className="font-semibold">{a.buyer.display_name}</div>
                      <div className="text-xs text-muted">{fmtDateTime(a.assigned_at)}{a.ended_at ? ` to ${fmtDateTime(a.ended_at)}` : ""} — {human(a.reason).toLowerCase()}</div>
                      {a.end_reason && a.status !== "active" && <div className="text-xs text-charcoal">{a.end_reason}</div>}
                    </div>
                    <StatusBadge status={a.status} />
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-muted">Not assigned yet.</p>}
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Batch">
            <div className="grid grid-cols-2 gap-4">
              <KV label="Quantity">{fmtKg(b.quantity_kg)}{b.unit !== "kg" ? <span className="block text-xs font-normal text-muted">{b.quantity_value} {b.unit}</span> : null}</KV>
              <KV label="Grade">{b.grade}</KV>
              <KV label="Harvested">{fmtDate(b.harvested_on)}</KV>
              <KV label="Available from">{fmtDate(b.available_from)}</KV>
              <KV label="Sell by">{b.sell_by ? fmtDate(b.sell_by) : "Not known"}</KV>
              <KV label="Shelf life">{b.shelf_life_days ? `${b.shelf_life_days} days (${b.shelf_life_source})` : "Not recorded"}</KV>
              <div className="col-span-2"><KV label="Storage">{b.storage_condition ?? "Not recorded"}</KV></div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <UrgencyBadge urgency={b.urgency} daysLeft={b.days_left} />
              {b.harvest_check_status === "unknown" ? <Badge tone="amber" icon="CircleHelp">Harvest PHI check incomplete</Badge> : <Badge tone="sage">Harvest date passed PHI check</Badge>}
              {b.harvest_check_details?.uses_fictional_reference && <ProvenanceBadge provenance="fictional_sample" />}
            </div>
            {b.quality_notes && <p className="mt-3 text-sm">{b.quality_notes}</p>}
          </Panel>
          {routable && b.status !== "in_transit" && <Button variant="quiet" size="sm" onClick={() => { setCloseReason(""); setClosing(true); }}>Close batch without delivery</Button>}
        </div>
      </div>

      <ConfirmDialog open={!!choice} onClose={() => setChoice(null)} title="Confirm new destination" confirmLabel="Confirm destination" pending={confirm.pending} error={confirm.error}
        onConfirm={async () => { const r = await confirm.run(undefined); if (r) { setChoice(null); toast(`Assigned to ${choice!.buyer.display_name}`); refresh(); reload(); } else reload(); }}>
        {choice && (
          <>
            <p>Send <span className="font-semibold">{fmtKg(b.quantity_kg)} {b.crop.name}</span> (grade {b.grade}) to <span className="font-semibold">{choice.buyer.display_name}</span>, {choice.buyer.district}.</p>
            {cur && <p className="text-muted">The current assignment to {cur.buyer.display_name} will be ended and its shipment cancelled. Both buyers are notified.</p>}
            <p className="text-muted">A delivery is scheduled from {fmtShort(choice.demand.delivery_start)}.</p>
          </>
        )}
      </ConfirmDialog>

      <Dialog open={disruption} onClose={() => setDisruption(false)} title="Report a disruption" footer={<><Button variant="ghost" onClick={() => setDisruption(false)}>Cancel</Button><Button loading={find.pending} disabled={note.trim().length < 3} onClick={async () => { if (await find.run({ trigger: "disruption", note })) { setDisruption(false); toast("Alternatives ready"); refresh(); reload(); } }}>Find alternatives</Button></>}>
        <p className="mb-4 text-sm text-muted">The current buyer stays assigned until you confirm a replacement.</p>
        <Field label="What happened?" htmlFor="dn"><Textarea id="dn" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Highway closed near Sinnar" /></Field>
        <div className="mt-3"><FormError error={find.error} /></div>
      </Dialog>

      <ConfirmDialog open={closing} onClose={() => setClosing(false)} title="Close this batch?" confirmLabel="Close batch" tone="danger" pending={close.pending} error={close.error}
        onConfirm={async () => { if (await close.run(undefined)) { setClosing(false); toast("Batch closed"); refresh(); reload(); } }}>
        <p>Use this when the produce was sold outside AGASTYA, used, or discarded. Any scheduled delivery is withdrawn.</p>
        <Field label="Reason" htmlFor="cr"><Input id="cr" value={closeReason} onChange={(e) => setCloseReason(e.target.value)} /></Field>
      </ConfirmDialog>
    </>
  );
}
