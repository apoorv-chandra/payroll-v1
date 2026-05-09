/**
 * offlineQueue — store attendance marks in IndexedDB while offline,
 * automatically replay them on reconnect.
 *
 * Why not Background Sync API? It needs a service worker registration and
 * is unsupported on iOS Safari. A foreground replay covers 95 % of users
 * and is far simpler.
 */

const DB_NAME = "payroll-offline";
const STORE = "attendance-queue";
const VERSION = 1;

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
    req.onerror = () => reject(req.error);
  });
  return dbp;
}

function tx(mode = "readonly") {
  return getDB().then((db) => db.transaction(STORE, mode).objectStore(STORE));
}

export async function enqueue(payload) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const item = { id, payload, queued_at: Date.now(), attempts: 0 };
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

export async function bumpAttempts(id) {
  const store = await tx("readwrite");
  return new Promise((res, rej) => {
    const get = store.get(id);
    get.onsuccess = () => {
      const item = get.result;
      if (!item) return res();
      item.attempts = (item.attempts || 0) + 1;
      item.last_attempt_at = Date.now();
      const put = store.put(item);
      put.onsuccess = () => res();
      put.onerror = () => rej(put.error);
    };
    get.onerror = () => rej(get.error);
  });
}

/**
 * drainQueue — replay queued attendance marks via the supplied API client.
 * Returns { ok: number, failed: Array<{id, error}> }.
 */
export async function drainQueue(api) {
  const items = await listQueue();
  let ok = 0;
  const failed = [];
  for (const item of items) {
    try {
      await api.post("/attendance/mark", item.payload);
      await removeFromQueue(item.id);
      ok += 1;
    } catch (e) {
      const status = e?.response?.status;
      if (status && status >= 400 && status < 500) {
        // 4xx → server rejected (bad data, expired, etc). Drop so we don't loop forever.
        await removeFromQueue(item.id);
        failed.push({ id: item.id, error: e?.response?.data?.detail || "Rejected by server" });
      } else {
        await bumpAttempts(item.id);
        failed.push({ id: item.id, error: "Network error — will retry" });
      }
    }
  }
  return { ok, failed };
}

export async function queueSize() {
  const items = await listQueue();
  return items.length;
}
