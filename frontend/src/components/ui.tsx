import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import type { ApiError } from "../lib/api";
import { Link } from "../lib/router";
import { Icon, type IconName } from "./icons";

export const cn = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// ------------------------------------------------------------------ buttons
type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "quiet";
const btnBase =
  "inline-flex items-center justify-center gap-2 font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap";
const btnVariants: Record<BtnVariant, string> = {
  primary: "bg-forest text-white hover:bg-forest-deep shadow-lift rounded-full",
  secondary: "bg-paper text-forest border border-line-strong hover:border-forest hover:bg-white rounded-full",
  ghost: "text-forest hover:bg-sage-pale rounded-full",
  danger: "bg-danger text-white hover:bg-[#8a3423] rounded-full",
  quiet: "text-muted hover:text-charcoal rounded-md",
};
const btnSizes = { sm: "h-8 px-3.5 text-[13px]", md: "h-10 px-5 text-sm", lg: "h-12 px-7 text-[15px]" };

export function Button({
  variant = "primary",
  size = "md",
  icon,
  loading,
  className,
  children,
  ...rest
}: { variant?: BtnVariant; size?: keyof typeof btnSizes; icon?: IconName; loading?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(btnBase, btnVariants[variant], btnSizes[size], className)}
      disabled={loading || rest.disabled}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Icon name="LoaderCircle" size={16} className="animate-spin" /> : icon ? <Icon name={icon} size={16} /> : null}
      {children}
    </button>
  );
}

export function LinkButton({ to, variant = "secondary", size = "md", icon, children, className }: {
  to: string; variant?: BtnVariant; size?: keyof typeof btnSizes; icon?: IconName; children: ReactNode; className?: string;
}) {
  return (
    <Link to={to} className={cn(btnBase, btnVariants[variant], btnSizes[size], className)}>
      {icon && <Icon name={icon} size={16} />}
      {children}
    </Link>
  );
}

// ------------------------------------------------------------------ badges
export type Tone = "neutral" | "forest" | "sage" | "amber" | "danger" | "water" | "earth";
const toneCls: Record<Tone, string> = {
  neutral: "bg-[#efebe1] text-charcoal",
  forest: "bg-forest text-white",
  sage: "bg-sage-pale text-forest",
  amber: "bg-amber-soft text-amber",
  danger: "bg-danger-soft text-danger",
  water: "bg-water-soft text-water",
  earth: "bg-beige text-earth",
};

export function Badge({ tone = "neutral", children, icon, className }: { tone?: Tone; children: ReactNode; icon?: IconName; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap", toneCls[tone], className)}>
      {icon && <Icon name={icon} size={12} strokeWidth={2} />}
      {children}
    </span>
  );
}

const STATUS: Record<string, [string, Tone, IconName?]> = {
  // harvest
  restricted: ["Restricted", "danger", "Lock"],
  upcoming: ["Eligible soon", "amber", "Timer"],
  eligible: ["Eligible under recorded PHI", "sage"],
  unknown: ["Needs verification", "amber", "CircleHelp"],
  // predictions
  completed: ["Analysed", "sage"],
  uncertain: ["Uncertain", "amber", "CircleHelp"],
  unsupported_input: ["Unsupported input", "earth"],
  failed: ["Analysis unavailable", "danger"],
  pending: ["Pending", "neutral"],
  awaiting_review: ["Awaiting review", "water"],
  reviewed: ["Reviewed", "forest"],
  not_required: ["No review needed", "neutral"],
  // bookings
  requested: ["Requested", "water"],
  accepted: ["Accepted", "forest"],
  reschedule_proposed: ["New dates proposed", "amber"],
  rejected: ["Declined", "danger"],
  cancelled: ["Cancelled", "neutral"],
  // batches / shipments
  unassigned: ["No buyer yet", "amber"],
  assigned: ["Buyer assigned", "sage"],
  needs_destination: ["Needs destination", "danger", "TriangleAlert"],
  in_transit: ["In transit", "water", "Truck"],
  delivered: ["Delivered", "forest"],
  closed: ["Closed", "neutral"],
  scheduled: ["Scheduled", "sage"],
  dispatched: ["Dispatched", "water"],
  active: ["Active", "sage"],
  harvesting: ["Harvesting", "earth"],
  planned: ["Planned", "neutral"],
  superseded: ["Replaced", "neutral"],
  cancelled_by_buyer: ["Cancelled by buyer", "danger"],
  withdrawn: ["Withdrawn", "neutral"],
  verified: ["Verified", "forest"],
  unverified: ["Unverified", "amber"],
  open: ["Open", "sage"],
  paused: ["Paused", "neutral"],
  voided: ["Voided", "neutral"],
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const [text, tone, icon] = STATUS[status] ?? [status.replace(/_/g, " "), "neutral"];
  return <Badge tone={tone} icon={icon}>{label ?? text}</Badge>;
}

