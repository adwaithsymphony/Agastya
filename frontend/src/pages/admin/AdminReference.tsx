import { useEffect, useState } from "react";
import { Badge, Button, ConfirmDialog, Dialog, ProvenanceBadge, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, StatusBadge, Table, Tabs, Td, Textarea, Th, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { invalidate, useApi, useMutation } from "../../lib/data";
import { productDisplayName, fmtDate, fmtDateTime, human } from "../../lib/format";
import type { Crop, Label, Product } from "../../lib/types";

function VerifyDialog({ l, onClose }: { l: Label; onClose: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ source_reference: "", phi_days: l.phi_days?.toString() ?? "", valid_from: l.valid_from, valid_until: l.valid_until ?? "", note: "" });
  const [reject, setReject] = useState("");
  const v = useMutation(() => api(`/pesticide-labels/${l.id}/verify`, { body: { source_reference: f.source_reference, phi_days: Number(f.phi_days), valid_from: f.valid_from, valid_until: f.valid_until || null, note: f.note || null } }));
  const r = useMutation(() => api(`/pesticide-labels/${l.id}/reject`, { body: { reason: reject } }));
  const done = (m: string) => { toast(m); invalidate("/pesticide-labels", "/pesticide-products", "/dashboard"); onClose(); };
  return (
    <Dialog open onClose={onClose} wide title={`Verify label rule: ${l.product_name} on ${l.crop.name}`} footer={
      <>
        <Input aria-label="Rejection reason" placeholder="Reason, to reject" value={reject} onChange={(e) => setReject(e.target.value)} className="mr-auto h-10 max-w-60" />
        <Button variant="ghost" disabled={reject.length < 3} loading={r.pending} onClick={async () => { if (await r.run(undefined)) done("Label rejected"); }}>Reject</Button>
        <Button loading={v.pending} disabled={!f.source_reference || f.phi_days === ""} onClick={async () => { if (await v.run(undefined)) done("Label verified; eligibility recalculated"); }}>Verify rule</Button>
      </>
    }>
      <div className="mb-4 rounded-md bg-amber-soft px-3 py-2.5 text-[13px] text-[#7a5212]">
        Submitted value: PHI {l.phi_days ?? "—"} days, from “{l.source_reference}”. Check it against the approved label or official registration record before verifying. Verified rules immediately govern harvest eligibility.
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field label="Authoritative source" htmlFor="vs" hint="Registration document, label copy reference, or official database entry."><Input id="vs" value={f.source_reference} onChange={(e) => setF({ ...f, source_reference: e.target.value })} /></Field></div>
        <Field label="Verified PHI (days)" htmlFor="vp"><Input id="vp" type="number" min="0" value={f.phi_days} onChange={(e) => setF({ ...f, phi_days: e.target.value })} /></Field>
        <div />
        <Field label="Valid from" htmlFor="vf"><Input id="vf" type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></Field>
        <Field label="Valid until" htmlFor="vu" optional><Input id="vu" type="date" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Verification note" htmlFor="vn" optional><Input id="vn" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field></div>
      </div>
      <div className="mt-4 space-y-2"><FormError error={v.error} /><FormError error={r.error} /></div>
    </Dialog>
  );
}

