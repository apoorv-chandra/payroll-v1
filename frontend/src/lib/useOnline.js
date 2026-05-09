import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import { drainQueue, queueSize } from "./offlineQueue";

/**
 * useOnline — tracks navigator.onLine and drains the offline attendance queue
 * whenever connectivity returns. Returns { online, queued, drain }.
 */
export default function useOnline() {
  const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);
  const [queued, setQueued] = useState(0);

  const refresh = useCallback(async () => {
    try { setQueued(await queueSize()); } catch { /* noop */ }
  }, []);

  const drain = useCallback(async () => {
    if (!online) return { ok: 0, failed: [] };
    const result = await drainQueue(api);
    await refresh();
    return result;
  }, [online, refresh]);

  useEffect(() => {
    refresh();
    const onUp = () => { setOnline(true); drain(); };
    const onDown = () => setOnline(false);
    window.addEventListener("online", onUp);
    window.addEventListener("offline", onDown);
    // Drain on mount in case we were offline last session
    if (typeof navigator !== "undefined" && navigator.onLine) drain();
    const interval = setInterval(refresh, 5000);
    return () => {
      window.removeEventListener("online", onUp);
      window.removeEventListener("offline", onDown);
      clearInterval(interval);
    };
  }, [drain, refresh]);

  return { online, queued, drain };
}
