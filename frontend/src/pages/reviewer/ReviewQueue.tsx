import { useState } from "react";
import { EmptyState, ErrorState, Loading, PageHeader, Panel, StatusBadge, Tabs } from "../../components/ui";
import { useApi } from "../../lib/data";
import { conditionLabel, fmtDateTime, human, pct } from "../../lib/format";
import { Link } from "../../lib/router";
import type { Observation, Page, Review } from "../../lib/types";

export default function ReviewQueue() {
  const [tab, setTab] = useState<"queue" | "history">("queue");
  const queue = useApi<Page<Observation>>(tab === "queue" ? "/reviews/queue?page_size=50" : null);
  const hist = useApi<Page<Review & { observation: Observation }>>(tab === "history" ? "/reviews/history?page_size=50" : null);
  const cur = tab === "queue" ? queue : hist;
  return (
    <>
      <PageHeader title="Review queue" subtitle="Uncertain, unsupported and disease-flagged observations, oldest first." />
      <Panel pad={false}>
        <div className="px-3 pt-1">
          <Tabs value={tab} onChange={setTab} items={[{ value: "queue", label: "Awaiting review", count: queue.data?.total }, { value: "history", label: "Your reviews" }]} />
        </div>
        {cur.loading && !cur.data ? <div className="p-5"><Loading /></div> : cur.error ? <div className="p-5"><ErrorState error={cur.error} onRetry={cur.reload} /></div> : tab === "queue" ? (
          queue.data?.items.length ? (
            <ul className="divide-y divide-line/70">
              {queue.data.items.map((o) => (
                <li key={o.id}>
                  <Link to={`/app/observations/${o.id}`} className="flex flex-wrap items-center gap-4 px-5 py-4 hover:bg-cream/60">
                    <img src={`/api/v1/observations/${o.id}/image`} alt="" className="size-16 rounded-md object-cover" loading="lazy" />
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold">{o.cycle.crop} — {o.cycle.farm}, {o.cycle.district}</div>
                      <div className="text-sm">{o.prediction?.predicted_condition && o.status !== "unsupported_input" ? `Model: ${o.prediction.predicted_crop} — ${conditionLabel(o.prediction.predicted_condition)} (${pct(o.prediction.confidence)})` : human(o.prediction?.status_reason ?? o.status)}</div>
                      <div className="text-xs text-muted">{fmtDateTime(o.observed_at)}{o.notes ? ` — “${o.notes}”` : ""}</div>
                    </div>
                    <StatusBadge status={o.status} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="ClipboardCheck" title="Nothing waiting for review" />
        ) : hist.data?.items.length ? (
          <ul className="divide-y divide-line/70">
            {hist.data.items.map((r) => (
              <li key={r.id}><Link to={`/app/observations/${r.observation.id}`} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 text-sm hover:bg-cream/60">
                <span><span className="font-semibold">{human(r.decision)}</span>{r.reviewed_label ? ` — ${r.reviewed_label}` : ""}<span className="block text-xs text-muted">{r.observation.cycle.crop}, {r.observation.cycle.farm}</span></span>
                <span className="text-xs text-muted">{fmtDateTime(r.created_at)}</span>
              </Link></li>
            ))}
          </ul>
        ) : <EmptyState icon="ListChecks" title="No reviews recorded yet" />}
      </Panel>
    </>
  );
}
