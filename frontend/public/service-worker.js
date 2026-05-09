// Minimal service worker for PWA install criteria & basic offline shell.
const CACHE = "payroll-shell-v1";
const ASSETS = ["/", "/manifest.json", "/icon-192.svg", "/icon-512.svg", "/favicon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => null));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) return; // never cache API
  e.respondWith(
    fetch(req).catch(() => caches.match(req).then((m) => m || caches.match("/")))
  );
});
