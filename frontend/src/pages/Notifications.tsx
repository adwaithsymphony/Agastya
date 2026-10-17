import { useState } from "react";
import { Button, EmptyState, ErrorState, Loading, PageHeader, Panel, cn } from "../components/ui";
import { api } from "../lib/api";
import { invalidate, useApi } from "../lib/data";
import { fmtDateTime } from "../lib/format";
import { useNavigate } from "../lib/router";
import type { Notification, Page } from "../lib/types";

export default function Notifications() {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(false);
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi<Page<Notification>>(`/notifications?page=${page}&page_size=20${unread ? "&unread=true" : ""}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const open = async (n: Notification) => {
    if (!n.read_at) await api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => undefined);
    invalidate("/notifications");
    if (n.link) navigate(n.link);
  };
  return (
    <>
      <PageHeader title="Notifications" actions={
        <>
          <Button variant="secondary" size="sm" onClick={() => { setUnread(!unread); setPage(1); }}>{unread ? "Show all" : "Unread only"}</Button>
          <Button variant="ghost" size="sm" disabled={!data?.unread_count} onClick={async () => { await api("/notifications/read-all", { method: "POST" }); invalidate("/notifications"); }}>Mark all read</Button>
        </>
      } />
      <Panel pad={false}>
        {loading && !data ? <div className="p-5"><Loading /></div> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : !data?.items.length ? (
          <EmptyState icon="Bell" title={unread ? "No unread notifications" : "No notifications yet"} />
        ) : (
          <ul className="divide-y divide-line/70">
            {data.items.map((n) => (
              <li key={n.id}>
                <button onClick={() => open(n)} className="flex w-full gap-3 px-5 py-4 text-left hover:bg-cream/60">
                  <span className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", n.read_at ? "bg-line" : n.severity === "warning" ? "bg-amber" : "bg-forest")} aria-label={n.read_at ? "Read" : "Unread"} />
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-sm", n.read_at ? "font-medium" : "font-bold")}>{n.title}</span>
                    {n.body && <span className="block text-[13px] text-muted">{n.body}</span>}
                  </span>
                  <span className="text-xs whitespace-nowrap text-muted">{fmtDateTime(n.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {pages > 1 && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
            <span className="text-muted">Page {page} of {pages}</span>
            <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
          </div>
        )}
      </Panel>
    </>
  );
}