function RevokeDialog({ l, onClose }: { l: Label; onClose: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const m = useMutation(() => api(`/pesticide-labels/${l.id}/revoke`, { body: { reason } }));
  return (
    <ConfirmDialog open onClose={onClose} title="Revoke this verification?" confirmLabel="Revoke verification" tone="danger" pending={m.pending} error={m.error}
      onConfirm={async () => { if (await m.run(undefined)) { toast("Verification revoked; eligibility recalculated"); invalidate("/pesticide-labels", "/dashboard"); onClose(); } }}>
      <p>{l.product_name} on {l.crop.name} ({l.phi_days} day PHI) stops counting immediately. Sprays that relied on it show as needing verification until a corrected rule is verified. This is recorded in the audit log.</p>
      <Field label="Reason" htmlFor="rvr" hint="For example: superseded label edition, entered against the wrong crop."><Input id="rvr" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
    </ConfirmDialog>
  );
}

function CropDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ code: "", name: "", scientific_name: "", category: "", stages: "", pollinator_dependent: false });
  const m = useMutation(() => api("/admin/crops", { body: { code: f.code, name: f.name, scientific_name: f.scientific_name || null, category: f.category, growth_stages: f.stages.split(",").map((s) => s.trim()).filter(Boolean), pollinator_dependent: f.pollinator_dependent, vision_label_prefix: null } }));
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} title="Add a crop" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} onClick={async () => { if (await m.run(undefined)) { toast("Crop added"); invalidate("/crops"); onClose(); } }}>Add crop</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Code" htmlFor="cc" hint="Lowercase, e.g. okra" error={errs.code}><Input id="cc" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} /></Field>
        <Field label="Name" htmlFor="cn" error={errs.name}><Input id="cn" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Scientific name" htmlFor="cs" optional><Input id="cs" value={f.scientific_name} onChange={(e) => setF({ ...f, scientific_name: e.target.value })} /></Field>
        <Field label="Category" htmlFor="ccat" error={errs.category}><Input id="ccat" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Growth stages, in order" htmlFor="cst" hint="Comma separated." error={errs.growth_stages}><Input id="cst" value={f.stages} onChange={(e) => setF({ ...f, stages: e.target.value })} /></Field></div>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={f.pollinator_dependent} onChange={(e) => setF({ ...f, pollinator_dependent: e.target.checked })} className="accent-[var(--color-forest)]" />Managed pollinators commonly used</label>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

