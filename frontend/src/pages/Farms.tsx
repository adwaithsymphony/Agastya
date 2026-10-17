import { useState } from "react";
import { Button, Dialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { Link, useNavigate } from "../lib/router";
import type { Farm } from "../lib/types";
import { Icon } from "../components/icons";

export function FarmForm({ open, onClose, initial }: { open: boolean; onClose: () => void; initial?: Farm }) {
  const navigate = useNavigate();
  const [f, setF] = useState({
    name: initial?.name ?? "", village: initial?.village ?? "", district: initial?.district ?? "", state: initial?.state ?? "Maharashtra",
    latitude: initial?.latitude?.toString() ?? "", longitude: initial?.longitude?.toString() ?? "",
  });
  const m = useMutation(async () => {
    const body = { ...f, village: f.village || null, latitude: f.latitude ? Number(f.latitude) : null, longitude: f.longitude ? Number(f.longitude) : null, timezone: initial?.timezone ?? "Asia/Kolkata" };
    return initial ? api<Farm>(`/farms/${initial.id}`, { method: "PATCH", body }) : api<Farm>("/farms", { body });
  });
  const errs = m.error?.fieldErrors() ?? {};
  const save = async () => {
    const r = await m.run(undefined);
    if (r) {
      invalidate("/farms", "/dashboard");
      onClose();
      if (!initial) navigate(`/app/farms/${r.id}`);
    }
  };
  return (
    <Dialog open={open} onClose={onClose} title={initial ? "Edit farm" : "Add a farm"} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.pending} onClick={save} disabled={!f.name || !f.district || !f.state}>{initial ? "Save farm" : "Add farm"}</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field label="Farm name" htmlFor="fn" error={errs.name}><Input id="fn" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
        <Field label="Village" htmlFor="fv" optional><Input id="fv" value={f.village} onChange={(e) => setF({ ...f, village: e.target.value })} /></Field>
        <Field label="District" htmlFor="fd" error={errs.district}><Input id="fd" value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })} /></Field>
        <Field label="State" htmlFor="fs" error={errs.state}><Input id="fs" value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })} /></Field>
        <div />
        <Field label="Latitude" htmlFor="flat" optional hint="Used only for distance estimates."><Input id="flat" inputMode="decimal" value={f.latitude} onChange={(e) => setF({ ...f, latitude: e.target.value })} /></Field>
        <Field label="Longitude" htmlFor="flon" optional><Input id="flon" inputMode="decimal" value={f.longitude} onChange={(e) => setF({ ...f, longitude: e.target.value })} /></Field>
      </div>
      <div className="mt-4"><FormError error={m.error} /></div>
    </Dialog>
  );
}

export default function Farms() {
  const { data, error, loading, reload } = useApi<Farm[]>("/farms");
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHeader title="Farms & fields" subtitle="Where each crop cycle lives." actions={<Button icon="Plus" onClick={() => setOpen(true)}>Add farm</Button>} />
      {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : !data?.length ? (
        <EmptyState icon="Map" title="Add your first farm" body="Farms hold your fields; each field runs one crop cycle at a time." action={<Button icon="Plus" onClick={() => setOpen(true)}>Add farm</Button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((f) => (
            <Link key={f.id} to={`/app/farms/${f.id}`} className="group rounded-lg border border-line bg-paper p-5 hover:border-line-strong">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-forest-ink group-hover:text-forest">{f.name}</h2>
                  <p className="flex items-center gap-1 text-sm text-muted"><Icon name="MapPin" size={14} />{[f.village, f.district, f.state].filter(Boolean).join(", ")}</p>
                </div>
                <Icon name="ChevronRight" className="text-muted" />
              </div>
              <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-line pt-4 text-sm">
                <div><dt className="text-xs text-muted">Fields</dt><dd className="num text-lg font-bold">{f.field_count}</dd></div>
                <div><dt className="text-xs text-muted">Area</dt><dd className="num text-lg font-bold">{f.total_area_ha} ha</dd></div>
                <div><dt className="text-xs text-muted">Active cycles</dt><dd className="num text-lg font-bold">{f.active_cycle_count}</dd></div>
              </dl>
            </Link>
          ))}
        </div>
      )}
      {open && <FarmForm open onClose={() => setOpen(false)} />}
    </>
  );
}
