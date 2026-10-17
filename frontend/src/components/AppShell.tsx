import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { invalidate, useApi } from "../lib/data";
import { timeAgo } from "../lib/format";
import { Link, useLocation, useNavigate } from "../lib/router";
import type { Notification, Page, Role } from "../lib/types";
import { Icon, type IconName } from "./icons";
import { Logo } from "./Logo";
import { cn } from "./ui";
import { LanguageSelect, useI18n } from "../lib/i18n";

type NavItem = { to: string; label: string; icon: IconName };

export const NAV: Record<Role, NavItem[]> = {
  farmer: [
    { to: "/app", label: "Overview", icon: "LayoutDashboard" },
    { to: "/app/farms", label: "Farms & fields", icon: "Map" },
    { to: "/app/observations", label: "Crop health", icon: "ScanLine" },
    { to: "/app/harvest", label: "Harvest safety", icon: "FlaskConical" },
    { to: "/app/pollination", label: "Pollination", icon: "Flower2" },
    { to: "/app/batches", label: "Produce & buyers", icon: "Package" },
  ],
  provider: [
    { to: "/app", label: "Overview", icon: "LayoutDashboard" },
    { to: "/app/provider/bookings", label: "Bookings", icon: "CalendarDays" },
    { to: "/app/provider/profile", label: "Services & availability", icon: "Hexagon" },
  ],
  buyer: [
    { to: "/app", label: "Overview", icon: "LayoutDashboard" },
    { to: "/app/buyer/demands", label: "Demand listings", icon: "Store" },
    { to: "/app/buyer/deliveries", label: "Deliveries", icon: "Truck" },
  ],
  reviewer: [
    { to: "/app", label: "Overview", icon: "LayoutDashboard" },
    { to: "/app/review", label: "Review queue", icon: "ClipboardCheck" },
    { to: "/app/observations", label: "All observations", icon: "ScanLine" },
  ],
  admin: [
    { to: "/app", label: "Overview", icon: "LayoutDashboard" },
    { to: "/app/admin/users", label: "Users & roles", icon: "Users" },
    { to: "/app/admin/reference", label: "Reference data", icon: "Database" },
    { to: "/app/admin/models", label: "Models", icon: "ScanLine" },
    { to: "/app/admin/audit", label: "Audit log", icon: "FileClock" },
  ],
};

const ROLE_LABEL: Record<Role, string> = {
  farmer: "Farmer",
  provider: "Pollination provider",
  buyer: "Buyer",
  reviewer: "Agronomist",
  admin: "Administrator",
};

const NAV_TRANSLATION_KEY: Record<string, string> = {
  "Overview": "nav.overview", "Farms & fields": "nav.farms", "Crop health": "nav.health",
  "Harvest safety": "nav.harvest", "Pollination": "nav.pollination", "Produce & buyers": "nav.produce",
  "Bookings": "nav.bookings", "Services & availability": "nav.services", "Demand listings": "nav.demands",
  "Deliveries": "nav.deliveries", "Review queue": "nav.review", "All observations": "nav.health",
  "Users & roles": "nav.users", "Reference data": "nav.reference", "Models": "nav.models", "Audit log": "nav.audit",
};

function isActive(pathname: string, to: string) {
  return to === "/app" ? pathname === "/app" : pathname === to || pathname.startsWith(to + "/");
}

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = useI18n();
  if (!user) return null;
  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <div className="px-5 pt-6 pb-7">
        <Link to="/app" onClick={onNavigate} aria-label="AGASTYA overview">
          <Logo tone="light" />
        </Link>
      </div>
      <ul className="flex-1 space-y-0.5 px-3">
        {NAV[user.role].map((n) => {
          const active = isActive(pathname, n.to);
          return (
            <li key={n.to}>
              <Link
                to={n.to}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2.5 text-[14px] font-semibold transition-colors",
                  active ? "bg-cream text-forest-deep" : "text-white/75 hover:bg-white/8 hover:text-white",
                )}
              >
                <Icon name={n.icon} size={18} />
                {t(NAV_TRANSLATION_KEY[n.label] ?? n.label)}
              </Link>
            </li>
          );
        })}
        {user.role === "farmer" && <li>
          <a href={(import.meta.env.VITE_PLANT_INTELLIGENCE_URL || "http://localhost:5174").replace(/\/$/, "")}
             target="_blank" rel="noopener noreferrer"
             className="flex items-center gap-3 rounded-md px-3 py-2.5 text-[14px] font-semibold text-white/75 transition-colors hover:bg-white/8 hover:text-white">
            <Icon name="Sprout" size={18} /> {t("nav.plant")}
          </a>
        </li>}
      </ul>
      <div className="m-3 rounded-lg border border-white/12 p-3.5 text-white/80">
        <div className="text-[13px] font-semibold text-white">{user.full_name}</div>
        <div className="text-xs">{ROLE_LABEL[user.role]}</div>
        {user.organization_name && <div className="mt-0.5 truncate text-xs text-white/60">{user.organization_name}</div>}
      </div>
    </nav>
  );
}

