import { useState } from "react";
import { Icon } from "../components/icons";
import { Button, Dialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, Select, StatusBadge, useToast } from "../components/ui";
import { api } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { fmtShort, todayISO } from "../lib/format";
import { Link, useNavigate, useParams } from "../lib/router";
import type { Crop, CycleBrief, Farm, FieldT } from "../lib/types";
import { FarmForm } from "./Farms";

function FieldDialog({ farmId, onClose }: { farmId: number; onClose: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", area_ha: "", soil_type: "", irrigation: "" });
  const m = useMutation(() => api(`/farms/${farmId}/fields`, { body: { name: f.name, area_ha: Number(f.area_ha), soil_type: f.soil_type || null, irrigation: f.irrigation || null } }));
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} title="Add a field" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} disabled={!f.name || !f.area_ha} onClick={async () => { if (await m.run(undefined) !== undefined) { invalidate(`/farms`); toast("Field added"); onClose(); } }}>Add field</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Field name" htmlFor="fname" error={errs.name}><Input id="fname" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Area (hectares)" htmlFor="farea" error={errs.area_ha}><Input id="farea" type="number" min="0.01" step="0.01" value={f.area_ha} onChange={(e) => setF({ ...f, area_ha: e.target.value })} /></Field>
        <Field label="Soil" htmlFor="fsoil" optional><Input id="fsoil" value={f.soil_type} onChange={(e) => setF({ ...f, soil_type: e.target.value })} /></Field>
        <Field label="Irrigation" htmlFor="firr" optional><Input id="firr" value={f.irrigation} onChange={(e) => setF({ ...f, irrigation: e.target.value })} /></Field>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

export function CycleDialog({ field, onClose }: { field: FieldT; onClose: () => void }) {
  const navigate = useNavigate();
  const { data: crops } = useApi<Crop[]>("/crops");
  const [f, setF] = useState({ crop_id: "", variety: "", season: "", sowing_date: todayISO(), fs: "", fe: "", harvest: "", stage: "" });
  const crop = crops?.find((c) => String(c.id) === f.crop_id);
  const m = useMutation(() =>
    api<CycleBrief>("/crop-cycles", {
      body: {
        field_id: field.id, crop_id: Number(f.crop_id), variety: f.variety || null, season: f.season || null, sowing_date: f.sowing_date,
        expected_flowering_start: f.fs || null, expected_flowering_end: f.fe || null, expected_harvest_date: f.harvest || null, current_stage: f.stage || null,
      },
    }),
  );
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Dialog open onClose={onClose} title={`Start a crop cycle on ${field.name}`} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} disabled={!f.crop_id || !f.sowing_date} onClick={async () => { const r = await m.run(undefined); if (r) { invalidate("/farms", "/crop-cycles", "/dashboard"); navigate(`/app/cycles/${r.id}`); } }}>Start cycle</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Crop" htmlFor="ccrop" error={errs.crop_id}>
          <Select id="ccrop" value={f.crop_id} onChange={(e) => setF({ ...f, crop_id: e.target.value, stage: "" })}>
            <option value="">Choose a crop</option>
            {crops?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="Variety" htmlFor="cvar" optional><Input id="cvar" value={f.variety} onChange={(e) => setF({ ...f, variety: e.target.value })} /></Field>
        <Field label="Sowing or transplant date" htmlFor="csow" error={errs.sowing_date}><Input id="csow" type="date" value={f.sowing_date} onChange={(e) => setF({ ...f, sowing_date: e.target.value })} /></Field>
        <Field label="Current stage" htmlFor="cstage" optional>
          <Select id="cstage" value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })} disabled={!crop}>
            <option value="">—</option>
            {crop?.growth_stages.map((s) => <option key={s}>{s}</option>)}
          </Select>
        </Field>
        <Field label="Flowering expected from" htmlFor="cfs" optional hint={crop?.pollinator_dependent ? "Needed to plan pollination." : undefined}><Input id="cfs" type="date" value={f.fs} onChange={(e) => setF({ ...f, fs: e.target.value })} /></Field>
        <Field label="Flowering expected until" htmlFor="cfe" optional><Input id="cfe" type="date" value={f.fe} min={f.fs || undefined} onChange={(e) => setF({ ...f, fe: e.target.value })} /></Field>
        <Field label="Expected harvest" htmlFor="ch" optional><Input id="ch" type="date" value={f.harvest} onChange={(e) => setF({ ...f, harvest: e.target.value })} /></Field>
        <Field label="Season" htmlFor="cseason" optional><Input id="cseason" placeholder="e.g. Rabi 2026" value={f.season} onChange={(e) => setF({ ...f, season: e.target.value })} /></Field>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

