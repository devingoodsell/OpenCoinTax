import { useState, useEffect, useCallback, useRef } from "react";

interface UseApiQueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string;
  refetch: () => void;
}

/**
 * Hook for fetching data from an API endpoint with loading/error state management.
 *
 * @param fetcher - Async function that returns the data (typically an axios call)
 * @param deps - Dependency array that triggers a refetch when values change
 * @param options - Configuration options
 * @returns Object with data, loading, error, and refetch
 *
 * @example
 * const { data, loading, error, refetch } = useApiQuery(
 *   () => fetchWallets().then(r => r.data),
 *   []
 * );
 */
export function useApiQuery<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: { enabled?: boolean; onError?: (msg: string) => void } = {},
): UseApiQueryResult<T> {
  const { enabled = true, onError } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState("");
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(() => {
    setLoading(true);
    setError("");
    fetcherRef.current()
      .then((result) => setData(result))
      .catch((e) => {
        const msg = e.response?.data?.detail || e.message || "Request failed";
        setError(msg);
        onError?.(msg);
      })
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (enabled) refetch();
  }, [enabled, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, error, refetch };
}
