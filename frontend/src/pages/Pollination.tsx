import { useEffect, useMemo, useState } from "react";
import { Icon } from "../components/icons";
import { Badge, Button, ConfirmDialog, Dialog, EmptyState, ErrorState, Field, FormError, Input, Loading, PageHeader, Panel, Select, StatusBadge, Textarea, cn, useToast } from "../components/ui";
import { api, idempotencyKey } from "../lib/api";
import { invalidate, useApi, useMutation } from "../lib/data";
import { addDays, daysBetween, fmtDateTime, fmtShort, todayISO } from "../lib/format";
import { useSearchParam } from "../lib/router";
import type { Booking, CycleBrief, ProviderMatch } from "../lib/types";

type Cal = { cycles: (CycleBrief & { pollinator_dependent: boolean })[]; bookings: Booking[] };
const SPAN = 90;

function FloweringCalendar({ cal }: { cal: Cal }) {
  const start = todayISO();
  const rows = cal.cycles.filter((c) => c.expected_flowering_start);
  const months = useMemo(() => {
    const out: { label: string; offset: number }[] = [];
    for (let i = 0; i < SPAN; i++) {
      const d = addDays(start, i);
      if (i === 0 || d.endsWith("-01")) out.push({ label: new Intl.DateTimeFormat("en-IN", { month: "short" }).format(new Date(`${d}T00:00:00`)), offset: i });
    }
    return out;
  }, [start]);
  const pos = (from: string, to: string) => {
    const a = Math.max(0, daysBetween(start, from));
    const b = Math.min(SPAN, daysBetween(start, to) + 1);
    return b <= 0 || a >= SPAN ? null : { left: `${(a / SPAN) * 100}%`, width: `${((b - a) / SPAN) * 100}%` };
  };
  if (!rows.length) return <EmptyState icon="Flower2" title="No flowering windows recorded" body="Add expected flowering dates to a crop cycle to see it here." />;
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[680px]">
        <div className="relative ml-44 h-6 border-b border-line text-[11px] text-muted">
          {months.map((m) => <span key={m.offset} className="absolute top-1 border-l border-line pl-1" style={{ left: `${(m.offset / SPAN) * 100}%` }}>{m.label}</span>)}
        </div>
        {rows.map((c) => {
          const fw = pos(c.expected_flowering_start!, c.expected_flowering_end!);
          const bs = cal.bookings.filter((b) => b.cycle.id === c.id && !["cancelled", "rejected"].includes(b.status));
          return (
            <div key={c.id} className="flex items-center border-b border-line/60 py-2.5">
              <div className="w-44 shrink-0 pr-3">
                <div className="truncate text-sm font-semibold">{c.crop.name}</div>
                <div className="truncate text-xs text-muted">{c.field.name}, {c.farm.name}</div>
              </div>
              <div className="relative h-9 flex-1 rounded-sm bg-[repeating-linear-gradient(90deg,transparent_0,transparent_calc(100%/13-1px),rgba(207,198,178,.35)_calc(100%/13-1px),rgba(207,198,178,.35)_calc(100%/13))]">
                {fw && <div className="absolute top-0 h-4 rounded-sm bg-sage/70" style={fw} title={`Flowering ${fmtShort(c.expected_flowering_start)} – ${fmtShort(c.expected_flowering_end)}`} />}
                {bs.map((b) => {
                  const p = pos(b.start_date, b.end_date);
                  return p && <div key={b.id} className={cn("absolute bottom-0 h-4 rounded-sm text-[10px] leading-4 font-semibold text-white", b.status === "accepted" || b.status === "completed" ? "bg-forest" : "border border-dashed border-forest bg-paper text-forest")} style={p} title={`${b.provider.display_name}: ${b.status}`}><span className="truncate px-1">{b.provider.display_name}</span></div>;
                })}
                {!fw && <span className="absolute top-2 text-xs text-muted">{c.expected_flowering_end! < start ? `Flowering ended ${fmtShort(c.expected_flowering_end)}` : `Flowers from ${fmtShort(c.expected_flowering_start)}`}</span>}
              </div>
            </div>
          );
        })}
        <div className="mt-3 ml-44 flex flex-wrap gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-sm bg-sage/70" />Expected flowering</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-sm bg-forest" />Confirmed booking</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-sm border border-dashed border-forest" />Awaiting provider</span>
        </div>
      </div>
    </div>
  );
}

