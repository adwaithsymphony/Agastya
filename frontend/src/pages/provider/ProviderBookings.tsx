import { useState } from "react";
import { Button, ConfirmDialog, Dialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, StatusBadge, Tabs, Textarea, cn, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { invalidate, useApi, useMutation } from "../../lib/data";
import { fmtDateTime, fmtShort, todayISO } from "../../lib/format";
import { useSearchParam } from "../../lib/router";
import type { Booking } from "../../lib/types";

type Tab = "requested" | "accepted" | "reschedule_proposed" | "history";

function BookingRow({ b, highlight }: { b: Booking; highlight: boolean }) {
  const toast = useToast();
  const [mode, setMode] = useState<null | "accept" | "reject" | "propose" | "complete" | "cancel">(null);
  const [note, setNote] = useState("");
  const [dates, setDates] = useState({ start: b.start_date, end: b.end_date });
  const t = useMutation((body: Record<string, unknown>) => api(`/pollination/bookings/${b.id}/transition`, { body: { version: b.version, ...body } }));
  const done = (msg: string) => { setMode(null); toast(msg); invalidate("/pollination", "/dashboard"); };
  const started = b.start_date <= todayISO();
  return (
    <li className={cn("rounded-lg border bg-white p-4", highlight ? "border-forest shadow-soft" : "border-line")}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{b.cycle.crop}, {b.cycle.area_ha} ha</span><StatusBadge status={b.status} /></div>
          <div className="text-sm">{b.cycle.farm}, {b.cycle.village ? `${b.cycle.village}, ` : ""}{b.cycle.district}</div>
          <div className="text-sm"><span className="font-semibold">{b.colonies_requested} colonies</span>, {fmtShort(b.start_date)} – {fmtShort(b.end_date)}{b.cycle.flowering_start && <span className="text-muted"> (flowering expected {fmtShort(b.cycle.flowering_start)} – {fmtShort(b.cycle.flowering_end)})</span>}</div>
          {b.status === "reschedule_proposed" && <div className="text-sm text-amber">You proposed {fmtShort(b.proposed_start_date)} – {fmtShort(b.proposed_end_date)}; waiting for the farmer.</div>}
          {b.farmer_note && <p className="text-[13px] text-muted">Farmer: “{b.farmer_note}”</p>}
          <p className="text-xs text-muted">Requested {fmtDateTime(b.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {b.status === "requested" && (
            <>
              <Button size="sm" onClick={() => { setNote(""); setMode("accept"); }}>Accept</Button>
              <Button size="sm" variant="secondary" onClick={() => { setNote(""); setDates({ start: b.start_date, end: b.end_date }); setMode("propose"); }}>Propose dates</Button>
              <Button size="sm" variant="quiet" onClick={() => { setNote(""); setMode("reject"); }}>Decline</Button>
            </>
          )}
          {b.status === "accepted" && (
            <>
              <Button size="sm" disabled={!started} title={started ? undefined : "Available once the service window starts"} onClick={() => setMode("complete")}>Mark completed</Button>
              {!started && <Button size="sm" variant="quiet" onClick={() => { setNote(""); setMode("cancel"); }}>Cancel</Button>}
            </>
          )}
        </div>
      </div>

      <ConfirmDialog open={mode === "accept"} onClose={() => setMode(null)} title="Accept this booking?" confirmLabel="Accept booking" pending={t.pending} error={t.error}
        onConfirm={async () => { if (await t.run({ to: "accepted", note: note || null })) done("Booking accepted"); }}>
        <p>{b.colonies_requested} colonies are reserved for {fmtShort(b.start_date)} – {fmtShort(b.end_date)}. Capacity is checked against your availability.</p>
        <Field label="Message to the farmer" htmlFor={`an${b.id}`} optional><Textarea id={`an${b.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </ConfirmDialog>
      <ConfirmDialog open={mode === "reject"} onClose={() => setMode(null)} title="Decline this request?" confirmLabel="Decline request" tone="danger" pending={t.pending} error={t.error}
        onConfirm={async () => { if (await t.run({ to: "rejected", note: note || null })) done("Request declined"); }}>
        <Field label="Reason for the farmer" htmlFor={`rn${b.id}`} optional><Textarea id={`rn${b.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </ConfirmDialog>
      <ConfirmDialog open={mode === "complete"} onClose={() => setMode(null)} title="Mark this service completed?" confirmLabel="Mark completed" pending={t.pending} error={t.error}
        onConfirm={async () => { if (await t.run({ to: "completed" })) done("Marked completed"); }}>
        <p>The farmer is notified and the colonies are released from this booking.</p>
      </ConfirmDialog>
      <ConfirmDialog open={mode === "cancel"} onClose={() => setMode(null)} title="Cancel an accepted booking?" confirmLabel="Cancel booking" tone="danger" pending={t.pending} error={t.error}
        onConfirm={async () => { if (await t.run({ to: "cancelled", note: note || null })) done("Booking cancelled"); }}>
        <p>The farmer will need to find another provider before flowering.</p>
        <Field label="Reason" htmlFor={`cn${b.id}`} optional><Textarea id={`cn${b.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </ConfirmDialog>
      <Dialog open={mode === "propose"} onClose={() => setMode(null)} title="Propose different dates" footer={<><Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button><Button loading={t.pending} onClick={async () => { if (await t.run({ to: "reschedule_proposed", start_date: dates.start, end_date: dates.end, note: note || null })) done("New dates proposed"); }}>Send proposal</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="From" htmlFor={`ps${b.id}`}><Input id={`ps${b.id}`} type="date" min={todayISO()} value={dates.start} onChange={(e) => setDates({ ...dates, start: e.target.value })} /></Field>
          <Field label="Until" htmlFor={`pe${b.id}`}><Input id={`pe${b.id}`} type="date" min={dates.start} value={dates.end} onChange={(e) => setDates({ ...dates, end: e.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Message" htmlFor={`pn${b.id}`} optional><Textarea id={`pn${b.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field></div>
        </div>
        <div className="mt-4"><FormError error={t.error} /></div>
      </Dialog>
    </li>
  );
}

export default function ProviderBookings() {
  const focus = useSearchParam("id");
  const { data, error, loading, reload } = useApi<Booking[]>("/pollination/bookings");
  const [tab, setTab] = useState<Tab>("requested");
  const groups: Record<Tab, Booking[]> = {
    requested: data?.filter((b) => b.status === "requested") ?? [],
    accepted: data?.filter((b) => b.status === "accepted").sort((a, b) => a.start_date.localeCompare(b.start_date)) ?? [],
    reschedule_proposed: data?.filter((b) => b.status === "reschedule_proposed") ?? [],
    history: data?.filter((b) => ["completed", "cancelled", "rejected"].includes(b.status)) ?? [],
  };
  return (
    <>
      <PageHeader title="Bookings" subtitle="Requests from farmers, your schedule and past services." />
      {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <Panel pad={false}>
          <div className="px-3 pt-1">
            <Tabs value={tab} onChange={setTab} items={[
              { value: "requested", label: "New requests", count: groups.requested.length },
              { value: "accepted", label: "Scheduled", count: groups.accepted.length },
              { value: "reschedule_proposed", label: "Awaiting farmer", count: groups.reschedule_proposed.length },
              { value: "history", label: "History", count: groups.history.length },
            ]} />
          </div>
          <div className="p-5">
            {groups[tab].length ? <ul className="space-y-3">{groups[tab].map((b) => <BookingRow key={`${b.id}-${b.version}`} b={b} highlight={String(b.id) === focus} />)}</ul> : <EmptyState icon="CalendarDays" title="Nothing here" />}
          </div>
        </Panel>
      )}
    </>
  );
}