export default function FarmDetail() {
  const { farmId } = useParams<{ farmId: string }>();
  const { data: farm, error, loading, reload } = useApi<Farm>(`/farms/${farmId}`);
  const [edit, setEdit] = useState(false);
  const [addField, setAddField] = useState(false);
  const [cycleFor, setCycleFor] = useState<FieldT | null>(null);
  if (loading && !farm) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!farm) return null;
  return (
    <>
      <PageHeader
        back={{ to: "/app/farms", label: "Farms" }}
        title={farm.name}
        subtitle={[farm.village, farm.district, farm.state].filter(Boolean).join(", ")}
        actions={<><Button variant="secondary" onClick={() => setEdit(true)}>Edit farm</Button><Button icon="Plus" onClick={() => setAddField(true)}>Add field</Button></>}
      />
      {!farm.fields?.length ? (
        <Panel><EmptyState icon="Map" title="No fields yet" body="Add a field, then start a crop cycle on it." action={<Button icon="Plus" onClick={() => setAddField(true)}>Add field</Button>} /></Panel>
      ) : (
        <div className="space-y-4">
          {farm.fields.map((fl) => {
            const active = fl.cycles.find((c) => c.status !== "closed");
            const past = fl.cycles.filter((c) => c.status === "closed");
            return (
              <Panel key={fl.id} title={<span>{fl.name} <span className="font-medium text-muted">— {fl.area_ha} ha{fl.soil_type ? `, ${fl.soil_type}` : ""}{fl.irrigation ? `, ${fl.irrigation.toLowerCase()} irrigation` : ""}</span></span>}
                actions={!active && <Button size="sm" icon="Sprout" onClick={() => setCycleFor(fl)}>Start crop cycle</Button>}>
                {active ? (
                  <Link to={`/app/cycles/${active.id}`} className="flex flex-wrap items-center gap-4 rounded-md border border-line bg-white px-4 py-3 hover:border-forest">
                    <span className="grid size-10 place-items-center rounded-full bg-sage-pale text-forest"><Icon name="Sprout" size={18} /></span>
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold">{active.crop.name}{active.variety ? ` (${active.variety})` : ""}</div>
                      <div className="text-xs text-muted">Sown {fmtShort(active.sowing_date)}{active.current_stage ? `, now ${active.current_stage.toLowerCase()}` : ""}{active.expected_harvest_date ? `, harvest expected ${fmtShort(active.expected_harvest_date)}` : ""}</div>
                    </div>
                    <StatusBadge status={active.status} />
                    <Icon name="ChevronRight" className="text-muted" />
                  </Link>
                ) : <p className="text-sm text-muted">No active crop on this field.</p>}
                {past.length > 0 && (
                  <p className="mt-3 text-xs text-muted">Earlier: {past.map((c) => `${c.crop.name} (${c.season ?? fmtShort(c.sowing_date)})`).join(", ")}</p>
                )}
              </Panel>
            );
          })}
        </div>
      )}
      {edit && <FarmForm open initial={farm} onClose={() => { setEdit(false); reload(); }} />}
      {addField && <FieldDialog farmId={farm.id} onClose={() => { setAddField(false); reload(); }} />}
      {cycleFor && <CycleDialog field={cycleFor} onClose={() => setCycleFor(null)} />}
    </>
  );
}