function FindProviders({ cycles, bookings, initialCycle }: { cycles: Cal["cycles"]; bookings: Booking[]; initialCycle: string | null }) {
  const toast = useToast();
  const candidates = cycles.filter((c) => c.status !== "closed");
  const booked = new Set(bookings.filter((b) => ["requested", "accepted", "reschedule_proposed"].includes(b.status)).map((b) => b.cycle.id));
  const today = todayISO();
  const first = initialCycle ?? String(
    candidates.find((c) => c.pollinator_dependent && !booked.has(c.id) && (c.expected_flowering_end ?? "") >= today)?.id ??
      candidates.find((c) => c.pollinator_dependent)?.id ?? candidates[0]?.id ?? "",
  );
  const [cycleId, setCycleId] = useState(first);
  const cycle = candidates.find((c) => String(c.id) === cycleId);
  const [win, setWin] = useState({ start: "", end: "", colonies: "" });
  useEffect(() => {
    const today = todayISO();
    const s = cycle?.expected_flowering_start && cycle.expected_flowering_start > today ? cycle.expected_flowering_start : addDays(today, 7);
    const e = cycle?.expected_flowering_end && cycle.expected_flowering_end >= s ? cycle.expected_flowering_end : addDays(s, 14);
    setWin((w) => ({ start: s, end: e, colonies: w.colonies }));
  }, [cycleId]); // eslint-disable-line react-hooks/exhaustive-deps
  const path = cycleId && win.start && win.end ? `/pollination/providers/match?crop_cycle_id=${cycleId}&start_date=${win.start}&end_date=${win.end}${win.colonies ? `&colonies=${win.colonies}` : ""}` : null;
  const { data: matches, error, loading } = useApi<ProviderMatch[]>(path);
  const [booking, setBooking] = useState<ProviderMatch | null>(null);
  const [note, setNote] = useState("");
  const [key, setKey] = useState(idempotencyKey());
  const m = useMutation(() =>
    api("/pollination/bookings", {
      body: { crop_cycle_id: Number(cycleId), provider_id: booking!.provider.id, start_date: win.start, end_date: win.end, colonies_requested: Number(win.colonies), farmer_note: note || null },
      headers: { "Idempotency-Key": key },
    }),
  );
  return (
    <Panel title="Find a pollination provider" subtitle="Ranked by crop, coverage of your dates, free colonies and distance.">
      <div className="grid gap-4 md:grid-cols-4">
        <Field label="Crop cycle" htmlFor="pc">
          <Select id="pc" value={cycleId} onChange={(e) => setCycleId(e.target.value)}>
            {candidates.map((c) => <option key={c.id} value={c.id}>{c.crop.name} — {c.field.name}</option>)}
          </Select>
        </Field>
        <Field label="From" htmlFor="ps"><Input id="ps" type="date" min={todayISO()} value={win.start} onChange={(e) => setWin({ ...win, start: e.target.value })} /></Field>
        <Field label="Until" htmlFor="pe"><Input id="pe" type="date" min={win.start} value={win.end} onChange={(e) => setWin({ ...win, end: e.target.value })} /></Field>
        <Field label="Colonies needed" htmlFor="pn" hint="Ask your provider about colony density for your crop."><Input id="pn" type="number" min="1" value={win.colonies} onChange={(e) => setWin({ ...win, colonies: e.target.value })} /></Field>
      </div>
      {cycle && booked.has(cycle.id) && <p className="mt-3 text-[13px] text-amber">This crop cycle already has an open booking. Change its dates below instead of booking again for the same period.</p>}
      {cycle && !cycle.pollinator_dependent && <p className="mt-3 text-[13px] text-muted">{cycle.crop.name} is usually self-pollinating; providers may not list it.</p>}
      <div className="mt-5">
        {loading && !matches ? <Loading rows={2} /> : error ? <ErrorState error={error} /> : matches && (
          <ul className="space-y-3">
            {matches.map((r, i) => (
              <li key={r.provider.id} className={cn("rounded-lg border p-4", r.eligible ? "border-line bg-white" : "border-line/70 bg-cream/50")}>
                <div className="flex flex-wrap items-start gap-4">
                  <div className={cn("grid size-10 shrink-0 place-items-center rounded-full text-sm font-bold", r.eligible ? "bg-forest text-white" : "bg-[#ece6d8] text-muted")}>{r.eligible ? i + 1 : <Icon name="Ban" size={16} />}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{r.provider.display_name}</span>
                      <span className="text-xs text-muted">{r.provider.base_district}, {r.provider.base_state}</span>
                      {r.eligible && r.score !== null && <Badge tone="sage">Match {Math.round(r.score)}/100</Badge>}
                    </div>
                    <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
                      {(r.eligible ? r.reasons : r.exclusions).map((t) => (
                        <li key={t} className={cn("flex items-center gap-1.5", r.eligible ? "text-charcoal" : "text-muted")}>
                          <Icon name={r.eligible ? "Check" : "X"} size={13} className={r.eligible ? "text-forest" : ""} />{t}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {r.eligible && <Button size="sm" onClick={() => { setNote(""); setKey(idempotencyKey()); m.setError(null); setBooking(r); }} disabled={!win.colonies}>Request booking</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Dialog open={!!booking} onClose={() => setBooking(null)} title="Request pollination" footer={<><Button variant="ghost" onClick={() => setBooking(null)}>Cancel</Button><Button loading={m.pending} onClick={async () => { if (await m.run(undefined)) { setBooking(null); toast("Request sent to provider"); invalidate("/pollination", "/dashboard"); } }}>Send request</Button></>}>
        {booking && (
          <div className="space-y-4 text-sm">
            <p><span className="font-semibold">{booking.provider.display_name}</span> will be asked for <span className="font-semibold">{win.colonies} colonies</span> on {cycle?.crop.name} ({cycle?.field.name}) from {fmtShort(win.start)} to {fmtShort(win.end)}. Nothing is booked until they accept.</p>
            <Field label="Note for the provider" htmlFor="bn" optional><Textarea id="bn" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Access, water source, where hives can go" /></Field>
            <FormError error={m.error} />
          </div>
        )}
      </Dialog>
    </Panel>
  );
}

function BookingCard({ b }: { b: Booking }) {
  const toast = useToast();
  const [mode, setMode] = useState<null | "cancel" | "accept" | "dates">(null);
  const [dates, setDates] = useState({ start: b.start_date, end: b.end_date });
  const [open, setOpen] = useState(false);
  const { data: detail } = useApi<Booking>(open ? `/pollination/bookings/${b.id}` : null);
  const t = useMutation((body: Record<string, unknown>) => api(`/pollination/bookings/${b.id}/transition`, { body: { version: b.version, ...body } }));
  const done = (msg: string) => { setMode(null); toast(msg); invalidate("/pollination", "/dashboard"); };
  const canCancel = ["requested", "accepted", "reschedule_proposed"].includes(b.status);
  return (
    <li className="rounded-lg border border-line bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{b.cycle.crop} — {b.cycle.field}</span><StatusBadge status={b.status} /></div>
          <div className="mt-0.5 text-sm text-charcoal">{b.provider.display_name}, {b.colonies_requested} colonies, {fmtShort(b.start_date)} – {fmtShort(b.end_date)}</div>
          {b.status === "reschedule_proposed" && <div className="mt-1 text-sm font-semibold text-amber">Proposed: {fmtShort(b.proposed_start_date)} – {fmtShort(b.proposed_end_date)}</div>}
          {b.provider_note && <p className="mt-1 text-[13px] text-muted">Provider: “{b.provider_note}”</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {b.status === "reschedule_proposed" && <Button size="sm" onClick={() => setMode("accept")}>Accept new dates</Button>}
          {["requested", "accepted", "reschedule_proposed"].includes(b.status) && <Button size="sm" variant="secondary" onClick={() => { setDates({ start: b.start_date, end: b.end_date }); setMode("dates"); }}>Change dates</Button>}
          {canCancel && <Button size="sm" variant="quiet" onClick={() => setMode("cancel")}>Cancel</Button>}
          <Button size="sm" variant="quiet" onClick={() => setOpen((o) => !o)} aria-expanded={open}>History</Button>
        </div>
      </div>
      {open && detail?.events && (
        <ol className="mt-3 space-y-1 border-t border-line pt-3 text-xs text-muted">
          {detail.events.map((e, i) => <li key={i}>{fmtDateTime(e.at)} — {e.actor}: {e.from ? `${e.from.replace(/_/g, " ")} → ` : ""}{e.to.replace(/_/g, " ")}{e.note ? ` (“${e.note}”)` : ""}</li>)}
        </ol>
      )}
      <ConfirmDialog open={mode === "cancel"} onClose={() => setMode(null)} title="Cancel this booking?" confirmLabel="Cancel booking" tone="danger" pending={t.pending} error={t.error}
        onConfirm={async () => { if (await t.run({ to: "cancelled" })) done("Booking cancelled"); }}>
        <p>{b.provider.display_name} will be notified and the colonies released.</p>
      </ConfirmDialog>
      <ConfirmDialog open={mode === "accept"} onClose={() => setMode(null)} title="Accept the proposed dates?" confirmLabel="Accept dates" pending={t.pending} error={t.error}
        onConfirm={async () => { if (await t.run({ to: "accepted" })) done("Booking confirmed"); }}>
        <p>The booking will be confirmed for {fmtShort(b.proposed_start_date)} – {fmtShort(b.proposed_end_date)}.</p>
      </ConfirmDialog>
      <Dialog open={mode === "dates"} onClose={() => setMode(null)} title="Request different dates" footer={<><Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button><Button loading={t.pending} onClick={async () => { if (await t.run({ to: "requested", start_date: dates.start, end_date: dates.end })) done("New dates sent"); }}>Send new dates</Button></>}>
        <p className="mb-4 text-sm text-muted">{b.status === "accepted" ? "Your confirmed booking goes back to the provider for approval." : "The provider will see the updated request."}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="From" htmlFor={`ds${b.id}`}><Input id={`ds${b.id}`} type="date" min={todayISO()} value={dates.start} onChange={(e) => setDates({ ...dates, start: e.target.value })} /></Field>
          <Field label="Until" htmlFor={`de${b.id}`}><Input id={`de${b.id}`} type="date" min={dates.start} value={dates.end} onChange={(e) => setDates({ ...dates, end: e.target.value })} /></Field>
        </div>
        <div className="mt-4"><FormError error={t.error} /></div>
      </Dialog>
    </li>
  );
}

export default function Pollination() {
  const pre = useSearchParam("cycle");
  const { data, error, loading, reload } = useApi<Cal>("/pollination/calendar");
  const [show, setShow] = useState<"open" | "past">("open");
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const open = data.bookings.filter((b) => ["requested", "accepted", "reschedule_proposed"].includes(b.status));
  const past = data.bookings.filter((b) => !["requested", "accepted", "reschedule_proposed"].includes(b.status));
  const list = show === "open" ? open : past;
  return (
    <>
      <PageHeader title="Pollination" subtitle="Flowering windows, provider bookings and requests." />
      <div className="space-y-6">
        <Panel title="Flowering calendar" subtitle={`Next ${SPAN} days`}><FloweringCalendar cal={data} /></Panel>
        {data.cycles.length > 0 && <FindProviders cycles={data.cycles} bookings={data.bookings} initialCycle={pre} />}
        <Panel title="Your bookings" actions={
          <div role="tablist" className="flex rounded-full bg-cream p-0.5 text-[13px] font-semibold">
            {(["open", "past"] as const).map((k) => <button key={k} role="tab" aria-selected={show === k} onClick={() => setShow(k)} className={cn("rounded-full px-3 py-1", show === k ? "bg-paper shadow-soft" : "text-muted")}>{k === "open" ? `Open (${open.length})` : `Past (${past.length})`}</button>)}
          </div>
        }>
          {list.length ? <ul className="space-y-3">{list.map((b) => <BookingCard key={`${b.id}-${b.version}`} b={b} />)}</ul> : <EmptyState icon="CalendarDays" title={show === "open" ? "No open bookings" : "No past bookings"} />}
        </Panel>
      </div>
    </>
  );
}
