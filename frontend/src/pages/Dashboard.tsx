import { UrgencyBadge } from "../components/domain";
import { Icon } from "../components/icons";
import { Badge, EmptyState, ErrorState, LinkButton, Loading, Metric, PageHeader, Panel, StatusBadge, Table, Td, Th, cn } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/data";
import { conditionLabel, fmtDate, fmtKg, fmtShort, human, pct, relDays, timeAgo } from "../lib/format";
import { Link } from "../lib/router";
import type { Batch, Booking, CycleBrief, Demand, Observation } from "../lib/types";
import AdminDashboard from "./admin/AdminDashboard";

type Attention = { kind: string; title: string; link: string; severity: string };
type Recent = { id: number; title: string; body: string | null; link: string | null; created_at: string; severity: string; read: boolean };

function AttentionList({ items }: { items: Attention[] }) {
  if (!items.length)
    return <EmptyState icon="Leaf" title="Nothing needs your attention" body="Restrictions, bookings and deliveries are all on track." />;
  return (
    <ul className="divide-y divide-line/70">
      {items.map((a, i) => (
        <li key={i}>
          <Link to={a.link} className="flex items-center gap-3 px-5 py-3.5 hover:bg-cream/70">
            <span className={cn("size-2.5 shrink-0 rounded-full", a.severity === "critical" ? "bg-danger" : a.severity === "warning" ? "bg-amber" : "bg-water")} aria-hidden="true" />
            <span className="flex-1 text-sm font-medium text-charcoal">{a.title}</span>
            <Icon name="ChevronRight" size={16} className="text-muted" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RecentList({ items }: { items: Recent[] }) {
  if (!items.length) return <p className="text-sm text-muted">No activity yet.</p>;
  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {items.map((r) => (
        <li key={r.id} className="relative">
          <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-paper bg-sage" aria-hidden="true" />
          {r.link ? <Link to={r.link} className="text-sm font-semibold text-charcoal hover:text-forest">{r.title}</Link> : <span className="text-sm font-semibold">{r.title}</span>}
          {r.body && <p className="text-[13px] text-muted">{r.body}</p>}
          <p className="text-[11px] text-muted">{timeAgo(r.created_at)}</p>
        </li>
      ))}
    </ol>
  );
}

type FarmerDash = {
  today: string;
  metrics: Record<string, number>;
  attention: Attention[];
  cycles: CycleBrief[];
  harvest: { cycle: CycleBrief; status: string; earliest_eligible_date: string | null; days_until_eligible: number | null; unresolved_count: number }[];
  flowering: (CycleBrief & { has_open_booking: boolean; pollinator_dependent: boolean; days_to_flowering: number })[];
  bookings: Booking[];
  batches: Batch[];
  recent_observations: Observation[];
  recent: Recent[];
};

function FarmerDashboard({ d }: { d: FarmerDash }) {
  const m = d.metrics;
  return (
    <div className="space-y-6">
      <Panel title="Needs attention" pad={false} subtitle={d.attention.length ? `${d.attention.length} item${d.attention.length > 1 ? "s" : ""}` : undefined}>
        <AttentionList items={d.attention} />
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric icon="Sprout" label="Active crop cycles" value={m.active_cycles} hint={`${m.fields} fields`} to="/app/farms" />
        <Metric icon="Lock" tone={m.harvest_restricted ? "danger" : "forest"} label="Harvest restrictions" value={m.harvest_restricted} hint={m.harvest_unknown ? `${m.harvest_unknown} need label verification` : "Under recorded PHI rules"} to="/app/harvest" />
        <Metric icon="Flower2" tone="water" label="Open pollination bookings" value={m.open_bookings} to="/app/pollination" />
        <Metric icon="Package" tone={m.batches_needing_destination ? "amber" : "forest"} label="Batches needing a buyer" value={m.batches_needing_destination} hint={m.rerouted_delivered_kg ? `${fmtKg(m.rerouted_delivered_kg)} rerouted and delivered` : undefined} to="/app/batches" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Harvest restrictions" actions={<LinkButton to="/app/harvest" variant="ghost" size="sm">Open</LinkButton>} pad={false}>
          {d.harvest.length ? (
            <ul className="divide-y divide-line/70">
              {d.harvest.map((h) => (
                <li key={h.cycle.id} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <Link to={`/app/harvest?cycle=${h.cycle.id}`} className="text-sm font-semibold hover:text-forest">{h.cycle.crop.name}</Link>
                    <div className="truncate text-xs text-muted">{h.cycle.field.name}, {h.cycle.farm.name}</div>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={h.status} label={h.status === "eligible" ? "Eligible" : undefined} />
                    {h.earliest_eligible_date && (h.status === "restricted" || h.status === "upcoming") && (
                      <div className="mt-0.5 text-xs text-muted">from {fmtShort(h.earliest_eligible_date)} ({relDays(h.days_until_eligible)})</div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No active crop cycles" />}
        </Panel>

        <Panel title="Flowering in the next 60 days" actions={<LinkButton to="/app/pollination" variant="ghost" size="sm">Pollination</LinkButton>} pad={false}>
          {d.flowering.length ? (
            <ul className="divide-y divide-line/70">
              {d.flowering.map((c) => (
                <li key={c.id} className="flex items-center gap-4 px-5 py-3">
                  <div className="w-14 shrink-0 text-center">
                    <div className="num text-lg leading-none font-bold text-forest-ink">{c.days_to_flowering <= 0 ? "Now" : c.days_to_flowering}</div>
                    <div className="text-[11px] text-muted">{c.days_to_flowering <= 0 ? "flowering" : "days"}</div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold">{c.crop.name} · {c.field.name}</div>
                    <div className="text-xs text-muted">{fmtShort(c.expected_flowering_start)} – {fmtShort(c.expected_flowering_end)}</div>
                  </div>
                  {c.has_open_booking ? <Badge tone="sage">Booked</Badge> : c.pollinator_dependent ? <Badge tone="amber">Not booked</Badge> : <Badge>Self-pollinating</Badge>}
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="Flower2" title="No flowering expected soon" body="Add expected flowering dates to your crop cycles to plan pollination." />}
        </Panel>
      </div>

      <Panel title="Produce batches" actions={<LinkButton to="/app/batches" variant="ghost" size="sm">All batches</LinkButton>} pad={false}>
        {d.batches.length ? (
          <Table>
            <thead><tr><Th>Batch</Th><Th>Quantity</Th><Th>Destination</Th><Th>Shelf life</Th><Th>Status</Th></tr></thead>
            <tbody>
              {d.batches.map((b) => (
                <tr key={b.id} className="hover:bg-cream/60">
                  <Td><Link to={`/app/batches/${b.id}`} className="font-semibold hover:text-forest">{b.code}</Link><div className="text-xs text-muted">{b.crop.name}, grade {b.grade}</div></Td>
                  <Td className="num">{fmtKg(b.quantity_kg)}</Td>
                  <Td>{b.current_assignment ? b.current_assignment.buyer.display_name : <span className="text-muted">—</span>}</Td>
                  <Td><UrgencyBadge urgency={b.urgency} daysLeft={b.days_left} /></Td>
                  <Td><StatusBadge status={b.status} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : <EmptyState icon="Package" title="No active batches" body="Record a harvested batch to find buyers." action={<LinkButton to="/app/batches" variant="primary" size="sm">Record a batch</LinkButton>} />}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Recent crop observations" actions={<LinkButton to="/app/observations" variant="ghost" size="sm" icon="Camera">New observation</LinkButton>} pad={false}>
          {d.recent_observations.length ? (
            <ul className="divide-y divide-line/70">
              {d.recent_observations.map((o) => (
                <li key={o.id}>
                  <Link to={`/app/observations/${o.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-cream/60">
                    <img src={`/api/v1/observations/${o.id}/image`} alt="" className="size-11 rounded-md object-cover" loading="lazy" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">
                        {o.prediction?.predicted_condition && (o.status === "completed" || o.status === "uncertain") ? `${conditionLabel(o.prediction.predicted_condition)} (${pct(o.prediction.confidence)})` : human(o.status)}
                      </div>
                      <div className="text-xs text-muted">{o.cycle.crop} · {o.cycle.field} · {fmtShort(o.observed_at)}</div>
                    </div>
                    <StatusBadge status={o.review_status === "not_required" ? o.status : o.review_status} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="Camera" title="No observations yet" />}
        </Panel>
        <Panel title="Recent activity"><RecentList items={d.recent} /></Panel>
      </div>
    </div>
  );
}

function ProviderDashboard({ d }: { d: { metrics: Record<string, number>; requests: Booking[]; upcoming: Booking[]; capacity_weeks: { week_start: string; available: number; committed: number }[]; recent: Recent[]; profile: { colonies_total: number } } }) {
  const max = Math.max(1, ...d.capacity_weeks.map((w) => w.available));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric icon="Send" tone={d.metrics.incoming_requests ? "amber" : "forest"} label="Requests to answer" value={d.metrics.incoming_requests} to="/app/provider/bookings" />
        <Metric icon="CalendarDays" label="Upcoming services" value={d.metrics.upcoming_services} />
        <Metric icon="Clock" tone="water" label="Waiting on farmers" value={d.metrics.awaiting_farmer} />
        <Metric icon="Hexagon" tone="earth" label="Colonies managed" value={d.metrics.colonies_total} to="/app/provider/profile" />
      </div>
      <Panel title="Requests to answer" pad={false} actions={<LinkButton to="/app/provider/bookings" variant="ghost" size="sm">All bookings</LinkButton>}>
        {d.requests.length ? (
          <ul className="divide-y divide-line/70">
            {d.requests.map((b) => (
              <li key={b.id}>
                <Link to={`/app/provider/bookings?id=${b.id}`} className="flex flex-wrap items-center gap-3 px-5 py-3.5 hover:bg-cream/60">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold">{b.cycle.crop}, {b.cycle.area_ha} ha — {b.cycle.district}</div>
                    <div className="text-xs text-muted">{b.colonies_requested} colonies, {fmtShort(b.start_date)} – {fmtShort(b.end_date)}</div>
                  </div>
                  <span className="text-sm font-semibold text-forest">Respond</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : <EmptyState icon="CalendarDays" title="No open requests" />}
      </Panel>
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="Colony capacity, next 8 weeks" subtitle="Committed colonies against your published availability">
          {d.capacity_weeks.some((w) => w.available) ? (
            <div className="flex h-44 items-end gap-2" role="img" aria-label="Weekly capacity chart">
              {d.capacity_weeks.map((w) => (
                <div key={w.week_start} className="flex flex-1 flex-col items-center gap-1.5">
                  <div className="relative w-full overflow-hidden rounded-t-md bg-sage-pale" style={{ height: `${(w.available / max) * 140}px`, minHeight: 4 }}>
                    <div className="absolute inset-x-0 bottom-0 bg-forest" style={{ height: `${w.available ? (w.committed / w.available) * 100 : 0}%` }} />
                  </div>
                  <span className="text-[10px] text-muted">{fmtShort(w.week_start)}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState icon="Calendar" title="No availability published" action={<LinkButton to="/app/provider/profile" size="sm">Add availability</LinkButton>} />}
          <div className="mt-3 flex gap-4 text-xs text-muted"><span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-forest" />Committed</span><span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-sage-pale" />Available</span></div>
        </Panel>
        <Panel title="Upcoming services" pad={false}>
          {d.upcoming.length ? (
            <ul className="divide-y divide-line/70">
              {d.upcoming.map((b) => (
                <li key={b.id} className="px-5 py-3">
                  <div className="text-sm font-semibold">{fmtShort(b.start_date)} – {fmtShort(b.end_date)}</div>
                  <div className="text-xs text-muted">{b.cycle.crop} at {b.cycle.farm}, {b.cycle.village ?? b.cycle.district} · {b.colonies_requested} colonies</div>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="Calendar" title="Nothing scheduled" />}
        </Panel>
      </div>
      <Panel title="Recent activity"><RecentList items={d.recent} /></Panel>
    </div>
  );
}

type Delivery = { id: number; status: string; quantity_kg: number; shipment: { status: string; scheduled_date: string | null } | null; batch: { code: string; crop: string; grade: string; source_district: string | null } };
function BuyerDashboard({ d }: { d: { metrics: Record<string, number>; demands: Demand[]; deliveries: Delivery[]; matching: { batch_code: string; crop: string; grade: string; quantity_kg: number; sell_by: string | null; district: string | null; distance_km: number | null }[]; recent: Recent[] } }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric icon="Store" label="Open demand listings" value={d.metrics.open_demands} to="/app/buyer/demands" />
        <Metric icon="Scale" tone="earth" label="Unfilled demand" value={fmtKg(d.metrics.open_demand_kg)} />
        <Metric icon="Truck" tone="water" label="Active deliveries" value={d.metrics.active_deliveries} to="/app/buyer/deliveries" />
        <Metric icon="Package" tone="amber" label="Matching batches available" value={d.metrics.matching_batches} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Incoming deliveries" pad={false} actions={<LinkButton to="/app/buyer/deliveries" variant="ghost" size="sm">Manage</LinkButton>}>
          {d.deliveries.length ? (
            <ul className="divide-y divide-line/70">
              {d.deliveries.map((x) => (
                <li key={x.id} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div><div className="text-sm font-semibold">{x.batch.code} — {fmtKg(x.quantity_kg)} {x.batch.crop}</div><div className="text-xs text-muted">Grade {x.batch.grade} from {x.batch.source_district} · scheduled {fmtShort(x.shipment?.scheduled_date)}</div></div>
                  {x.shipment && <StatusBadge status={x.shipment.status} />}
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="Truck" title="No active deliveries" />}
        </Panel>
        <Panel title="Produce matching your demand" subtitle="Batches looking for a buyer right now" pad={false}>
          {d.matching.length ? (
            <ul className="divide-y divide-line/70">
              {d.matching.map((m) => (
                <li key={m.batch_code} className="px-5 py-3">
                  <div className="text-sm font-semibold">{fmtKg(m.quantity_kg)} {m.crop}, grade {m.grade}</div>
                  <div className="text-xs text-muted">{m.district}{m.distance_km !== null ? `, about ${Math.round(m.distance_km)} km` : ""} · sell by {fmtShort(m.sell_by)}</div>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="Package" title="No matching batches right now" />}
        </Panel>
      </div>
      <Panel title="Open demand" pad={false}>
        {d.demands.length ? (
          <Table>
            <thead><tr><Th>Crop</Th><Th>Grades</Th><Th>Remaining</Th><Th>Delivery window</Th><Th>Valid until</Th></tr></thead>
            <tbody>{d.demands.map((x) => (
              <tr key={x.id}><Td className="font-semibold">{x.crop.name}</Td><Td>{x.accepted_grades.join(", ")}</Td><Td className="num">{fmtKg(x.remaining_kg)} <span className="text-muted">of {fmtKg(x.quantity_kg)}</span></Td><Td>{fmtShort(x.delivery_start)} – {fmtShort(x.delivery_end)}</Td><Td>{fmtDate(x.valid_until)}</Td></tr>
            ))}</tbody>
          </Table>
        ) : <EmptyState icon="Store" title="No open demand" action={<LinkButton to="/app/buyer/demands" variant="primary" size="sm">Post demand</LinkButton>} />}
      </Panel>
    </div>
  );
}

function ReviewerDashboard({ d }: { d: { metrics: Record<string, number>; queue: Observation[]; history: { id: number; observation_id: number; decision: string; reviewed_label: string | null; created_at: string }[]; recent: Recent[] } }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric icon="ClipboardCheck" tone={d.metrics.awaiting_review ? "amber" : "forest"} label="Awaiting review" value={d.metrics.awaiting_review} to="/app/review" />
        <Metric icon="CircleHelp" tone="amber" label="Uncertain predictions" value={d.metrics.uncertain} />
        <Metric icon="Ban" tone="earth" label="Unsupported inputs" value={d.metrics.unsupported} />
        <Metric icon="ListChecks" label="Reviews you've recorded" value={d.metrics.my_reviews} />
      </div>
      <Panel title="Oldest first" pad={false} actions={<LinkButton to="/app/review" variant="ghost" size="sm">Open queue</LinkButton>}>
        {d.queue.length ? (
          <ul className="divide-y divide-line/70">
            {d.queue.map((o) => (
              <li key={o.id}>
                <Link to={`/app/observations/${o.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-cream/60">
                  <img src={`/api/v1/observations/${o.id}/image`} alt="" className="size-12 rounded-md object-cover" loading="lazy" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold">{o.cycle.crop} — {o.cycle.farm}, {o.cycle.district}</div>
                    <div className="text-xs text-muted">{fmtDate(o.observed_at)} · {o.prediction?.predicted_condition ? `model: ${conditionLabel(o.prediction.predicted_condition)} ${pct(o.prediction.confidence)}` : human(o.status)}</div>
                  </div>
                  <StatusBadge status={o.status} />
                </Link>
              </li>
            ))}
          </ul>
        ) : <EmptyState icon="ClipboardCheck" title="Queue is clear" />}
      </Panel>
      <Panel title="Your recent reviews" pad={false}>
        {d.history.length ? (
          <ul className="divide-y divide-line/70">{d.history.map((h) => (
            <li key={h.id}><Link to={`/app/observations/${h.observation_id}`} className="flex justify-between gap-3 px-5 py-3 text-sm hover:bg-cream/60"><span><span className="font-semibold">{human(h.decision)}</span>{h.reviewed_label ? ` — ${h.reviewed_label}` : ""}</span><span className="text-muted">{timeAgo(h.created_at)}</span></Link></li>
          ))}</ul>
        ) : <p className="p-5 text-sm text-muted">No reviews yet.</p>}
      </Panel>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data, error, loading, reload } = useApi<any>("/dashboard");
  const today = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  return (
    <>
      <PageHeader title="Overview" subtitle={`${today}${user?.organization_name ? ` — ${user.organization_name}` : ""}`} />
      {loading && !data ? <Loading rows={5} /> : error ? <ErrorState error={error} onRetry={reload} /> : data ? (
        data.role === "farmer" ? <FarmerDashboard d={data} /> :
        data.role === "provider" ? (data.profile_missing ? <EmptyState title="No provider profile linked to this account" /> : <ProviderDashboard d={data} />) :
        data.role === "buyer" ? (data.profile_missing ? <EmptyState title="No buyer profile linked to this account" /> : <BuyerDashboard d={data} />) :
        data.role === "reviewer" ? <ReviewerDashboard d={data} /> :
        <AdminDashboard d={data} />
      ) : null}
    </>
  );
}
