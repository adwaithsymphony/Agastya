import { Badge, LinkButton, Metric, Panel, Table, Td, Th } from "../../components/ui";
import { human, roleName, timeAgo } from "../../lib/format";

type D = {
  metrics: Record<string, number>;
  users_by_role: Record<string, number>;
  model: { available: boolean; version: string | null; error: string | null; classes: number; metrics: Record<string, number> };
  audit: { id: number; action: string; entity_type: string; entity_id: number | null; actor: string; created_at: string; severity: string }[];
};

export default function AdminDashboard({ d }: { d: D }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric icon="Users" label="Active users" value={d.metrics.active_users} to="/app/admin/users" />
        <Metric icon="FlaskConical" tone={d.metrics.unverified_labels ? "amber" : "forest"} label="Labels awaiting verification" value={d.metrics.unverified_labels} to="/app/admin/reference" />
        <Metric icon="ScanLine" tone={d.model.available ? "forest" : "danger"} label="Crop-vision model" value={d.model.available ? "Online" : "Offline"} hint={d.model.available ? `v${d.model.version}, ${d.model.classes} classes` : d.model.error ?? undefined} to="/app/admin/models" />
        <Metric icon="CircleAlert" tone={d.metrics.failed_predictions ? "danger" : "forest"} label="Failed analyses" value={d.metrics.failed_predictions} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        <Panel title="Users by role">
          <ul className="space-y-2 text-sm">
            {Object.entries(d.users_by_role).map(([r, n]) => (
              <li key={r} className="flex justify-between"><span>{roleName(r)}</span><span className="num font-semibold">{n}</span></li>
            ))}
          </ul>
        </Panel>
        <Panel title="Recent operational activity" pad={false} actions={<LinkButton to="/app/admin/audit" variant="ghost" size="sm">Audit log</LinkButton>}>
          <Table>
            <thead><tr><Th>Action</Th><Th>Record</Th><Th>By</Th><Th>When</Th></tr></thead>
            <tbody>
              {d.audit.map((e) => (
                <tr key={e.id}>
                  <Td><span className="font-medium">{e.action}</span> {e.severity !== "info" && <Badge tone={e.severity === "safety" ? "amber" : "water"}>{e.severity}</Badge>}</Td>
                  <Td className="text-muted">{human(e.entity_type)} #{e.entity_id}</Td>
                  <Td>{e.actor}</Td>
                  <Td className="text-muted">{timeAgo(e.created_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      </div>
    </div>
  );
}
