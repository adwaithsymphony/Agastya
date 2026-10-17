import { useEffect, useState } from "react";
import { HarvestStrip } from "../components/domain";
import { Icon } from "../components/icons";
import { Badge, Button, ConfirmDialog, ProvenanceBadge, Dialog, EmptyState, ErrorState, Field, FormError, Help, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, Td, Textarea, Th, cn, useToast } from "../components/ui";
import { api } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { productDisplayName, fmtDate, fmtDateTime, fmtShort, human, localInputToISO, nowLocalInput, relDays, todayISO } from "../lib/format";
import { Link, useNavigate, useSearchParam } from "../lib/router";
import type { Application, Assessment, Product } from "../lib/types";

type CycleRef = { id: number; crop: string; field: string; farm: string; expected_harvest_date: string | null; status: string; current_stage: string | null };
type Overview = { cycle: CycleRef; assessment: Assessment; application_count: number }[];
type Detail = { cycle: CycleRef; assessment: Assessment; applications: Application[]; history: { id: number; status: string; earliest_eligible_date: string | null; unresolved_count: number; trigger: string; created_at: string }[] };

function RecordDialog({ cycleId, cropName, onClose }: { cycleId: number; cropName: string; onClose: () => void }) {
  const toast = useToast();
  const { data: crops } = useApi<{ id: number; name: string }[]>("/crops");
  const cropId = crops?.find((c) => c.name === cropName)?.id;
  const { data: products } = useApi<Product[]>(cropId ? `/pesticide-products?crop_id=${cropId}` : null);
  const [f, setF] = useState({ product_id: "", applied_at: nowLocalInput(), dose_value: "", dose_unit: "ml per litre", treated_area_ha: "", application_method: "Knapsack sprayer", target_problem: "", recorded_phi_days: "", notes: "" });
  const product = products?.find((p) => String(p.id) === f.product_id);
  const verified = product?.labels.filter((l) => l.verification_status === "verified" && (!l.valid_until || l.valid_until >= todayISO()));
  const m = useMutation(() =>
    api<{ assessment: Assessment }>("/applications", {
      body: {
        crop_cycle_id: cycleId, product_id: Number(f.product_id), applied_at: localInputToISO(f.applied_at), dose_value: Number(f.dose_value), dose_unit: f.dose_unit,
        treated_area_ha: f.treated_area_ha ? Number(f.treated_area_ha) : null, application_method: f.application_method || null, target_problem: f.target_problem || null,
        recorded_phi_days: f.recorded_phi_days ? Number(f.recorded_phi_days) : null, notes: f.notes || null,
      },
    }),
  );
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} wide title={`Record a spray on ${cropName}`} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} disabled={!f.product_id || !f.dose_value || !f.applied_at} onClick={async () => { const r = await m.run(undefined); if (r) { toast(`Recorded. Status: ${human(r.assessment.status).toLowerCase()}`); invalidate("/harvest-assessments", "/dashboard", "/applications", "/crop-cycles"); onClose(); } }}>Save application</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Product" htmlFor="ap" error={errs.product_id}>
            <Select id="ap" value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })}>
              <option value="">Choose a product</option>
              {products?.map((p) => <option key={p.id} value={p.id}>{productDisplayName(p.trade_name)}{p.active_ingredient ? ` (${p.active_ingredient})` : ""}</option>)}
            </Select>
          </Field>
          {product && (
            <div className={cn("mt-2 rounded-md px-3 py-2 text-[13px]", verified?.length ? "bg-sage-pale text-forest" : "bg-amber-soft text-[#7a5212]")}>
              {verified?.length
                ? verified.some((l) => l.provenance === "fictional_sample")
                  ? `Fictional sample label rule for ${cropName}: ${verified.map((l) => `${l.phi_days} day PHI`).join("; ")}. Fictional sample, not for field use.`
                  : `Verified label rule for ${cropName}: ${verified.map((l) => `${l.phi_days} day PHI (label ${l.label_version})`).join("; ")}.`
                : `No verified label rule for ${cropName}. The application will be saved, but harvest eligibility will show "needs verification" until label data is verified.`}
            </div>
          )}
        </div>
        <Field label="Applied at" htmlFor="aat" error={errs.applied_at} hint="Your local time."><Input id="aat" type="datetime-local" max={nowLocalInput()} value={f.applied_at} onChange={(e) => setF({ ...f, applied_at: e.target.value })} /></Field>
        <div className="grid grid-cols-[1fr_1.2fr] gap-2">
          <Field label="Dose" htmlFor="ad" error={errs.dose_value}><Input id="ad" type="number" min="0" step="0.01" value={f.dose_value} onChange={(e) => setF({ ...f, dose_value: e.target.value })} /></Field>
          <Field label="Unit" htmlFor="au"><Select id="au" value={f.dose_unit} onChange={(e) => setF({ ...f, dose_unit: e.target.value })}>{["ml per litre", "g per litre", "ml per acre", "g per acre", "kg per ha", "litre per ha"].map((u) => <option key={u}>{u}</option>)}</Select></Field>
        </div>
        <Field label="Area treated (ha)" htmlFor="aa" optional error={errs.treated_area_ha}><Input id="aa" type="number" min="0" step="0.01" value={f.treated_area_ha} onChange={(e) => setF({ ...f, treated_area_ha: e.target.value })} /></Field>
        <Field label="Method" htmlFor="am" optional><Input id="am" value={f.application_method} onChange={(e) => setF({ ...f, application_method: e.target.value })} /></Field>
        <Field label="Target problem" htmlFor="at" optional><Input id="at" value={f.target_problem} onChange={(e) => setF({ ...f, target_problem: e.target.value })} placeholder="e.g. Thrips" /></Field>
        <Field label="PHI printed on your pack (days)" htmlFor="aphi" optional hint="Recorded for comparison. Only a verified label rule sets the interval; a longer value you enter is applied as a precaution.">
          <Input id="aphi" type="number" min="0" value={f.recorded_phi_days} onChange={(e) => setF({ ...f, recorded_phi_days: e.target.value })} />
        </Field>
        <div className="sm:col-span-2"><Field label="Notes" htmlFor="an" optional><Textarea id="an" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field></div>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

