/**
 * Generic async hook: { data, loading, error, execute }
 * execute(fn) accepts a function returning a Promise.
 */
import { useState, useCallback } from "react";

export function useApi() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const execute = useCallback(async (apiFn) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await apiFn();
      setData(result);
      return result;
    } catch (err) {
      setError(err.message ?? "Unknown error");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, execute };
}