// ------------------------------------------------------------------ layout
export function Panel({ title, actions, children, className, pad = true, id, subtitle }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean; id?: string;
}) {
  return (
    <section id={id} className={cn("rounded-lg border border-line bg-paper", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            {title && <h2 className="text-[15px] font-bold text-charcoal">{title}</h2>}
            {subtitle && <p className="text-[13px] text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: { to: string; label: string } }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {back && (
          <Link to={back.to} className="mb-2 inline-flex items-center gap-1 text-[13px] font-semibold text-muted hover:text-forest">
            <Icon name="ArrowLeft" size={14} /> {back.label}
          </Link>
        )}
        <h1 className="text-title font-bold text-forest-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Metric({ label, value, hint, icon, tone = "forest", to }: {
  label: string; value: ReactNode; hint?: ReactNode; icon?: IconName; tone?: "forest" | "danger" | "amber" | "water" | "earth"; to?: string;
}) {
  const ring = { forest: "text-forest bg-sage-pale", danger: "text-danger bg-danger-soft", amber: "text-amber bg-amber-soft", water: "text-water bg-water-soft", earth: "text-earth bg-beige" }[tone];
  const body = (
    <div className="flex h-full items-start gap-3.5 rounded-lg border border-line bg-paper p-4 transition-colors hover:border-line-strong">
      {icon && (
        <span className={cn("grid size-9 shrink-0 place-items-center rounded-full", ring)}>
          <Icon name={icon} size={17} />
        </span>
      )}
      <div className="min-w-0">
        <div className="num text-[26px] leading-none font-bold tracking-tight text-forest-ink">{value}</div>
        <div className="mt-1.5 text-[13px] font-semibold text-charcoal">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
      </div>
    </div>
  );
  return to ? <Link to={to} className="block">{body}</Link> : body;
}

// ------------------------------------------------------------------ forms
export function Field({ label, hint, error, children, htmlFor, optional }: { label: string; hint?: ReactNode; error?: string; children: ReactNode; htmlFor?: string; optional?: boolean }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-[13px] font-semibold text-charcoal">
        {label} {optional && <span className="font-normal text-muted">(optional)</span>}
      </label>
      {children}
      {error ? <p className="text-xs font-medium text-danger" role="alert">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-line-strong bg-white px-3 py-2 text-sm text-charcoal placeholder:text-[#a3a69e] focus:border-forest focus:outline-none focus:ring-2 focus:ring-sage-pale disabled:bg-cream";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(inputCls, props.className)} />;
}
export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cn(inputCls, "appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%23727970%22 stroke-width=%222%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[right_0.75rem_center] bg-no-repeat pr-9", props.className)}>
      {children}
    </select>
  );
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={cn(inputCls, props.className)} />;
}

export function FormError({ error }: { error?: ApiError | null }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">
      <Icon name="CircleAlert" size={16} className="mt-0.5 shrink-0" />
      <span>{error.message}</span>
    </div>
  );
}

