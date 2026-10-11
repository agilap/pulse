import { useCallback, useEffect, useRef, useState } from "react";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Fetch data on mount and re-fetch when `pollMs` elapses. Dedupes concurrent
 * in-flight requests so overlapping poll ticks never double-fetch.
 */
export function usePolledResource<T>(
  fetcher: () => Promise<T>,
  pollMs = 5000,
): State<T> & { reload: () => void } {
  const [state, setState] = useState<State<T>>({
    data: null,
    loading: true,
    error: null,
  });
  const inFlight = useRef(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await fetcherRef.current();
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState((s) => ({
        data: s.data,
        loading: false,
        error: e instanceof Error ? e.message : "Request failed",
      }));
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    run();
    if (pollMs <= 0) return;
    const t = setInterval(run, pollMs);
    return () => clearInterval(t);
  }, [run, pollMs]);

  return { ...state, reload: run };
}
