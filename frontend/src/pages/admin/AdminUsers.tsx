import { useState } from "react";
import { Button, ConfirmDialog, ErrorState, Input, Loading, PageHeader, Panel, Select, Table, Td, Th, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useApi, useMutation } from "../../lib/data";
import { roleName, timeAgo } from "../../lib/format";
import type { Me, Page, Role } from "../../lib/types";

type U = Me & { is_active: boolean; last_login_at: string | null; is_demo: boolean };
const ROLES: Role[] = ["farmer", "provider", "buyer", "reviewer", "admin"];

export default function AdminUsers() {
  const toast = useToast();
  const { user: me } = useAuth();
  const [role, setRole] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const qs = new URLSearchParams({ page_size: "100" });
  if (role) qs.set("role", role);
  if (query) qs.set("q", query);
  const { data, error, loading, reload } = useApi<Page<U>>(`/admin/users?${qs}`);
  const [pending, setPending] = useState<{ u: U; change: { role?: Role; is_active?: boolean } } | null>(null);
  const m = useMutation(() => api(`/admin/users/${pending!.u.id}`, { method: "PATCH", body: pending!.change }));
  return (
    <>
      <PageHeader title="Users & roles" subtitle="Role and access changes take effect immediately and are recorded in the audit log." />
      <Panel pad={false} actions={
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
          <Input aria-label="Search users" placeholder="Name or email" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 w-52 py-1" />
          <Select aria-label="Filter by role" value={role} onChange={(e) => setRole(e.target.value)} className="h-9 w-auto py-1"><option value="">All roles</option>{ROLES.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</Select>
          <Button size="sm" variant="secondary" type="submit" icon="Search">Search</Button>
        </form>
      } title="Accounts">
        {loading && !data ? <div className="p-5"><Loading /></div> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : (
          <Table>
            <thead><tr><Th>Person</Th><Th>Organisation</Th><Th>Role</Th><Th>Last sign-in</Th><Th>Access</Th></tr></thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id}>
                  <Td><div className="font-semibold">{u.full_name}</div><div className="text-xs text-muted">{u.email}</div></Td>
                  <Td>{u.organization_name ?? "—"}</Td>
                  <Td>
                    <Select aria-label={`Role for ${u.full_name}`} value={u.role} disabled={u.id === me?.id} onChange={(e) => { m.setError(null); setPending({ u, change: { role: e.target.value as Role } }); }} className="h-9 w-auto py-1">
                      {ROLES.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}
                    </Select>
                  </Td>
                  <Td className="text-muted">{u.last_login_at ? timeAgo(u.last_login_at) : "Never"}</Td>
                  <Td>{u.id === me?.id ? <span className="text-xs text-muted">You</span> : <Button size="sm" variant={u.is_active ? "quiet" : "secondary"} onClick={() => { m.setError(null); setPending({ u, change: { is_active: !u.is_active } }); }}>{u.is_active ? "Deactivate" : "Reactivate"}</Button>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      <ConfirmDialog open={!!pending} onClose={() => setPending(null)} title="Change access?" confirmLabel="Apply change" tone={pending?.change.is_active === false ? "danger" : "primary"} pending={m.pending} error={m.error}
        onConfirm={async () => { if (await m.run(undefined)) { setPending(null); toast("Access updated"); reload(); } }}>
        {pending && (pending.change.role
          ? <p>{pending.u.full_name} will become {/^[AEIOU]/.test(roleName(pending.change.role)) ? "an" : "a"} <span className="font-semibold">{roleName(pending.change.role).toLowerCase()}</span> and must sign in again.</p>
          : <p>{pending.u.full_name} will be {pending.change.is_active ? "able to sign in again" : "signed out and unable to sign in"}.</p>)}
      </ConfirmDialog>
    </>
  );
}