// ------------------------------------------------------------------ states
export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} className="space-y-3 p-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-11 animate-pulse rounded-md bg-[#ece6d8]" style={{ opacity: 1 - i * 0.2 }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-danger/20 bg-danger-soft/60 p-5">
      <div className="flex items-center gap-2 font-semibold text-danger">
        <Icon name="CircleAlert" size={18} /> Couldn't load this
      </div>
      <p className="text-sm text-charcoal">{error.message}</p>
      {onRetry && <Button variant="secondary" size="sm" icon="RefreshCw" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function EmptyState({ icon = "Sprout", title, body, action }: { icon?: IconName; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <span className="mb-3 grid size-12 place-items-center rounded-full bg-sage-pale text-forest">
        <Icon name={icon} size={22} />
      </span>
      <p className="font-semibold text-charcoal">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Help({ children, label = "More information" }: { children: ReactNode; label?: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex align-middle">
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        className="text-muted hover:text-forest"
      >
        <Icon name="CircleHelp" size={14} />
      </button>
      {open && (
        <span id={id} role="tooltip" className="absolute bottom-full left-1/2 z-40 mb-2 w-64 -translate-x-1/2 rounded-md bg-forest-ink px-3 py-2 text-xs leading-relaxed font-medium text-white shadow-lift">
          {children}
        </span>
      )}
    </span>
  );
}

// ------------------------------------------------------------------ table
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full min-w-[640px] text-left text-sm">{children}</table>
    </div>
  );
}
export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th className={cn("border-b border-line px-4 py-2.5 text-xs font-semibold text-muted", className)}>{children}</th>;
}
export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cn("border-b border-line/70 px-4 py-3 align-middle", className)}>{children}</td>;
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[] }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "-mb-px flex items-center gap-2 border-b-2 px-3.5 py-2.5 text-sm font-semibold whitespace-nowrap",
            value === it.value ? "border-forest text-forest" : "border-transparent text-muted hover:text-charcoal",
          )}
        >
          {it.label}
          {it.count !== undefined && <span className="num rounded-full bg-[#ece6d8] px-1.5 text-[11px] text-charcoal">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ dialog
export function Dialog({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>("input,select,textarea,button:not([data-close])");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && node) {
        const f = [...node.querySelectorAll<HTMLElement>("a,button,input,select,textarea,[tabindex]:not([tabindex='-1'])")].filter((x) => !x.hasAttribute("disabled"));
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-forest-ink/40 p-0 sm:items-center sm:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className={cn("toast-in flex max-h-[92vh] w-full flex-col rounded-t-xl bg-paper shadow-lift sm:rounded-xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-base font-bold text-forest-ink">{title}</h2>
          <button data-close aria-label="Close" onClick={onClose} className="rounded-md p-1 text-muted hover:bg-cream hover:text-charcoal">
            <Icon name="X" size={18} />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, onClose, onConfirm, title, children, confirmLabel, tone = "primary", pending, error }: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: string; children: ReactNode; confirmLabel: string;
  tone?: "primary" | "danger"; pending?: boolean; error?: ApiError | null;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Keep as is</Button>
          <Button variant={tone} loading={pending} onClick={onConfirm}>{confirmLabel}</Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        {children}
        <FormError error={error} />
      </div>
    </Dialog>
  );
}

// ------------------------------------------------------------------ toasts
type Toast = { id: number; text: string; tone: "ok" | "error" };
const ToastCtx = createContext<(text: string, tone?: "ok" | "error") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 left-4 z-[60] flex flex-col items-end gap-2 sm:left-auto">
        {toasts.map((t) => (
          <div key={t.id} className={cn("toast-in pointer-events-auto flex max-w-sm items-center gap-2.5 rounded-lg px-4 py-3 text-sm font-semibold shadow-lift", t.tone === "ok" ? "bg-forest-ink text-white" : "bg-danger text-white")}>
            <Icon name={t.tone === "ok" ? "Check" : "CircleAlert"} size={16} />
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/** One consistent marker for where pesticide label data came from. */
export function ProvenanceBadge({ provenance }: { provenance?: string | null }) {
  if (provenance === "fictional_sample")
    return <Badge tone="earth" icon="TriangleAlert" className="align-middle">Fictional sample, not for field use</Badge>;
  if (provenance === "submitted") return <Badge tone="amber" icon="CircleHelp" className="align-middle">Submitted, unverified</Badge>;
  return null;
}

export function DataList({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,auto)_1fr] gap-x-4 gap-y-2 text-sm">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="font-medium text-charcoal">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
