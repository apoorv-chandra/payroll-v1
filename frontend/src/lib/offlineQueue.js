/**
 * offlineQueue — store attendance marks in IndexedDB while offline,
 * automatically replay them on reconnect.
 *
 * Design notes:
 * - We stamp `user_id` at enqueue time so a different user logging in
 *   on the same device never replays someone else's marks.
 * - Auth (401) errors mark the item `needs_auth` and STOP the drain so
 *   the user can re-login; we never silently drop a successful mark.
 * - 4xx ≠ 401 means the server rejected the data (bad date, consent
 *   missing, etc.) — drop with a reason so we don't loop forever.
 * - 5xx / network errors use exponential backoff (30 s → 2 min → 8 min,
 *   capped at 15 min).
 */

const DB_NAME = "payroll-offline";
const STORE = "attendance-queue";
const VERSION = 1;
const MAX_BACKOFF_MS = 15 * 60 * 1000;
const BASE_BACKOFF_MS = 30 * 1000;

let dbp = null;

function getDB() {
  if (dbp) return dbp;
  dbp = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => {
      // Reset so the next call retries instead of inheriting our failure.
      dbp = null;
      reject(req.error);
    };
  });
  // If the promise rejects, clear the cache so a retry creates a fresh request.
  dbp.catch(() => { dbp = null; });
  return dbp;
}

function tx(mode = "readonly") {
  return getDB().then((db) => db.transaction(STORE, mode).objectStore(STORE));
}

function currentUserId() {
  try {
    const u = JSON.parse(localStorage.getItem("auth_user") || "null");
    return u?.id || null;
  } catch { return null; }
}

export async function enqueue(payload) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const item = {
    id,
    payload,
    user_id: currentUserId(),    // ← bind to the user who created it
    queued_at: Date.now(),
    attempts: 0,
    next_attempt_at: 0,
    needs_auth: false,
  };
  const store = await tx("readwrite");
  await new Promise((res, rej) => {
    const r = store.add(item);
    r.onsuccess = () => res();
    r.onerror = () => rej(r.error);
  });
  return id;
}

export async function listQueue() {
  const store = await tx();
  return new Promise((res, rej) => {
    const r = store.getAll();
    r.onsuccess = () => res(r.result || []);
    r.onerror = () => rej(r.error);
  });
}

export async function removeFromQueue(id) {
  const store = await tx("readwrite");
  return new Promise((res, rej) => {
    const r = store.delete(id);
    r.onsuccess = () => res();
    r.onerror = () => rej(r.error);
  });
}

async function updateItem(id, patch) {
  const store = await tx("readwrite");
  return new Promise((res, rej) => {
    const get = store.get(id);
    get.onsuccess = () => {
      const item = get.result;
      if (!item) return res();
      const next = { ...item, ...patch };
      const put = store.put(next);
      put.onsuccess = () => res();
      put.onerror = () => rej(put.error);
    };
    get.onerror = () => rej(get.error);
  });
}

function backoffFor(attempts) {
  // 30s, 1m, 2m, 4m, 8m, capped at 15m.
  return Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** Math.max(0, attempts - 1));
}

/**
 * drainQueue — replay queued attendance marks. Returns
 * { ok, failed, needs_auth, skipped }.
 *
 * - Items belonging to a different user are SKIPPED (kept in queue —
 *   they'll drain when that user logs back in).
 * - On 401, the item is marked `needs_auth=true` and we STOP the drain.
 * - Items not yet past their `next_attempt_at` backoff are skipped.
 */
export async function drainQueue(api) {
  const items = await listQueue();
  const me = currentUserId();
  const now = Date.now();
  let ok = 0;
  let needsAuth = false;
  let skipped = 0;
  const failed = [];

  for (const item of items) {
    if (item.user_id && me && item.user_id !== me) {
      skipped += 1;
      continue;
    }
    if (item.needs_auth || (item.next_attempt_at && item.next_attempt_at > now)) {
      skipped += 1;
      continue;
    }

    try {
      await api.post("/attendance/mark", item.payload);
      await removeFromQueue(item.id);
      ok += 1;
    } catch (e) {
      const status = e?.response?.status;
      if (status === 401) {
        // Don't drop — let the user re-login to recover.
        await updateItem(item.id, { needs_auth: true, last_attempt_at: now });
        needsAuth = true;
        failed.push({ id: item.id, error: "Session expired — sign in again to sync" });
        break;
      } else if (status && status >= 400 && status < 500) {
        // Genuine server rejection (bad data, consent withdrawn, geo-fence).
        const reason = e?.response?.data?.detail || "Rejected by server";
        await removeFromQueue(item.id);
        failed.push({ id: item.id, error: reason });
      } else {
        // Network / 5xx — exponential backoff.
        const attempts = (item.attempts || 0) + 1;
        await updateItem(item.id, {
          attempts,
          last_attempt_at: now,
          next_attempt_at: now + backoffFor(attempts),
        });
        failed.push({ id: item.id, error: "Network error — will retry" });
      }
    }
  }
  return { ok, failed, needs_auth: needsAuth, skipped };
}

export async function queueSize() {
  const items = await listQueue();
  const me = currentUserId();
  // Only count items belonging to the current user so the badge is accurate.
  return items.filter((i) => !i.user_id || !me || i.user_id === me).length;
}

/**
 * clearAuthBlock — call after a successful re-login to unblock items
 * that were paused because of a 401 (only for the current user).
 */
export async function clearAuthBlock() {
  const items = await listQueue();
  const me = currentUserId();
  for (const item of items) {
    if (item.needs_auth && (!item.user_id || !me || item.user_id === me)) {
      await updateItem(item.id, { needs_auth: false, next_attempt_at: 0 });
    }
  }
}
