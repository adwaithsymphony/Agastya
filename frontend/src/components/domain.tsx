import type { ReactNode } from "react";
import { addDays, conditionLabel, fmtDate, fmtShort, pct } from "../lib/format";
import type { Assessment, Prediction } from "../lib/types";
import { Icon } from "./icons";
import { Badge, cn, StatusBadge } from "./ui";

/** Day-by-day strip from today to the earliest eligible harvest date. */
export function FictionalReferenceNotice({ a }: { a: Assessment }) {
  if (!a.uses_fictional_reference) return null;
  return (
    <p className="mt-3 flex items-start gap-2 rounded-md border border-earth/30 bg-beige/60 px-3 py-2 text-[13px] text-[#5b4a2f]">
      <Icon name="TriangleAlert" size={15} className="mt-0.5 shrink-0" />
      <span>Calculated from fictional sample label rules. Not valid for real harvest decisions — verify against the approved product label.</span>
    </p>
  );
}

export function HarvestStrip({ a, compact }: { a: Assessment; compact?: boolean }) {
  return (
    <>
      <HarvestStripInner a={a} compact={compact} />
      {!compact && <FictionalReferenceNotice a={a} />}
    </>
  );
}

function HarvestStripInner({ a, compact }: { a: Assessment; compact?: boolean }) {
  const today = a.as_of_date;
  if (a.status === "eligible") {
    return (
      <div className="text-sm text-charcoal">
        {a.outcomes.length ? "All recorded intervals have passed." : "No pesticide applications recorded for this crop."}
        {!compact && <span className="text-muted"> Status reflects recorded PHI rules only.</span>}
      </div>
    );
  }
  if (a.status === "unknown" && !a.earliest_eligible_date) {
    return (
      <div className="flex items-center gap-2 rounded-md bg-[repeating-linear-gradient(135deg,var(--color-amber-soft)_0_8px,#fbf3e3_8px_16px)] px-3 py-2.5 text-sm font-medium text-amber">
        <Icon name="CircleHelp" size={16} /> Eligibility can't be calculated until label data is verified.
      </div>
    );
  }
  const days = Math.max(a.days_until_eligible ?? 0, 0);
  const shown = Math.min(Math.max(days + 1, 5), 14);
  return (
    <div>
      <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${shown}, minmax(0, 1fr))` }} aria-hidden="true">
        {Array.from({ length: shown }).map((_, i) => {
          const d = addDays(today, i);
          const isElig = i === days;
          const blocked = i < days;
          return (
            <div key={i} className="min-w-0">
              <div className={cn("h-7 rounded-sm", blocked ? "bg-danger/15" : isElig ? "bg-forest" : "bg-sage-pale", i === 0 && "ring-2 ring-charcoal/60 ring-offset-1 ring-offset-paper")} />
              {!compact && (i === 0 || isElig) && <div className={cn("mt-1 truncate text-[11px]", isElig ? "font-semibold text-forest" : "text-muted")}>{i === 0 ? "Today" : fmtShort(d)}</div>}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-sm">
        <span className="font-semibold text-forest-ink">Eligible from {fmtDate(a.earliest_eligible_date)}</span>
        <span className="text-muted"> — {days} day{days === 1 ? "" : "s"} remaining under recorded rules.</span>
      </p>
      {a.unresolved_count > 0 && (
        <p className="mt-1.5 flex items-center gap-1.5 text-[13px] font-medium text-amber">
          <Icon name="TriangleAlert" size={14} /> {a.unresolved_count} application{a.unresolved_count > 1 ? "s" : ""} not counted — label data needs verification.
        </p>
      )}
    </div>
  );
}

const REASON_TEXT: Record<string, string> = {
  low_confidence: "The model wasn't confident. Take a clearer photo of one leaf in daylight, or wait for an agronomist's review.",
  predicted_crop_mismatch: "The model recognised a different crop from the one in this crop cycle. Check the photo, or wait for review.",
  crop_not_covered_by_model: "This crop isn't covered by the current model, so no reading is shown. An agronomist can review the photo.",
  image_not_recognised_as_leaf: "The photo doesn't look like a single leaf, so no reading is shown. Photograph one leaf against a plain background.",
  model_files_missing: "The crop-vision model isn't installed on this server. The photo is saved and can be analysed later.",
  inference_error: "The analysis failed for this image. The photo is saved; try re-analysing later.",
  condition_detected: "A possible problem was detected. It has been queued for agronomist review — confirm before treating.",
};

export function PredictionPanel({ p, cropHasModel }: { p: Prediction | null; cropHasModel?: boolean }) {
  if (!p) return <p className="text-sm text-muted">No analysis yet.</p>;
  const showReading = p.status === "completed" || p.status === "uncertain";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={p.status} />
        {p.review_recommended && <Badge tone="water" icon="ClipboardCheck">Review recommended</Badge>}
      </div>
      {showReading && p.predicted_condition && (
        <div>
          <div className="text-xs text-muted">Model reading</div>
          <div className="text-xl font-bold text-forest-ink">
            {p.predicted_crop} — {conditionLabel(p.predicted_condition)}
          </div>
          <ConfidenceBar value={p.confidence} />
        </div>
      )}
      {p.status_reason && REASON_TEXT[p.status_reason] && (
        <p className={cn("rounded-md px-3 py-2.5 text-sm", p.status === "failed" ? "bg-danger-soft text-danger" : p.status === "completed" ? "bg-water-soft text-water" : "bg-amber-soft text-[#7a5212]")}>
          {REASON_TEXT[p.status_reason]}
        </p>
      )}
      {showReading && p.top_k.length > 1 && (
        <div>
          <div className="mb-1.5 text-xs text-muted">Other possibilities</div>
          <ul className="space-y-1 text-sm">
            {p.top_k.slice(1).map((t) => (
              <li key={t.class} className="flex justify-between gap-3"><span>{t.crop} — {conditionLabel(t.condition)}</span><span className="num text-muted">{pct(t.probability)}</span></li>
            ))}
          </ul>
        </div>
      )}
      {cropHasModel === false && p.status !== "unsupported_input" && <p className="text-xs text-muted">This crop isn't covered by the model.</p>}
      <p className="text-xs text-muted">
        {p.model_version ? `Model ${p.model_key} v${p.model_version}` : "No model output"}{p.processing_ms !== null ? `, ${p.processing_ms} ms` : ""}. Decision support only — not a diagnosis.
      </p>
    </div>
  );
}

export function ConfidenceBar({ value }: { value: number | null }) {
  if (value === null) return null;
  const v = Math.round(value * 100);
  return (
    <div className="mt-2 flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-sage-pale" role="meter" aria-valuenow={v} aria-valuemin={0} aria-valuemax={100} aria-label="Model confidence">
        <div className={cn("h-full rounded-full", v >= 70 ? "bg-forest" : "bg-amber")} style={{ width: `${v}%` }} />
      </div>
      <span className="num shrink-0 text-right text-sm font-semibold whitespace-nowrap">{v}% confidence</span>
    </div>
  );
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="text-sm font-semibold text-charcoal">{children}</div>
    </div>
  );
}

export function UrgencyBadge({ urgency, daysLeft }: { urgency: string; daysLeft: number | null }) {
  if (urgency === "unknown") return <Badge tone="neutral">Shelf life not recorded</Badge>;
  const txt = daysLeft === null ? "" : daysLeft < 0 ? "Past sell-by" : daysLeft === 0 ? "Sell today" : `${daysLeft} day${daysLeft === 1 ? "" : "s"} left`;
  return <Badge tone={urgency === "critical" ? "danger" : urgency === "high" ? "amber" : "sage"} icon="Timer">{txt}</Badge>;
}
