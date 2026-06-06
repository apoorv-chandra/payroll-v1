/**
 * Browser permission helpers.
 *
 * Toggling a consent in our UI does NOT automatically grant the underlying
 * OS / browser permission — we still have to trigger the platform's permission
 * dialog. These helpers wrap the relevant Web APIs so the rest of the app can
 * stay declarative.
 */

/**
 * Trigger the OS / browser location permission prompt.
 * Resolves true if the user grants location and we get coords, false otherwise.
 * Never rejects — failures are normal (denial, unsupported, timeout).
 */
export function requestGeoPermission({ timeoutMs = 10000 } = {}) {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) {
      resolve(false);
      return;
    }
    let settled = false;
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    try {
      navigator.geolocation.getCurrentPosition(
        () => done(true),
        () => done(false),
        { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 },
      );
      setTimeout(() => done(false), timeoutMs + 500);
    } catch {
      done(false);
    }
  });
}

/**
 * Query the current browser-level geolocation permission state without
 * triggering the prompt. Returns one of:
 *   "granted" | "denied" | "prompt" | "unknown" | "unsupported"
 *
 * Notes:
 *  - `navigator.permissions` isn't available on every Safari version; we
 *    return "unknown" in that case so the UI can stay neutral.
 *  - "prompt" means the next getCurrentPosition() call will show the OS dialog.
 *  - "denied" means the user previously blocked us; the only way back is via
 *    the browser's per-site permission UI (no JS API).
 */
export async function getGeoPermissionState() {
  if (!("geolocation" in navigator)) return "unsupported";
  if (!("permissions" in navigator) || !navigator.permissions?.query) return "unknown";
  try {
    const r = await navigator.permissions.query({ name: "geolocation" });
    return r.state || "unknown";
  } catch {
    return "unknown";
  }
}
