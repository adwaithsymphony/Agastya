// A small client-side router (history API) — enough for AGASTYA's flat route table.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type AnchorHTMLAttributes, type ReactNode } from "react";

type Loc = { pathname: string; search: string };
type Ctx = { loc: Loc; navigate: (to: string, opts?: { replace?: boolean }) => void; params: Record<string, string> };

const RouterCtx = createContext<Ctx>({ loc: { pathname: "/", search: "" }, navigate: () => {}, params: {} });

function current(): Loc {
  return { pathname: window.location.pathname, search: window.location.search };
}

export function Router({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState<Loc>(current);
  useEffect(() => {
    const on = () => setLoc(current());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  const navigate = useCallback((to: string, opts?: { replace?: boolean }) => {
    if (opts?.replace) window.history.replaceState(null, "", to);
    else window.history.pushState(null, "", to);
    setLoc(current());
    if (!to.includes("#")) window.scrollTo({ top: 0 });
  }, []);
  const value = useMemo(() => ({ loc, navigate, params: {} }), [loc, navigate]);
  return <RouterCtx.Provider value={value}>{children}</RouterCtx.Provider>;
}

export function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  const pp = pattern.split("/").filter(Boolean);
  const sp = pathname.split("/").filter(Boolean);
  if (pp.length !== sp.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < pp.length; i++) {
    if (pp[i].startsWith(":")) params[pp[i].slice(1)] = decodeURIComponent(sp[i]);
    else if (pp[i] !== sp[i]) return null;
  }
  return params;
}

export type RouteDef = { path: string; element: ReactNode };

export function Routes({ routes, fallback }: { routes: RouteDef[]; fallback: ReactNode }) {
  const ctx = useContext(RouterCtx);
  for (const r of routes) {
    const params = matchPath(r.path, ctx.loc.pathname);
    if (params) return <RouterCtx.Provider value={{ ...ctx, params }}>{r.element}</RouterCtx.Provider>;
  }
  return <>{fallback}</>;
}

export function useLocation() {
  return useContext(RouterCtx).loc;
}
export function useNavigate() {
  return useContext(RouterCtx).navigate;
}
export function useParams<T extends Record<string, string>>() {
  return useContext(RouterCtx).params as T;
}
export function useSearchParam(name: string): string | null {
  return new URLSearchParams(useContext(RouterCtx).loc.search).get(name);
}

export function Link({ to, children, onClick, ...rest }: { to: string } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const navigate = useNavigate();
  return (
    <a
      href={to}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to);
      }}
      {...rest}
    >
      {children}
    </a>
  );
}

export function Redirect({ to }: { to: string }) {
  const navigate = useNavigate();
  useEffect(() => navigate(to, { replace: true }), [to, navigate]);
  return null;
}
