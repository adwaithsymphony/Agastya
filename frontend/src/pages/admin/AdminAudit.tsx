import { useState } from "react";
import { Badge, Button, ErrorState, Loading, PageHeader, Panel, Select, Table, Td, Th } from "../../components/ui";
import { useApi } from "../../lib/data";
import { fmtDateTime, human } from "../../lib/format";
import type { Page } from "../../lib/types";

type Ev = { id: number; action: string; entity_type: string; entity_id: number | null; summary: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null; severity: string; actor: string; created_at: string };

const brief = (o: Record<string, unknown> | null) => (o ? Object.entries(o).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("; ") : "");

export default function AdminAudit() {
  const [severity, setSeverity] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ page: String(page), page_size: "30" });
  if (severity) qs.set("severity", severity);
  if (entity) qs.set("entity_type", entity);
  const { data, error, loading, reload } = useApi<Page<Ev>>(`/admin/audit?${qs}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <>
      <PageHeader title="Audit log" subtitle="Safety-related, access and assignment changes, newest first." />
      <Panel pad={false} title={data ? `${data.total} events` : "Events"} actions={
        <>
          <Select aria-label="Severity" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }} className="h-9 w-auto py-1"><option value="">All severities</option>{["info", "safety", "security", "warning"].map((s) => <option key={s} value={s}>{human(s)}</option>)}</Select>
          <Select aria-label="Record type" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }} className="h-9 w-auto py-1"><option value="">All records</option>{["pesticide_application", "product_label", "produce_batch", "pollination_booking", "crop_observation", "user", "crop_cycle"].map((s) => <option key={s} value={s}>{human(s)}</option>)}</Select>
        </>
      }>
        {loading && !data ? <div className="p-5"><Loading /></div> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : (
          <>
            <Table>
              <thead><tr><Th>When</Th><Th>Action</Th><Th>Record</Th><Th>By</Th><Th>Change</Th></tr></thead>
              <tbody>{data?.items.map((e) => (
                <tr key={e.id} className="align-top">
                  <Td className="text-xs whitespace-nowrap text-muted">{fmtDateTime(e.created_at)}</Td>
                  <Td><span className="font-medium">{e.action}</span> {e.severity !== "info" && <Badge tone={e.severity === "safety" ? "amber" : e.severity === "security" ? "water" : "danger"}>{e.severity}</Badge>}</Td>
                  <Td className="text-[13px] whitespace-nowrap">{human(e.entity_type)} #{e.entity_id}</Td>
                  <Td className="text-[13px]">{e.actor}</Td>
                  <Td className="max-w-md text-xs break-words text-muted">{e.before && <div>Before — {brief(e.before)}</div>}{e.after && <div>After — {brief(e.after)}</div>}{e.summary && <div>{e.summary}</div>}</Td>
                </tr>
              ))}</tbody>
            </Table>
            <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
              <span className="text-muted">Page {page} of {pages}</span>
              <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
            </div>
          </>
        )}
      </Panel>
    </>
  );
}
