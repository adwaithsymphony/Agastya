const dFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const dShort = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
const dtFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const nFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });

function parseDate(v: string): Date {
  // Plain dates ("2026-10-16") are calendar dates; render them without a timezone shift.
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(`${v}T00:00:00`) : new Date(v);
}

export const fmtDate = (v?: string | null) => (v ? dFmt.format(parseDate(v)) : "—");
export const fmtShort = (v?: string | null) => (v ? dShort.format(parseDate(v)) : "—");
export const fmtDateTime = (v?: string | null) => (v ? dtFmt.format(parseDate(v)) : "—");
export const fmtNum = (v?: number | null) => (v === null || v === undefined ? "—" : nFmt.format(v));
export const fmtKg = (v?: number | null) => (v === null || v === undefined ? "—" : `${nFmt.format(v)} kg`);
export const pct = (v?: number | null) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function addDays(iso: string, n: number): string {
  const d = parseDate(iso);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function daysBetween(a: string, b: string): number {
  return Math.round((parseDate(b).getTime() - parseDate(a).getTime()) / 86400000);
}

export function relDays(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  if (n === 0) return "today";
  if (n === 1) return "tomorrow";
  if (n === -1) return "yesterday";
  return n > 0 ? `in ${n} days` : `${-n} days ago`;
}

export function timeAgo(v: string): string {
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return fmtShort(v);
}

export const human = (s?: string | null) => (s ? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "—");

/** "Tomato___Early_blight" → "Early blight" */
export function conditionLabel(cond?: string | null): string {
  if (!cond) return "—";
  const c = cond.replace(/_/g, " ").trim();
  return c.charAt(0).toUpperCase() + c.slice(1).toLowerCase().replace(/\s+/g, " ");
}

/** Local datetime-input value → ISO string with the browser's offset. */
export function localInputToISO(v: string): string {
  const d = new Date(v);
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, "0");
  const mm = String(Math.abs(off) % 60).padStart(2, "0");
  return `${v.length === 16 ? v + ":00" : v}${sign}${hh}:${mm}`;
}
export function nowLocalInput(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

const ROLE_NAMES: Record<string, string> = {
  farmer: "Farmer",
  provider: "Pollination provider",
  buyer: "Buyer",
  reviewer: "Agronomist",
  admin: "Administrator",
};
export const roleName = (r?: string | null) => (r ? ROLE_NAMES[r] ?? human(r) : "—");

/** Hide the development-only naming prefix in the interface; provenance warnings remain visible for fictional pesticide records. */
export function productDisplayName(name: string): string {
  return name.replace(/^Demo\s+/i, "");
}
