import { useState, type ReactNode } from "react";
import { HarvestStrip, KV } from "../components/domain";
import { Icon, type IconName } from "../components/icons";
import { Button, ConfirmDialog, Dialog, ErrorState, Field, FormError, Input, LinkButton, Loading, PageHeader, Panel, Select, StatusBadge, Textarea, useToast } from "../components/ui";
import { api } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { conditionLabel, fmtDate, fmtShort, human, pct, todayISO } from "../lib/format";
import { Link, useParams } from "../lib/router";
import type { Assessment, CycleDetail as CD } from "../lib/types";

type TItem = { kind: string; date: string; id: number; [k: string]: unknown };

const KIND: Record<string, { icon: IconName; tone: string }> = {
  sowing: { icon: "Sprout", tone: "bg-sage-pale text-forest" },
  stage: { icon: "Leaf", tone: "bg-sage-pale text-forest" },
  observation: { icon: "Camera", tone: "bg-water-soft text-water" },
  review: { icon: "ClipboardCheck", tone: "bg-water-soft text-water" },
  application: { icon: "FlaskConical", tone: "bg-amber-soft text-amber" },
  booking: { icon: "Flower2", tone: "bg-beige text-earth" },
};

function TimelineItem({ t }: { t: TItem }) {
  const k = KIND[t.kind] ?? KIND.stage;
  let body: ReactNode = null;
  if (t.kind === "sowing") body = <span className="font-semibold">Sown</span>;
  if (t.kind === "stage") body = <><span className="font-semibold">Stage: {String(t.stage)}</span>{t.notes ? <p className="text-[13px] text-muted">{String(t.notes)}</p> : null}</>;
  if (t.kind === "observation") {
    const p = t.prediction as { predicted_condition: string | null; confidence: number | null; status: string } | null;
    body = (
      <Link to={`/app/observations/${t.id}`} className="flex items-center gap-3 hover:text-forest">
        <img src={`/api/v1/observations/${t.id}/image`} alt="" className="size-12 rounded-md object-cover" loading="lazy" />
        <span>
          <span className="font-semibold">Photo observation</span>
          <span className="block text-[13px] text-muted">{p?.predicted_condition && (p.status === "completed" || p.status === "uncertain") ? `Model: ${conditionLabel(p.predicted_condition)}, ${pct(p.confidence)}` : human(String(t.status))}</span>
        </span>
        <span className="ml-auto"><StatusBadge status={String(t.review_status) === "not_required" ? String(t.status) : String(t.review_status)} /></span>
      </Link>
    );
  }
  if (t.kind === "review") body = <Link to={`/app/observations/${t.observation_id}`} className="hover:text-forest"><span className="font-semibold">Reviewed by {String(t.reviewer)}</span><span className="block text-[13px] text-muted">{human(String(t.decision))}{t.reviewed_label ? ` — ${String(t.reviewed_label)}` : ""}</span></Link>;
  if (t.kind === "application") body = <><span className="font-semibold">Sprayed {String(t.product)}</span><span className="block text-[13px] text-muted">{String(t.dose)}{t.status === "voided" ? " — record voided" : ""}</span></>;
  if (t.kind === "booking") body = <><span className="font-semibold">Pollination with {String(t.provider)}</span><span className="block text-[13px] text-muted">{fmtShort(String(t.start_date))} – {fmtShort(String(t.end_date))}, {human(String(t.status)).toLowerCase()}</span></>;
  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      <span className={`relative z-10 grid size-8 shrink-0 place-items-center rounded-full ${k.tone}`}><Icon name={k.icon} size={15} /></span>
      <div className="min-w-0 flex-1 pt-1 text-sm">
        <div className="text-xs text-muted">{fmtDate(t.date)}</div>
        <div className="mt-0.5">{body}</div>
      </div>
    </li>
  );
}