function NotificationsMenu() {
  const { t } = useI18n();
  const { data, reload } = useApi<Page<Notification>>("/notifications?page_size=8");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const t = setInterval(reload, 60000);
    return () => clearInterval(t);
  }, [reload]);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const unread = data?.unread_count ?? 0;
  const openItem = async (n: Notification) => {
    if (!n.read_at) await api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => undefined);
    invalidate("/notifications");
    setOpen(false);
    if (n.link) navigate(n.link);
  };
  return (
    <div ref={ref} className="relative">
      <button
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="relative grid size-10 place-items-center rounded-full text-charcoal hover:bg-sage-pale"
      >
        <Icon name="Bell" size={19} />
        {unread > 0 && <span className="num absolute top-1.5 right-1.5 min-w-4 rounded-full bg-danger px-1 text-center text-[10px] leading-4 font-bold text-white">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(380px,calc(100vw-24px))] overflow-hidden rounded-lg border border-line bg-paper shadow-lift">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-sm font-bold">{t("notifications.title")}</span>
            {unread > 0 && (
              <button className="text-xs font-semibold text-forest hover:underline" onClick={async () => { await api("/notifications/read-all", { method: "POST" }); invalidate("/notifications"); }}>
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {data?.items.length ? (
              data.items.map((n) => (
                <li key={n.id}>
                  <button onClick={() => openItem(n)} className="flex w-full gap-3 border-b border-line/60 px-4 py-3 text-left hover:bg-cream">
                    <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : n.severity === "warning" ? "bg-amber" : "bg-forest")} />
                    <span className="min-w-0">
                      <span className="block text-[13px] font-semibold text-charcoal">{n.title}</span>
                      {n.body && <span className="block text-xs text-muted">{n.body}</span>}
                      <span className="mt-0.5 block text-[11px] text-muted">{timeAgo(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))
            ) : (
              <li className="px-4 py-8 text-center text-sm text-muted">{t("notifications.empty")}</li>
            )}
          </ul>
          <Link to="/app/notifications" onClick={() => setOpen(false)} className="block px-4 py-2.5 text-center text-[13px] font-semibold text-forest hover:bg-cream">
            {t("notifications.all")}
          </Link>
        </div>
      )}
    </div>
  );
}

function AccountMenu() {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  if (!user) return null;
  const initials = user.full_name.split(" ").filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("");
  return (
    <div ref={ref} className="relative">
      <button aria-label="Account" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="grid size-10 place-items-center rounded-full bg-forest text-[13px] font-bold text-white">
        {initials || <Icon name="User" size={16} />}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-56 overflow-hidden rounded-lg border border-line bg-paper py-1 shadow-lift">
          <div className="border-b border-line px-4 py-2.5">
            <div className="text-sm font-semibold">{user.full_name}</div>
            <div className="truncate text-xs text-muted">{user.email}</div>
          </div>
          <button className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-cream" onClick={() => { setOpen(false); navigate("/app/settings"); }}>
            <Icon name="Settings" size={16} /> {t("account.settings")}
          </button>
          <button className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-cream" onClick={async () => { await logout(); navigate("/login"); }}>
            <Icon name="LogOut" size={16} /> {t("account.signout")}
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { t } = useI18n();
  useEffect(() => setDrawer(false), [pathname]);
  const section = user ? NAV[user.role].filter((n) => isActive(pathname, n.to)).pop()?.label : undefined;
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="sticky top-0 hidden h-screen bg-forest-deep lg:block">
        <SideNav />
      </aside>
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-forest-ink/50" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 w-[270px] bg-forest-deep shadow-lift">
            <SideNav onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-cream/90 px-4 backdrop-blur sm:px-6 lg:px-8">
          <button className="grid size-10 place-items-center rounded-full hover:bg-sage-pale lg:hidden" aria-label="Open navigation" onClick={() => setDrawer(true)}>
            <Icon name="Menu" size={20} />
          </button>
          <span className="lg:hidden"><Logo size={26} wordmark={false} /></span>
          <span className="truncate text-sm font-semibold text-muted">{section ? t(NAV_TRANSLATION_KEY[section] ?? section) : ""}</span>
          <div className="ml-auto flex items-center gap-1.5">
            <LanguageSelect compact />
            <NotificationsMenu />
            <AccountMenu />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
