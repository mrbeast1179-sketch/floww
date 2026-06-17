/**
 * service-worker.js — KILL-SWITCH (2026-06-17)
 *
 * The previous caching SW (floww-v2/v4) kept serving stale bundles in the local
 * PWA, masking every frontend change for ~30h. This replacement does the opposite:
 * on the next page load it unregisters itself, deletes ALL caches, and reloads the
 * open windows so they fetch fresh code straight from the dev server.
 *
 * Net effect: after ONE normal reload of the Confluence Decoder PWA, the old SW is
 * gone for good and never caches dev builds again. (Offline caching is intentionally
 * disabled locally — restore the prior SW from git history if a prod PWA needs it.)
 */
self.addEventListener('install', () => {
  // Activate immediately, don't wait for old clients to close.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // 1. Nuke every cache the old SW created.
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    // 2. Take control, then unregister ourselves.
    await self.clients.claim();
    await self.registration.unregister();
    // 3. Reload every open window so it loads fresh from the network.
    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach((client) => client.navigate(client.url));
  })());
});

// While alive, never serve from cache — always hit the network.
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
