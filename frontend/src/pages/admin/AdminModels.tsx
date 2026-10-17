import { Badge, DataList, ErrorState, Loading, PageHeader, Panel, Table, Td, Th } from "../../components/ui";
import { useApi } from "../../lib/data";
import { fmtDateTime, human, pct } from "../../lib/format";

type Card = {
  key: string; version: string; name: string; task: string; artifact_sha256: string; classes: string[];
  backbone: { architecture: string; weights: string; license: string };
  training_data: { dataset: string; license: string; citation: string; images_used: number; split: Record<string, number>; split_method: string };
  metrics: Record<string, number | null | Record<string, { precision: number; recall: number; support: number }>>;
  limitations: string[]; evaluated_on: string;
};
type Resp = {
  runtime: { available: boolean; version: string | null; error: string | null; classes: number };
  card: Card | null;
  registry: { id: number; key: string; version: string; name: string; status: string; license: string; class_count: number; registered_at: string; artifact_sha256: string }[];
  prediction_counts: Record<string, number>;
};

export default function AdminModels() {
  const { data, error, loading, reload } = useApi<Resp>("/admin/models");
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const c = data.card;
  const m = (c?.metrics ?? {}) as Record<string, number | null>;
  const per = (c?.metrics?.per_class ?? {}) as Record<string, { precision: number; recall: number; support: number }>;
  return (
    <>
      <PageHeader title="Models" subtitle="Crop-vision model status, evaluation and limits." />
      <div className="space-y-6">
        <Panel title="Runtime" actions={data.runtime.available ? <Badge tone="sage">Loaded</Badge> : <Badge tone="danger">Unavailable</Badge>}>
          {data.runtime.available && c ? (
            <DataList items={[
              ["Model", `${c.name}`],
              ["Version", `${c.key} v${c.version}`],
              ["Task", c.task],
              ["Backbone", `${c.backbone.architecture} — ${c.backbone.weights} (${c.backbone.license})`],
              ["Training data", `${c.training_data.dataset}, ${c.training_data.images_used.toLocaleString()} images (${c.training_data.license})`],
              ["Split", `${c.training_data.split.train} / ${c.training_data.split.validation} / ${c.training_data.split.test} — ${c.training_data.split_method}`],
              ["Artifact SHA-256", <code key="sha" className="text-xs break-all">{c.artifact_sha256}</code>],
              ["Evaluated", c.evaluated_on],
            ]} />
          ) : <p className="text-sm text-danger">The model is not loaded ({data.runtime.error ?? "unknown reason"}). Observations are saved with a "failed" result and can be re-analysed once it is installed.</p>}
        </Panel>
        {c && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Held-out evaluation (PlantVillage test split)">
              <DataList items={[
                ["Test accuracy", pct(m.test_accuracy)],
                ["Macro F1", pct(m.test_macro_f1)],
                ["Calibration error (ECE)", m.test_ece_15_bins?.toFixed(3) ?? "—"],
                ["Uncertainty threshold", pct(m.uncertainty_threshold)],
                ["Coverage at threshold", pct(m.test_coverage_at_threshold)],
                ["Accuracy above threshold", pct(m.test_accuracy_at_or_above_threshold)],
                ["Accuracy below threshold", pct(m.test_accuracy_below_threshold)],
                ["Out-of-distribution guard", `cosine ≥ ${m.ood_guard_cosine_threshold}; passes ${pct(m.ood_guard_test_pass_rate)} of test leaves`],
              ]} />
            </Panel>
            <Panel title="Known limitations">
              <ul className="list-disc space-y-2 pl-5 text-sm">{c.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            </Panel>
          </div>
        )}
        <Panel title="Predictions recorded">
          <div className="flex flex-wrap gap-6">
            {Object.entries(data.prediction_counts).map(([k, v]) => <div key={k}><div className="num text-2xl font-bold">{v}</div><div className="text-xs text-muted">{human(k)}</div></div>)}
          </div>
        </Panel>
        {c && (
          <Panel title="Per-class results" pad={false}>
            <Table>
              <thead><tr><Th>Class</Th><Th>Precision</Th><Th>Recall</Th><Th>Test images</Th></tr></thead>
              <tbody>{Object.entries(per).map(([k, v]) => (
                <tr key={k}><Td className="text-[13px]">{k.replace("___", " — ").replace(/_/g, " ")}</Td><Td className="num">{pct(v.precision)}</Td><Td className="num">{pct(v.recall)}</Td><Td className="num">{v.support}</Td></tr>
              ))}</tbody>
            </Table>
          </Panel>
        )}
        <Panel title="Registry" pad={false}>
          <Table>
            <thead><tr><Th>Key</Th><Th>Version</Th><Th>Classes</Th><Th>License</Th><Th>Registered</Th></tr></thead>
            <tbody>{data.registry.map((r) => <tr key={r.id}><Td>{r.key}</Td><Td>{r.version}</Td><Td className="num">{r.class_count}</Td><Td className="text-xs">{r.license}</Td><Td>{fmtDateTime(r.registered_at)}</Td></tr>)}</tbody>
          </Table>
        </Panel>
      </div>
    </>
  );
}
