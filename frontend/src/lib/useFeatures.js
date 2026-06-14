/**
 * useFeatures — single source of truth for what modules the logged-in user
 * can see. Fetches /api/me/features once and caches in module-level state
 * so any component can subscribe without refetching.
 *
 * Shape returned by the API:
 *   { role, features: [{ code, name, description, icon, landing_path }] }
 *
 * Why a hook (not context): keeps the diff small. AuthContext stays focused
 * on identity; this stays focused on permissions. Components can `useFeatures()`
 * anywhere.
 */
import { useEffect, useState } from "react";
import { api } from "./api";

let cache = null;        // { role, features }
let inflight = null;     // de-dupe in-flight requests
const listeners = new Set();

function notify() {
  for (const l of listeners) l(cache);
}

export async function loadFeatures(force = false) {
  if (cache && !force) return cache;
  if (inflight) return inflight;
  inflight = api
    .get("/me/features")
    .then((r) => {
      cache = r.data;
      notify();
      return cache;
    })
    .catch(() => {
      cache = { role: null, features: [] };
      notify();
      return cache;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function resetFeatures() {
  cache = null;
  notify();
}

export default function useFeatures() {
  const [state, setState] = useState(cache);

  useEffect(() => {
    listeners.add(setState);
    if (!cache) loadFeatures();
    return () => listeners.delete(setState);
  }, []);

  return {
    loading: state === null,
    role: state?.role,
    features: state?.features || [],
    has: (code) => !!(state?.features || []).find((f) => f.code === code),
    reload: () => loadFeatures(true),
  };
}
