import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "./api";
import { drainQueue, queueSize } from "./offlineQueue";

/**
 * useOnline — tracks navigator.onLine and drains the offline attendance queue
 * whenever connectivity returns. Returns { online, queued, needsAuth, drain }.
 *
 * Robustness:
 * - Drains on `online` event (browser-fired).
 * - Drains on mount (covers "was offline last session" / first paint).
 * - Periodic drain every 30 s while items are queued AND online.
 *   Some browsers report `navigator.onLine=true` while the network is
 *   actually flaky — the periodic drain papers over this.
 * - `needsAuth` flag flips true if any item got a 401; user must re-login
 *   then call `drain()` (or just navigate — the next mount will re-attempt).
 */
export default function useOnline() {
  const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);
  const [queued, setQueued] = useState(0);
  const [needsAuth, setNeedsAuth] = useState(false);
  const draining = useRef(false);   // re-entry guard

  const refresh = useCallback(async () => {
    try { setQueued(await queueSize()); } catch { /* noop */ }
  }, []);

  const drain = useCallback(async () => {
    if (draining.current) return { ok: 0, failed: [], needs_auth: needsAuth };
    if (!navigator.onLine) return { ok: 0, failed: [], needs_auth: needsAuth };
    draining.current = true;
    try {
      const result = await drainQueue(api);
      if (result.needs_auth) setNeedsAuth(true);
      else if (result.ok > 0 && needsAuth) setNeedsAuth(false);
      await refresh();
      return result;
    } finally {
      draining.current = false;
    }
  }, [refresh, needsAuth]);

  useEffect(() => {
    let cancelled = false;
    const safeDrain = () => { if (!cancelled) drain(); };
    const safeRefresh = () => { if (!cancelled) refresh(); };

    const onUp = () => { setOnline(true); safeDrain(); };
    const onDown = () => setOnline(false);
    window.addEventListener("online", onUp);
    window.addEventListener("offline", onDown);

    // Drain on mount in case we were offline last session.
    safeDrain();

    // Refresh badge count every 5 s.
    const refreshTimer = setInterval(safeRefresh, 5000);
    // Periodic drain every 30 s — catches false-positive online reports.
    const drainTimer = setInterval(safeDrain, 30000);

    return () => {
      cancelled = true;
      window.removeEventListener("online", onUp);
      window.removeEventListener("offline", onDown);
      clearInterval(refreshTimer);
      clearInterval(drainTimer);
    };
  }, [drain, refresh]);

  return { online, queued, needsAuth, drain };
}
