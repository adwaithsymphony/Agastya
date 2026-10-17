import { useState } from "react";
import { PredictionPanel } from "../components/domain";
import { Button, ErrorState, Field, FormError, Input, LinkButton, Loading, PageHeader, Panel, StatusBadge, Textarea, cn, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { invalidate, useApi, useMutation } from "../lib/data";
import { conditionLabel, fmtDateTime, human, pct } from "../lib/format";
import { useParams } from "../lib/router";
import type { Observation } from "../lib/types";

const DECISIONS = [
  { value: "confirmed", label: "Confirm the model's reading" },
  { value: "corrected", label: "Correct it" },
  { value: "inconclusive", label: "Inconclusive — needs a field visit" },
  { value: "image_unusable", label: "Photo unusable" },
];

function ReviewForm({ o, onDone }: { o: Observation; onDone: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ decision: "confirmed", reviewed_label: "", notes: "", recommended_action: "" });
  const m = useMutation(() =>
    api(`/observations/${o.id}/reviews`, {
      body: {
        decision: f.decision,
        reviewed_label: f.reviewed_label || (f.decision === "confirmed" && o.prediction?.predicted_condition ? `${o.prediction.predicted_crop} — ${conditionLabel(o.prediction.predicted_condition)}` : null),
        notes: f.notes || null,
        recommended_action: f.recommended_action || null,
      },
    }),
  );
  const errs = m.error?.fieldErrors() ?? {};
  return (
    <Panel title="Record your review" subtitle="Stored separately from the model's output.">
      <fieldset className="space-y-2">
        <legend className="mb-2 text-[13px] font-semibold">Decision</legend>
        {DECISIONS.map((d) => (
          <label key={d.value} className={cn("flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 text-sm", f.decision === d.value ? "border-forest bg-sage-pale" : "border-line bg-white")}>
            <input type="radio" name="decision" value={d.value} checked={f.decision === d.value} onChange={() => setF({ ...f, decision: d.value })} className="accent-[var(--color-forest)]" />
            {d.label}
          </label>
        ))}
      </fieldset>
      <div className="mt-4 space-y-4">
        {(f.decision === "corrected" || f.decision === "inconclusive") && (
          <Field label="Your assessment" htmlFor="rl" error={errs[""] ?? errs.reviewed_label} optional={f.decision !== "corrected"}>
            <Input id="rl" value={f.reviewed_label} onChange={(e) => setF({ ...f, reviewed_label: e.target.value })} placeholder="e.g. Tomato — late blight" />
          </Field>
        )}
        <Field label="Notes for the farmer" htmlFor="rn" optional><Textarea id="rn" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <Field label="Recommended next step" htmlFor="ra" optional hint="Inspection or sampling advice. Treatment decisions belong to a field visit."><Input id="ra" value={f.recommended_action} onChange={(e) => setF({ ...f, recommended_action: e.target.value })} /></Field>
        <FormError error={m.error} />
        <Button loading={m.pending} onClick={async () => { if (await m.run(undefined)) { toast("Review recorded"); invalidate("/observations", "/reviews", "/dashboard"); onDone(); } }}>Save review</Button>
      </div>
    </Panel>
  );
}

export default function ObservationDetail() {
  const { obsId } = useParams<{ obsId: string }>();
  const { user } = useAuth();
  const toast = useToast();
  const { data: o, error, loading, reload } = useApi<Observation>(`/observations/${obsId}`);
  const re = useMutation(() => api<Observation>(`/observations/${obsId}/reanalyze`, { method: "POST" }));
  if (loading && !o) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!o) return null;
  const back = user?.role === "reviewer" ? { to: "/app/review", label: "Review queue" } : { to: "/app/observations", label: "Crop health" };
  return (
    <>
      <PageHeader
        back={back}
        title={`${o.cycle.crop} observation`}
        subtitle={`${o.cycle.field}, ${o.cycle.farm} (${o.cycle.district}) — ${fmtDateTime(o.observed_at)}`}
        actions={
          <>
            {user?.role === "farmer" && <LinkButton to={`/app/cycles/${o.cycle.id}`} variant="secondary">Crop cycle</LinkButton>}
            {o.can_reanalyze && (o.status === "failed" || o.status === "pending") && (
              <Button icon="RefreshCw" loading={re.pending} onClick={async () => { if (await re.run(undefined)) { toast("Re-analysed"); invalidate(`/observations`); } }}>Re-analyse</Button>
            )}
          </>
        }
      />
      <FormError error={re.error} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <figure className="overflow-hidden rounded-lg border border-line bg-forest-ink">
            <img src={`/api/v1/observations/${o.id}/image`} alt={`Leaf photo for ${o.cycle.crop}`} className="mx-auto max-h-[520px] w-full object-contain" />
            {o.image && <figcaption className="bg-paper px-4 py-2 text-xs text-muted">{o.image.width}×{o.image.height}px{o.image.source_note ? ` — ${o.image.source_note}` : ""}</figcaption>}
          </figure>
          {o.notes && <Panel title="Farmer's note"><p className="text-sm">{o.notes}</p></Panel>}
        </div>
        <div className="space-y-6">
          <Panel title="Model result" actions={<StatusBadge status={o.review_status} />}>
            <PredictionPanel p={o.prediction} cropHasModel={o.cycle.vision_supported} />
          </Panel>
          {o.reviews && o.reviews.length > 0 && (
            <Panel title="Agronomist review">
              <ul className="space-y-4">
                {o.reviews.map((r) => (
                  <li key={r.id} className="text-sm">
                    <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{human(r.decision)}</span>{r.reviewed_label && <span>— {r.reviewed_label}</span>}</div>
                    {r.notes && <p className="mt-1 text-charcoal">{r.notes}</p>}
                    {r.recommended_action && <p className="mt-1 rounded-md bg-sage-pale px-3 py-2 text-forest"><span className="font-semibold">Next step:</span> {r.recommended_action}</p>}
                    <p className="mt-1 text-xs text-muted">{r.reviewer}, {fmtDateTime(r.created_at)}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          {o.can_review && o.review_status !== "reviewed" && <ReviewForm o={o} onDone={reload} />}
          {o.predictions && o.predictions.length > 1 && (
            <Panel title="Analysis history">
              <ul className="space-y-2 text-sm">
                {o.predictions.map((p) => (
                  <li key={p.id} className="flex justify-between gap-3"><span>{fmtDateTime(p.created_at)} — {human(p.status)}{p.predicted_condition && p.status !== "unsupported_input" ? `, ${conditionLabel(p.predicted_condition)} ${pct(p.confidence)}` : ""}</span><span className="text-muted">{p.model_version ? `v${p.model_version}` : "no model"}</span></li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
