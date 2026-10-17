import { useEffect, useState } from "react";
import { Icon } from "../../components/icons";
import { Button, ConfirmDialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, Table, Td, Textarea, Th, cn, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { invalidate, useApi, useMutation } from "../../lib/data";
import { fmtDate, todayISO } from "../../lib/format";
import type { Crop, Provider } from "../../lib/types";

export default function ProviderProfile() {
  const toast = useToast();
  const { data: p, error, loading, reload } = useApi<Provider>("/pollination/profile");
  const { data: crops } = useApi<Crop[]>("/crops");
  const [f, setF] = useState<{ display_name: string; description: string; contact_phone: string; service_radius_km: string; colonies_total: string; is_active: boolean; crop_ids: number[]; areas: { district: string; state: string }[] } | null>(null);
  const [area, setArea] = useState({ district: "", state: "" });
  const [win, setWin] = useState({ start_date: todayISO(), end_date: "", colonies_available: "", notes: "" });
  const [removing, setRemoving] = useState<number | null>(null);

  useEffect(() => {
    if (p) setF({ display_name: p.display_name, description: p.description ?? "", contact_phone: p.contact_phone ?? "", service_radius_km: p.service_radius_km?.toString() ?? "", colonies_total: String(p.colonies_total), is_active: p.is_active, crop_ids: p.crops.map((c) => c.id), areas: p.service_areas.map(({ district, state }) => ({ district, state })) });
  }, [p]);

  const save = useMutation(() => api("/pollination/profile", { method: "PUT", body: { display_name: f!.display_name, description: f!.description || null, contact_phone: f!.contact_phone || null, service_radius_km: f!.service_radius_km ? Number(f!.service_radius_km) : null, colonies_total: Number(f!.colonies_total), is_active: f!.is_active, crop_ids: f!.crop_ids, service_areas: f!.areas } }));
  const add = useMutation(() => api("/pollination/availability", { body: { ...win, colonies_available: Number(win.colonies_available), notes: win.notes || null } }));
  const del = useMutation((id: number) => api(`/pollination/availability/${id}`, { method: "DELETE" }));

  if (loading && !p) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!p || !f) return null;
  const errs = save.error?.fieldErrors() ?? {};
  return (
    <>
      <PageHeader title="Services & availability" subtitle="What farmers see when they search for pollination." />
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <Panel title="Service profile" actions={<Button size="sm" loading={save.pending} onClick={async () => { if (await save.run(undefined)) { toast("Profile saved"); invalidate("/pollination"); } }}>Save profile</Button>}>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Business name" htmlFor="pn" error={errs.display_name}><Input id="pn" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
              <Field label="Contact phone" htmlFor="pp" optional><Input id="pp" value={f.contact_phone} onChange={(e) => setF({ ...f, contact_phone: e.target.value })} /></Field>
              <Field label="Colonies you manage" htmlFor="pc" error={errs.colonies_total}><Input id="pc" type="number" min="0" value={f.colonies_total} onChange={(e) => setF({ ...f, colonies_total: e.target.value })} /></Field>
              <Field label="Service radius (km)" htmlFor="pr" optional hint="Used when both locations are recorded."><Input id="pr" type="number" min="1" value={f.service_radius_km} onChange={(e) => setF({ ...f, service_radius_km: e.target.value })} /></Field>
            </div>
            <Field label="Description" htmlFor="pd" optional><Textarea id="pd" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
            <fieldset>
              <legend className="mb-2 text-[13px] font-semibold">Crops you pollinate</legend>
              <div className="flex flex-wrap gap-2">
                {crops?.map((c) => {
                  const on = f.crop_ids.includes(c.id);
                  return (
                    <button key={c.id} type="button" aria-pressed={on} onClick={() => setF({ ...f, crop_ids: on ? f.crop_ids.filter((x) => x !== c.id) : [...f.crop_ids, c.id] })}
                      className={cn("rounded-full border px-3 py-1.5 text-[13px] font-semibold", on ? "border-forest bg-forest text-white" : "border-line-strong bg-white text-charcoal hover:border-forest")}>
                      {c.name}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <fieldset>
              <legend className="mb-2 text-[13px] font-semibold">Districts you serve</legend>
              <ul className="mb-2 flex flex-wrap gap-2">
                {f.areas.map((a, i) => (
                  <li key={`${a.district}-${a.state}`} className="flex items-center gap-1 rounded-full bg-sage-pale py-1 pr-1.5 pl-3 text-[13px] font-semibold text-forest">
                    {a.district}, {a.state}
                    <button aria-label={`Remove ${a.district}`} onClick={() => setF({ ...f, areas: f.areas.filter((_, j) => j !== i) })} className="rounded-full p-0.5 hover:bg-white"><Icon name="X" size={13} /></button>
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap gap-2">
                <Input aria-label="District" placeholder="District" value={area.district} onChange={(e) => setArea({ ...area, district: e.target.value })} className="w-40" />
                <Input aria-label="State" placeholder="State" value={area.state} onChange={(e) => setArea({ ...area, state: e.target.value })} className="w-40" />
                <Button size="sm" variant="secondary" disabled={area.district.length < 2 || area.state.length < 2} onClick={() => { setF({ ...f, areas: [...f.areas, area] }); setArea({ district: "", state: "" }); }}>Add district</Button>
              </div>
            </fieldset>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} className="accent-[var(--color-forest)]" />Accepting new requests</label>
            <FormError error={save.error} />
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Availability windows" subtitle="Farmers can only book inside these windows." pad={false}>
            {p.availability?.length ? (
              <Table>
                <thead><tr><Th>Window</Th><Th>Colonies</Th><Th>Lowest free</Th><Th /></tr></thead>
                <tbody>{p.availability.map((w) => (
                  <tr key={w.id}>
                    <Td>{fmtDate(w.start_date)} – {fmtDate(w.end_date)}{w.notes && <div className="text-xs text-muted">{w.notes}</div>}</Td>
                    <Td className="num">{w.colonies_available}</Td>
                    <Td className="num">{w.min_free}</Td>
                    <Td><Button size="sm" variant="quiet" onClick={() => { del.setError(null); setRemoving(w.id); }}>Remove</Button></Td>
                  </tr>
                ))}</tbody>
              </Table>
            ) : <EmptyState icon="Calendar" title="No availability yet" />}
          </Panel>
          <Panel title="Add a window">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="From" htmlFor="ws"><Input id="ws" type="date" value={win.start_date} onChange={(e) => setWin({ ...win, start_date: e.target.value })} /></Field>
              <Field label="Until" htmlFor="we"><Input id="we" type="date" min={win.start_date} value={win.end_date} onChange={(e) => setWin({ ...win, end_date: e.target.value })} /></Field>
              <Field label="Colonies available" htmlFor="wc" hint={`Up to ${p.colonies_total}.`}><Input id="wc" type="number" min="1" max={p.colonies_total} value={win.colonies_available} onChange={(e) => setWin({ ...win, colonies_available: e.target.value })} /></Field>
              <Field label="Note" htmlFor="wn" optional><Input id="wn" value={win.notes} onChange={(e) => setWin({ ...win, notes: e.target.value })} /></Field>
            </div>
            <div className="mt-4 space-y-3">
              <FormError error={add.error} />
              <Button loading={add.pending} disabled={!win.end_date || !win.colonies_available} onClick={async () => { if (await add.run(undefined)) { toast("Availability added"); setWin({ start_date: todayISO(), end_date: "", colonies_available: "", notes: "" }); invalidate("/pollination", "/dashboard"); } }}>Add window</Button>
            </div>
          </Panel>
        </div>
      </div>
      <ConfirmDialog open={removing !== null} onClose={() => setRemoving(null)} title="Remove this availability window?" confirmLabel="Remove window" tone="danger" pending={del.pending} error={del.error}
        onConfirm={async () => { if (await del.run(removing!)) { setRemoving(null); toast("Window removed"); invalidate("/pollination", "/dashboard"); } }}>
        <p>Windows that accepted bookings depend on can't be removed.</p>
      </ConfirmDialog>
    </>
  );
}
