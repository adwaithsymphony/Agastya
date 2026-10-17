import { useEffect, useRef, useState } from "react";
import { PredictionPanel } from "../components/domain";
import { Icon } from "../components/icons";
import { Button, EmptyState, ErrorState, Field, FormError, LinkButton, Loading, PageHeader, Panel, Select, StatusBadge, Textarea, cn, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { invalidate, useApi } from "../lib/data";
import { conditionLabel, fmtDateTime, human, pct } from "../lib/format";
import { Link, useSearchParam } from "../lib/router";
import type { Crop, CycleBrief, Observation, Page } from "../lib/types";

const MAX_MB = 8;
const TYPES = ["image/jpeg", "image/png", "image/webp"];

function Uploader() {
  const toast = useToast();
  const pre = useSearchParam("cycle");
  const { data: cycles } = useApi<CycleBrief[]>("/crop-cycles?status=open");
  const { data: crops } = useApi<Crop[]>("/crops");
  const [cycle, setCycle] = useState(pre ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<Observation | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!cycle && cycles?.length) setCycle(String(cycles[0].id));
  }, [cycles, cycle]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const pick = (f: File | undefined) => {
    setResult(null);
    setError(null);
    if (!f) return;
    if (!TYPES.includes(f.type)) return setLocalErr("Choose a JPEG, PNG or WebP photo.");
    if (f.size > MAX_MB * 1024 * 1024) return setLocalErr(`The photo is larger than ${MAX_MB} MB.`);
    setLocalErr(null);
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const submit = async () => {
    if (!file || !cycle) return;
    setPending(true);
    setError(null);
    const form = new FormData();
    form.append("crop_cycle_id", cycle);
    if (notes) form.append("notes", notes);
    form.append("image", file);
    try {
      const r = await api<Observation>("/observations", { form });
      setResult(r);
      toast("Observation saved");
      invalidate("/observations", "/dashboard", "/crop-cycles");
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setPending(false);
    }
  };

  const selected = cycles?.find((c) => String(c.id) === cycle);
  const selectedCrop = crops?.find((c) => c.id === selected?.crop.id);
  return (
    <Panel title="New observation" subtitle="Photograph one leaf, in daylight, against a plain background.">
      <div className="grid gap-6 md:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          <Field label="Crop cycle" htmlFor="ocycle">
            <Select id="ocycle" value={cycle} onChange={(e) => { setCycle(e.target.value); setResult(null); }}>
              {!cycles?.length && <option value="">No active crop cycles</option>}
              {cycles?.map((c) => <option key={c.id} value={c.id}>{c.crop.name} — {c.field.name}, {c.farm.name}</option>)}
            </Select>
          </Field>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
            className={cn("relative flex min-h-56 flex-col items-center justify-center overflow-hidden rounded-lg border-2 border-dashed text-center transition-colors", drag ? "border-forest bg-sage-pale" : "border-line-strong bg-white")}
          >
            {preview ? (
              <>
                <img src={preview} alt="Selected leaf" className="absolute inset-0 size-full object-contain p-2" />
                <button onClick={() => input.current?.click()} className="absolute right-2 bottom-2 rounded-full bg-paper/95 px-3 py-1.5 text-xs font-semibold shadow-soft">Change photo</button>
              </>
            ) : (
              <button onClick={() => input.current?.click()} className="flex flex-col items-center gap-2 p-6">
                <span className="grid size-12 place-items-center rounded-full bg-sage-pale text-forest"><Icon name="ImageUp" size={22} /></span>
                <span className="text-sm font-semibold">Choose a photo or drop it here</span>
                <span className="text-xs text-muted">JPEG, PNG or WebP, up to {MAX_MB} MB</span>
              </button>
            )}
            <input ref={input} type="file" accept={TYPES.join(",")} capture="environment" className="sr-only" aria-label="Leaf photo" onChange={(e) => pick(e.target.files?.[0])} />
          </div>
          {localErr && <p role="alert" className="text-sm font-medium text-danger">{localErr}</p>}
          <Field label="Notes" htmlFor="onotes" optional><Textarea id="onotes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Where in the field, what you noticed" /></Field>
          <FormError error={error} />
          <Button icon="ScanLine" loading={pending} disabled={!file || !cycle} onClick={submit}>{pending ? "Analysing" : "Save and analyse"}</Button>
        </div>
        <div className="rounded-lg bg-cream/70 p-5">
          {result ? (
            <div className="space-y-4">
              <PredictionPanel p={result.prediction} />
              <LinkButton to={`/app/observations/${result.id}`} size="sm">Open observation</LinkButton>
            </div>
          ) : (
            <div className="flex h-full flex-col justify-center text-sm text-muted">
              <p className="font-semibold text-charcoal">The model's reading appears here.</p>
              <p className="mt-1">
                {selectedCrop && !selectedCrop.vision_supported
                  ? `${selectedCrop.name} isn't covered by the model, so no reading will be shown. The photo is saved for an agronomist to review.`
                  : "It recognises 38 leaf conditions across 14 crops. Anything unclear goes to an agronomist for review; nothing here is a diagnosis."}
              </p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

export default function Observations() {
  const { user } = useAuth();
  const cycleFilter = useSearchParam("cycle");
  const [status, setStatus] = useState("");
  const [review, setReview] = useState("");
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ page: String(page), page_size: "12" });
  if (status) qs.set("status", status);
  if (review) qs.set("review_status", review);
  if (cycleFilter) qs.set("crop_cycle_id", cycleFilter);
  const { data, error, loading, reload } = useApi<Page<Observation>>(`/observations?${qs}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <>
      <PageHeader title={user?.role === "farmer" ? "Crop health" : "Observations"} subtitle="Leaf photos, the model's reading, and agronomist reviews." />
      <div className="space-y-6">
        {user?.role === "farmer" && <Uploader />}
        <Panel
          title="Observation history"
          pad={false}
          actions={
            <>
              <Select aria-label="Filter by result" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-9 w-auto py-1">
                <option value="">All results</option>
                {["completed", "uncertain", "unsupported_input", "failed"].map((s) => <option key={s} value={s}>{human(s)}</option>)}
              </Select>
              <Select aria-label="Filter by review" value={review} onChange={(e) => { setReview(e.target.value); setPage(1); }} className="h-9 w-auto py-1">
                <option value="">Any review state</option>
                {["awaiting_review", "reviewed", "not_required"].map((s) => <option key={s} value={s}>{human(s)}</option>)}
              </Select>
            </>
          }
        >
          {loading && !data ? <div className="p-5"><Loading /></div> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : !data?.items.length ? (
            <EmptyState icon="Camera" title="No observations match" body={status || review ? "Try clearing the filters." : "Upload a leaf photo to start a crop-health record."} />
          ) : (
            <>
              <ul className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-3">
                {data.items.map((o) => (
                  <li key={o.id} className="bg-paper">
                    <Link to={`/app/observations/${o.id}`} className="flex gap-3 p-4 hover:bg-cream/60">
                      <img src={`/api/v1/observations/${o.id}/image`} alt="" className="size-20 shrink-0 rounded-md object-cover" loading="lazy" />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold">{o.cycle.crop}, {o.cycle.field}</div>
                        <div className="text-xs text-muted">{fmtDateTime(o.observed_at)}</div>
                        <div className="mt-1 truncate text-[13px]">
                          {o.prediction?.predicted_condition && (o.status === "completed" || o.status === "uncertain") ? `${conditionLabel(o.prediction.predicted_condition)} — ${pct(o.prediction.confidence)}` : human(o.status)}
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1"><StatusBadge status={o.status} />{o.review_status !== "not_required" && <StatusBadge status={o.review_status} />}</div>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              {pages > 1 && (
                <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
                  <span className="text-muted">Page {page} of {pages}</span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                    <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
