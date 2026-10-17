import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { clearCache } from "./data";
import type { Me } from "./types";

type AuthCtx = {
  user: Me | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({} as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<Me>("/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauth = () => setUser(null);
    window.addEventListener("agastya:unauthorized", onUnauth);
    return () => window.removeEventListener("agastya:unauthorized", onUnauth);
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    clearCache();
    const me = await api<Me>("/auth/login", { body: { email, password } });
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      clearCache();
      setUser(null);
    }
  }, []);

  return <Ctx.Provider value={{ user, ready, login, logout, refresh }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