export default function CycleDetail() {
  const { cycleId } = useParams<{ cycleId: string }>();
  const toast = useToast();
  const { data: c, error, loading, reload } = useApi<CD>(`/crop-cycles/${cycleId}`);
  const { data: timeline } = useApi<TItem[]>(`/crop-cycles/${cycleId}/timeline`);
  const { data: harvest } = useApi<{ assessment: Assessment }>(`/harvest-assessments/${cycleId}`);
  const [stageOpen, setStageOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [stage, setStage] = useState({ stage: "", observed_on: todayISO(), notes: "" });
  const [dates, setDates] = useState({ fs: "", fe: "", harvest: "" });
  const addStage = useMutation(() => api(`/crop-cycles/${cycleId}/stages`, { body: { ...stage, notes: stage.notes || null } }));
  const update = useMutation((body: Record<string, unknown>) => api(`/crop-cycles/${cycleId}`, { method: "PATCH", body }));

  if (loading && !c) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!c) return null;
  const refresh = () => invalidate(`/crop-cycles/${cycleId}`, "/dashboard", "/farms", "/harvest-assessments");
  const closed = c.status === "closed";
  return (
    <>
      <PageHeader
        back={{ to: `/app/farms/${c.farm.id}`, label: c.farm.name }}
        title={`${c.crop.name}${c.variety ? ` — ${c.variety}` : ""}`}
        subtitle={`${c.field.name}, ${c.field.area_ha} ha${c.season ? ` — ${c.season}` : ""}`}
        actions={!closed && (
          <>
            <Button variant="secondary" icon="Leaf" onClick={() => { setStage({ stage: c.growth_stages[0] ?? "", observed_on: todayISO(), notes: "" }); setStageOpen(true); }}>Record stage</Button>
            <LinkButton to={`/app/observations?cycle=${c.id}`} variant="primary" icon="Camera">Add photo</LinkButton>
          </>
        )}
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Panel title="Harvest safety" actions={<LinkButton to={`/app/harvest?cycle=${c.id}`} size="sm" variant="ghost">Spray records</LinkButton>}>
            {harvest ? (
              <div className="space-y-3">
                <StatusBadge status={harvest.assessment.status} />
                <HarvestStrip a={harvest.assessment} />
              </div>
            ) : <Loading rows={1} />}
          </Panel>
          <Panel title="Crop timeline">
            {timeline?.length ? (
              <ol className="relative before:absolute before:top-2 before:bottom-2 before:left-4 before:w-px before:bg-line">
                {timeline.map((t) => <TimelineItem key={`${t.kind}-${t.id}-${t.date}`} t={t} />)}
              </ol>
            ) : <Loading rows={2} />}
          </Panel>
        </div>
        <div className="space-y-6">
          <Panel title="Cycle details" actions={!closed && <Button size="sm" variant="ghost" onClick={() => { setDates({ fs: c.expected_flowering_start ?? "", fe: c.expected_flowering_end ?? "", harvest: c.expected_harvest_date ?? "" }); setEditOpen(true); }}>Edit dates</Button>}>
            <div className="grid grid-cols-2 gap-4">
              <KV label="Status"><StatusBadge status={c.status} /></KV>
              <KV label="Current stage">{c.current_stage ?? "—"}</KV>
              <KV label="Sown">{fmtDate(c.sowing_date)}</KV>
              <KV label="Expected harvest">{fmtDate(c.expected_harvest_date)}</KV>
              <div className="col-span-2"><KV label="Expected flowering">{c.expected_flowering_start ? `${fmtShort(c.expected_flowering_start)} – ${fmtShort(c.expected_flowering_end)}` : "Not set"}</KV></div>
            </div>
            {!closed && (
              <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
                {c.pollinator_dependent && <LinkButton to={`/app/pollination?cycle=${c.id}`} size="sm" icon="Flower2">Find pollination</LinkButton>}
                <LinkButton to={`/app/harvest?cycle=${c.id}&record=1`} size="sm" icon="FlaskConical">Record spray</LinkButton>
                {c.status !== "planned" && <LinkButton to={`/app/batches?cycle=${c.id}`} size="sm" icon="Package">Record harvest batch</LinkButton>}
              </div>
            )}
          </Panel>
          <Panel title="Crop-health model">
            <p className="text-sm text-charcoal">{c.vision_supported ? `Leaf photos of ${c.crop.name.toLowerCase()} can be analysed by the crop-vision model.` : `${c.crop.name} isn't covered by the crop-vision model. Photos are saved for agronomist review.`}</p>
          </Panel>
          {!closed && <Button variant="quiet" size="sm" onClick={() => setCloseOpen(true)}>Close this cycle</Button>}
        </div>
      </div>

      <Dialog open={stageOpen} onClose={() => setStageOpen(false)} title="Record growth stage" footer={<><Button variant="ghost" onClick={() => setStageOpen(false)}>Cancel</Button><Button loading={addStage.pending} onClick={async () => { if (await addStage.run(undefined)) { setStageOpen(false); toast("Stage recorded"); refresh(); } }}>Save stage</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Stage" htmlFor="st"><Select id="st" value={stage.stage} onChange={(e) => setStage({ ...stage, stage: e.target.value })}>{c.growth_stages.map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Observed on" htmlFor="sto"><Input id="sto" type="date" max={todayISO()} value={stage.observed_on} onChange={(e) => setStage({ ...stage, observed_on: e.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Notes" htmlFor="stn" optional><Textarea id="stn" value={stage.notes} onChange={(e) => setStage({ ...stage, notes: e.target.value })} /></Field></div>
        </div>
        <div className="mt-4"><FormError error={addStage.error} /></div>
      </Dialog>

      <Dialog open={editOpen} onClose={() => setEditOpen(false)} title="Edit expected dates" footer={<><Button variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button><Button loading={update.pending} onClick={async () => { if (await update.run({ expected_flowering_start: dates.fs || null, expected_flowering_end: dates.fe || null, expected_harvest_date: dates.harvest || null })) { setEditOpen(false); toast("Dates updated"); refresh(); } }}>Save dates</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Flowering from" htmlFor="efs"><Input id="efs" type="date" value={dates.fs} onChange={(e) => setDates({ ...dates, fs: e.target.value })} /></Field>
          <Field label="Flowering until" htmlFor="efe"><Input id="efe" type="date" value={dates.fe} onChange={(e) => setDates({ ...dates, fe: e.target.value })} /></Field>
          <Field label="Expected harvest" htmlFor="eh"><Input id="eh" type="date" value={dates.harvest} onChange={(e) => setDates({ ...dates, harvest: e.target.value })} /></Field>
        </div>
        <div className="mt-4"><FormError error={update.error} /></div>
      </Dialog>

      <ConfirmDialog open={closeOpen} onClose={() => setCloseOpen(false)} title="Close this crop cycle?" confirmLabel="Close cycle" tone="danger" pending={update.pending} error={update.error}
        onConfirm={async () => { if (await update.run({ status: "closed" })) { setCloseOpen(false); toast("Cycle closed"); refresh(); } }}>
        <p>The field becomes free for a new crop. Records stay in history and can't be edited afterwards.</p>
      </ConfirmDialog>
    </>
  );
}
