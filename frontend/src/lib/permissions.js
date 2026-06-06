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