export default function AdminReference() {
  const toast = useToast();
  const [tab, setTab] = useState<"labels" | "products" | "crops" | "guidance">("labels");
  const labels = useApi<Label[]>("/pesticide-labels");
  const products = useApi<Product[]>(tab === "products" ? "/pesticide-products" : null);
  const crops = useApi<Crop[]>(tab === "crops" || tab === "guidance" ? "/crops" : null);
  type Guidance = { crop_id: number; soil_moisture_min_pct: number | null; sunlight_min_hours: number | null; fertilizer_guidance: string | null; disease_guidance: string | null; source_reference: string; verified: boolean; updated_at?: string };
  const guidance = useApi<{ items: Guidance[] }>(tab === "guidance" ? "/plant-intelligence/guidance" : null);
  const [guidanceCrop, setGuidanceCrop] = useState("");
  const [guidanceForm, setGuidanceForm] = useState({ soil_moisture_min_pct: "", sunlight_min_hours: "", fertilizer_guidance: "", disease_guidance: "", source_reference: "" });
  const [guidanceSaving, setGuidanceSaving] = useState(false);
  const [guidanceError, setGuidanceError] = useState("");
  const [guidanceSaved, setGuidanceSaved] = useState(false);
  useEffect(() => {
    const row = guidance.data?.items.find((item) => String(item.crop_id) === guidanceCrop);
    setGuidanceForm({
      soil_moisture_min_pct: row?.soil_moisture_min_pct == null ? "" : String(row.soil_moisture_min_pct),
      sunlight_min_hours: row?.sunlight_min_hours == null ? "" : String(row.sunlight_min_hours),
      fertilizer_guidance: row?.fertilizer_guidance ?? "",
      disease_guidance: row?.disease_guidance ?? "",
      source_reference: row?.source_reference ?? "",
    });
    setGuidanceSaved(false);
  }, [guidanceCrop, guidance.data]);
  const [verify, setVerify] = useState<Label | null>(null);
  const [addCrop, setAddCrop] = useState(false);
  const [revoke, setRevoke] = useState<Label | null>(null);
  const pendingCount = labels.data?.filter((l) => l.verification_status === "unverified").length ?? 0;
  return (
    <>
      <PageHeader title="Reference data" subtitle="Crops, pesticide products and the label rules that govern harvest eligibility." actions={tab === "crops" && <Button icon="Plus" onClick={() => setAddCrop(true)}>Add crop</Button>} />
      <Panel pad={false}>
        <div className="px-3 pt-1">
          <Tabs value={tab} onChange={setTab} items={[{ value: "labels", label: "Label rules", count: pendingCount || undefined }, { value: "products", label: "Products" }, { value: "crops", label: "Crops" }, { value: "guidance", label: "Plant guidance" }]} />
        </div>
        {tab === "labels" && (labels.loading && !labels.data ? <div className="p-5"><Loading /></div> : labels.error ? <div className="p-5"><ErrorState error={labels.error} /></div> : (
          <Table>
            <thead><tr><Th>Product</Th><Th>Crop</Th><Th>PHI</Th><Th>Valid</Th><Th>Source</Th><Th>Status</Th><Th /></tr></thead>
            <tbody>
              {[...(labels.data ?? [])].sort((a, b) => Number(b.verification_status === "unverified") - Number(a.verification_status === "unverified")).map((l) => (
                <tr key={l.id}>
                  <Td className="font-semibold">{l.product_name}<div className="text-xs font-normal text-muted">Label {l.label_version}</div></Td>
                  <Td>{l.crop.name}</Td>
                  <Td className="num whitespace-nowrap">{l.phi_days ?? "—"} d</Td>
                  <Td className="whitespace-nowrap text-[13px]">{fmtDate(l.valid_from)} – {l.valid_until ? fmtDate(l.valid_until) : "open"}</Td>
                  <Td className="max-w-xs text-xs text-muted">{l.provenance === "fictional_sample" && <span className="mb-1 block"><ProvenanceBadge provenance={l.provenance} /></span>}{l.source_reference}</Td>
                  <Td><StatusBadge status={l.verification_status} />{l.verified_at && <div className="mt-0.5 text-[11px] text-muted">{fmtDateTime(l.verified_at)}</div>}</Td>
                  <Td>
                    {l.verification_status === "unverified" && <Button size="sm" onClick={() => setVerify(l)}>Review</Button>}
                    {l.verification_status === "verified" && <Button size="sm" variant="quiet" onClick={() => setRevoke(l)}>Revoke</Button>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ))}
        {tab === "products" && (products.loading && !products.data ? <div className="p-5"><Loading /></div> : products.data?.length ? (
          <Table>
            <thead><tr><Th>Product</Th><Th>Active ingredient</Th><Th>Type</Th><Th>Label rules</Th></tr></thead>
            <tbody>{products.data.map((p) => (
              <tr key={p.id}><Td className="font-semibold">{productDisplayName(p.trade_name)}</Td><Td>{p.active_ingredient ?? "—"}</Td><Td>{p.product_type ?? "—"}</Td>
                <Td className="text-[13px]">{p.labels.length ? p.labels.map((l) => `${l.crop.name} (${human(l.verification_status).toLowerCase()})`).join(", ") : <span className="text-amber">None</span>}</Td></tr>
            ))}</tbody>
          </Table>
        ) : <EmptyState title="No products" />)}
        {tab === "crops" && (crops.loading && !crops.data ? <div className="p-5"><Loading /></div> : (
          <Table>
            <thead><tr><Th>Crop</Th><Th>Category</Th><Th>Growth stages</Th><Th>Pollinators</Th><Th>Vision model</Th></tr></thead>
            <tbody>{crops.data?.map((c) => (
              <tr key={c.id}><Td className="font-semibold">{c.name}<div className="text-xs font-normal text-muted italic">{c.scientific_name}</div></Td><Td>{c.category}</Td>
                <Td className="text-[13px]">{c.growth_stages.join(", ")}</Td><Td>{c.pollinator_dependent ? "Commonly used" : "—"}</Td><Td>{c.vision_supported ? <Badge tone="sage">Covered</Badge> : <span className="text-muted">Not covered</span>}</Td></tr>
            ))}</tbody>
          </Table>
        ))}
        {tab === "guidance" && <div className="space-y-5 p-5">
          <div className="max-w-3xl">
            <h3 className="font-semibold text-forest-ink">Crop-specific care guidance</h3>
            <p className="mt-1 text-sm text-muted">Configure thresholds and advice only from an approved agronomic source. Recommendations are generated only when recorded measurements or actual model results support them.</p>
          </div>
          {crops.loading && !crops.data ? <Loading /> : <>
            <Field label="Crop" htmlFor="guidance-crop"><select id="guidance-crop" className="h-10 w-full rounded-md border border-line bg-paper px-3" value={guidanceCrop} onChange={(e) => setGuidanceCrop(e.target.value)}><option value="">Select crop</option>{crops.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            {guidanceCrop && <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Minimum soil moisture (%)" htmlFor="guidance-moisture" optional><Input id="guidance-moisture" type="number" min="0" max="100" step="0.1" value={guidanceForm.soil_moisture_min_pct} onChange={(e) => setGuidanceForm({ ...guidanceForm, soil_moisture_min_pct: e.target.value })} /></Field>
                <Field label="Minimum sunlight hours" htmlFor="guidance-sunlight" optional><Input id="guidance-sunlight" type="number" min="0" max="24" step="0.1" value={guidanceForm.sunlight_min_hours} onChange={(e) => setGuidanceForm({ ...guidanceForm, sunlight_min_hours: e.target.value })} /></Field>
              </div>
              <Field label="Fertilizer guidance" htmlFor="guidance-fertilizer" optional><Textarea id="guidance-fertilizer" value={guidanceForm.fertilizer_guidance} onChange={(e) => setGuidanceForm({ ...guidanceForm, fertilizer_guidance: e.target.value })} /></Field>
              <Field label="Plant-health follow-up guidance" htmlFor="guidance-disease" optional><Textarea id="guidance-disease" value={guidanceForm.disease_guidance} onChange={(e) => setGuidanceForm({ ...guidanceForm, disease_guidance: e.target.value })} /></Field>
              <Field label="Approved source reference" htmlFor="guidance-source"><Input id="guidance-source" value={guidanceForm.source_reference} onChange={(e) => setGuidanceForm({ ...guidanceForm, source_reference: e.target.value })} placeholder="Guideline title, issuer and version" /></Field>
              {guidanceError && <p role="alert" className="text-sm text-danger">{guidanceError}</p>}
              {guidanceSaved && <p className="text-sm font-semibold text-forest">Guidance saved.</p>}
              <Button loading={guidanceSaving} disabled={guidanceSaving || guidanceForm.source_reference.trim().length < 3} onClick={async () => {
                setGuidanceSaving(true); setGuidanceError(""); setGuidanceSaved(false);
                try {
                  await api(`/plant-intelligence/guidance/${guidanceCrop}`, { method: "PUT", body: {
                    soil_moisture_min_pct: guidanceForm.soil_moisture_min_pct === "" ? null : Number(guidanceForm.soil_moisture_min_pct),
                    sunlight_min_hours: guidanceForm.sunlight_min_hours === "" ? null : Number(guidanceForm.sunlight_min_hours),
                    fertilizer_guidance: guidanceForm.fertilizer_guidance || null,
                    disease_guidance: guidanceForm.disease_guidance || null,
                    source_reference: guidanceForm.source_reference.trim()
                  }});
                  await guidance.reload(); setGuidanceSaved(true); toast("Crop guidance saved");
                } catch (e) { setGuidanceError((e as Error).message); }
                finally { setGuidanceSaving(false); }
              }}>Save guidance</Button>
            </>}
          </>}
        </div>}
      </Panel>
      {verify && <VerifyDialog l={verify} onClose={() => { setVerify(null); labels.reload(); }} />}
      {revoke && <RevokeDialog l={revoke} onClose={() => { setRevoke(null); labels.reload(); }} />}
      {addCrop && <CropDialog onClose={() => { setAddCrop(false); crops.reload(); }} />}
    </>
  );
}