function LabelDialog({ productId, productName, cropName, onClose }: { productId: number; productName: string; cropName: string; onClose: () => void }) {
  const toast = useToast();
  const { data: crops } = useApi<{ id: number; name: string }[]>("/crops");
  const [f, setF] = useState({ label_version: "", phi_days: "", source_reference: "", valid_from: todayISO() });
  const cropId = crops?.find((c) => c.name === cropName)?.id;
  const m = useMutation(() => api(`/pesticide-products/${productId}/labels`, { body: { crop_id: cropId, label_version: f.label_version, phi_days: f.phi_days ? Number(f.phi_days) : null, source_reference: f.source_reference, valid_from: f.valid_from } }));
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} title={`Submit label details: ${productName}`} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} disabled={!f.label_version || !f.source_reference || !cropId} onClick={async () => { if (await m.run(undefined)) { toast("Submitted for verification"); invalidate("/harvest-assessments", "/pesticide-products"); onClose(); } }}>Submit for verification</Button></>}>
      <p className="mb-4 text-sm text-muted">Details you enter are stored as unverified. They won't change harvest eligibility until an administrator checks them against the approved label.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Crop"><Input value={cropName} disabled /></Field>
        <Field label="Label version or date" htmlFor="lv" error={errs.label_version}><Input id="lv" value={f.label_version} onChange={(e) => setF({ ...f, label_version: e.target.value })} /></Field>
        <Field label="PHI on the label (days)" htmlFor="lp" error={errs.phi_days}><Input id="lp" type="number" min="0" value={f.phi_days} onChange={(e) => setF({ ...f, phi_days: e.target.value })} /></Field>
        <Field label="Valid from" htmlFor="lvf"><Input id="lvf" type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Where this came from" htmlFor="ls" error={errs.source_reference}><Input id="ls" value={f.source_reference} onChange={(e) => setF({ ...f, source_reference: e.target.value })} placeholder="e.g. Pack leaflet, batch 2291" /></Field></div>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

