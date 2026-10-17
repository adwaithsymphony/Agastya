// Minimal data hooks: cached GETs keyed by path, with prefix invalidation after mutations.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

type Listener = () => void;
const listeners = new Map<string, Set<Listener>>();
const cache = new Map<string, unknown>();

export function invalidate(...prefixes: string[]) {
  for (const [key, set] of listeners) {
    if (prefixes.some((p) => key.startsWith(p))) {
      cache.delete(key);
      set.forEach((fn) => fn());
    }
  }
  for (const key of [...cache.keys()]) if (prefixes.some((p) => key.startsWith(p))) cache.delete(key);
}

export function clearCache() {
  cache.clear();
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | undefined>(() => (path ? (cache.get(path) as T | undefined) : undefined));
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path && !cache.has(path));
  const [tick, setTick] = useState(0);
  const pathRef = useRef(path);
  pathRef.current = path;

  useEffect(() => {
    if (!path) return;
    const fn = () => setTick((t) => t + 1);
    if (!listeners.has(path)) listeners.set(path, new Set());
    listeners.get(path)!.add(fn);
    return () => {
      listeners.get(path)?.delete(fn);
    };
  }, [path]);

  useEffect(() => {
    if (!path) {
      setData(undefined);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    const cached = cache.get(path) as T | undefined;
    if (cached !== undefined) setData(cached);
    else setLoading(true);
    setError(null);
    api<T>(path, { signal: ctrl.signal })
      .then((d) => {
        cache.set(path, d);
        if (pathRef.current === path) setData(d);
      })
      .catch((e) => {
        if ((e as Error).name !== "AbortError" && pathRef.current === path) setError(e as ApiError);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export function useMutation<A, R>(fn: (args: A) => Promise<R>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = useCallback(
    async (args: A): Promise<R | undefined> => {
      setPending(true);
      setError(null);
      try {
        return await fn(args);
      } catch (e) {
        setError(e as ApiError);
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [fn],
  );
  return { run, pending, error, setError };
}