function CyclePanel({ cycleId, openRecord }: { cycleId: number; openRecord: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Detail>(`/harvest-assessments/${cycleId}`);
  const [record, setRecord] = useState(openRecord);
  const [voiding, setVoiding] = useState<Application | null>(null);
  const [reason, setReason] = useState("");
  const [labelFor, setLabelFor] = useState<{ id: number; name: string } | null>(null);
  const [showVoided, setShowVoided] = useState(false);
  const v = useMutation(() => api(`/applications/${voiding!.id}/void`, { body: { reason } }));
  useEffect(() => setRecord(openRecord), [openRecord, cycleId]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const a = data.assessment;
  const outcome = new Map(a.outcomes.map((o) => [o.application_id, o]));
  const apps = data.applications.filter((x) => showVoided || x.status === "active");
  const closed = data.cycle.status === "closed";
  return (
    <div className="min-w-0 space-y-6">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link to={`/app/cycles/${data.cycle.id}`} className="text-lg font-bold text-forest-ink hover:text-forest">{data.cycle.crop}</Link>
            <p className="text-sm text-muted">{data.cycle.field}, {data.cycle.farm}{data.cycle.expected_harvest_date ? ` — harvest expected ${fmtShort(data.cycle.expected_harvest_date)}` : ""}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={a.status} />
            <Help label="How eligibility is calculated">
              Each application counts from its date in the farm's time zone plus the PHI from a verified label rule for this product and crop. The latest date governs. Unverified data never shortens a restriction. This is not a guarantee of residue compliance.
            </Help>
          </div>
        </div>
        <div className="mt-5"><HarvestStrip a={a} /></div>
      </Panel>

      <Panel title="Pesticide applications" pad={false} actions={
        <>
          <label className="flex items-center gap-2 text-[13px] text-muted"><input type="checkbox" checked={showVoided} onChange={(e) => setShowVoided(e.target.checked)} className="accent-[var(--color-forest)]" />Show voided</label>
          {!closed && <Button size="sm" icon="Plus" onClick={() => setRecord(true)}>Record spray</Button>}
        </>
      }>
        {apps.length ? (
          <Table>
            <thead><tr><Th>Product</Th><Th>Applied</Th><Th>Dose</Th><Th>Interval</Th><Th>Eligible from</Th><Th>Label reference</Th><Th /></tr></thead>
            <tbody>
              {apps.map((x) => {
                const o = outcome.get(x.id);
                return (
                  <tr key={x.id} className={x.status === "voided" ? "opacity-55" : ""}>
                    <Td className="min-w-44"><div className="font-semibold">{productDisplayName(x.product.trade_name)}</div><div className="text-xs text-muted">{x.target_problem ?? x.product.active_ingredient}</div></Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(x.applied_at)}</Td>
                    <Td className="num whitespace-nowrap">{x.dose_value} {x.dose_unit}</Td>
                    <Td className="whitespace-nowrap">{x.status === "voided" ? <StatusBadge status="voided" /> : o?.resolved ? <span className="num font-semibold">{o.phi_days} days</span> : <Badge tone="amber" icon="CircleHelp">Unresolved</Badge>}</Td>
                    <Td className="whitespace-nowrap">{o?.earliest_eligible_date ? fmtDate(o.earliest_eligible_date) : "—"}</Td>
                    <Td className="min-w-56 max-w-[300px] text-xs">
                      {x.status === "voided" ? <span className="text-muted">Voided: {x.void_reason}</span> : o?.resolved ? (
                        <span className="text-muted">{o.provenance === "fictional_sample" ? <><span className="mb-1 block"><ProvenanceBadge provenance={o.provenance} /></span>Label {o.label_version}</> : <>Label {o.label_version}: {o.source_reference}</>}{o.warnings.length ? <span className="mt-1 block font-semibold text-amber">{o.warnings.includes("recorded_phi_longer_applied") ? "Your longer recorded PHI was applied." : "Your recorded PHI was shorter and was not used."}</span> : null}</span>
                      ) : o ? (
                        <span className="text-[#7a5212]">{o.issue_message}{" "}
                          {(o.issue === "no_label" || o.issue === "label_not_for_crop") && !closed && <button className="font-semibold underline" onClick={() => setLabelFor({ id: x.product.id, name: productDisplayName(x.product.trade_name) })}>Add label details</button>}
                        </span>
                      ) : null}
                    </Td>
                    <Td>{x.status === "active" && !closed && <Button size="sm" variant="quiet" onClick={() => { setReason(""); setVoiding(x); }}>Void</Button>}</Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        ) : <EmptyState icon="FlaskConical" title="No sprays recorded" body="Record each pesticide application so harvest dates can be checked." action={!closed && <Button size="sm" icon="Plus" onClick={() => setRecord(true)}>Record spray</Button>} />}
      </Panel>

      {data.history.length > 0 && (
        <Panel title="Status history" subtitle="Recorded whenever the result changes.">
          <ol className="space-y-2 text-sm">
            {data.history.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2">
                <span className="w-36 text-xs text-muted">{fmtDateTime(h.created_at)}</span>
                <StatusBadge status={h.status} />
                {h.earliest_eligible_date && <span className="text-muted">from {fmtShort(h.earliest_eligible_date)}</span>}
                <span className="text-xs text-muted">({human(h.trigger).toLowerCase()})</span>
              </li>
            ))}
          </ol>
        </Panel>
      )}

      {record && <RecordDialog cycleId={cycleId} cropName={data.cycle.crop} onClose={() => { setRecord(false); reload(); }} />}
      {labelFor && <LabelDialog productId={labelFor.id} productName={labelFor.name} cropName={data.cycle.crop} onClose={() => { setLabelFor(null); reload(); }} />}
      <ConfirmDialog open={!!voiding} onClose={() => setVoiding(null)} title="Void this application record?" confirmLabel="Void record" tone="danger" pending={v.pending} error={v.error}
        onConfirm={async () => { if (await v.run(undefined)) { setVoiding(null); toast("Record voided"); invalidate("/harvest-assessments", "/dashboard"); } }}>
        <p>Use this only for a record entered by mistake. The record stays in the audit history and eligibility is recalculated.</p>
        <Field label="Reason" htmlFor="vr" hint="At least 5 characters."><Input id="vr" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </ConfirmDialog>
    </div>
  );
}

export default function Harvest() {
  const selectedParam = useSearchParam("cycle");
  const recordParam = useSearchParam("record");
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi<Overview>("/harvest-assessments");
  const selected = selectedParam ? Number(selectedParam) : data?.[0]?.cycle.id;
  return (
    <>
      <PageHeader title="Harvest safety" subtitle="Pre-harvest intervals from verified label rules, per crop cycle." />
      {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : !data?.length ? (
        <EmptyState icon="FlaskConical" title="No active crop cycles" body="Start a crop cycle to record sprays and track harvest dates." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          <nav aria-label="Crop cycles" className="space-y-2">
            {data.map(({ cycle, assessment }) => (
              <button
                key={cycle.id}
                onClick={() => navigate(`/app/harvest?cycle=${cycle.id}`)}
                aria-current={selected === cycle.id ? "true" : undefined}
                className={cn("w-full rounded-lg border px-4 py-3 text-left", selected === cycle.id ? "border-forest bg-paper shadow-soft" : "border-line bg-paper/60 hover:border-line-strong")}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{cycle.crop}</span>
                  <StatusBadge status={assessment.status} label={assessment.status === "eligible" ? "Eligible" : undefined} />
                </div>
                <div className="mt-0.5 text-xs text-muted">{cycle.field}, {cycle.farm}</div>
                {(assessment.status === "restricted" || assessment.status === "upcoming") && (
                  <div className="mt-1.5 flex items-center gap-1 text-xs font-semibold text-charcoal"><Icon name="Timer" size={13} /> Eligible {fmtShort(assessment.earliest_eligible_date)}, {relDays(assessment.days_until_eligible)}</div>
                )}
              </button>
            ))}
          </nav>
          {selected && <CyclePanel key={selected} cycleId={selected} openRecord={recordParam === "1"} />}
        </div>
      )}
    </>
  );
}
