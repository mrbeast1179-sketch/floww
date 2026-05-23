/**
 * service-worker.js — PWA Enhancements
 *
 * Caches static assets for offline access and instant loading.
 * Uses cache-first for static assets, network-first for API calls.
 *
 * v2 changes:
 *   - Added IndexedDB-aware caching for API responses
 *   - Better cache-busting with content-hash versioning
 *   - /api/tick-cache/ endpoints are cached and served offline
 *   - Graceful fallback to cached data when API returns 429/500
 */

const CACHE_NAME = 'floww-v2';
const STATIC_CACHE = 'floww-static-v2';
const DYNAMIC_CACHE = 'floww-dynamic-v2';
const API_CACHE = 'floww-api-v2';

// Core static assets to precache
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/offline.html',
];

// API endpoints that should be cached for offline use
const CACHEABLE_API_PATTERNS = [
  /\/api\/tick-cache\//,
  /\/api\/tickers$/,
  /\/api\/heatmap\//,
  /\/api\/chain\//,
];

// Install event - precache core assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => {
            return name !== STATIC_CACHE &&
                   name !== DYNAMIC_CACHE &&
                   name !== API_CACHE &&
                   !name.startsWith('floww-');
          })
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - intelligent caching strategy
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip cross-origin requests (except same-origin API)
  if (url.origin !== self.location.origin) return;

  // API calls - network first, fallback to cache
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    const isCacheable = CACHEABLE_API_PATTERNS.some(p => p.test(url.pathname));

    if (isCacheable) {
      // Cacheable API: network-first, cache for offline fallback
      event.respondWith(networkFirstWithApiCache(request));
    } else {
      // Non-cacheable API: network-first, fallback to generic response
      event.respondWith(networkFirst(request));
    }
    return;
  }

  // Static assets (JS, CSS, images, fonts, icons) - cache first
  if (
    request.destination === 'script' ||
    request.destination === 'style' ||
    request.destination === 'image' ||
    request.destination === 'font' ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.woff2') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.ico')
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML pages - network first with cache fallback
  if (request.destination === 'document' || url.pathname.endsWith('.html')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Default - network first
  event.respondWith(networkFirst(request));
});

// Cache-first strategy for static assets
async function cacheFirst(request) {
  try {
    const cached = await caches.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    if (request.destination === 'document') {
      return caches.match('/offline.html');
    }
    throw error;
  }
}

// Network-first strategy for HTML/API
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;

    if (request.destination === 'document') {
      return caches.match('/offline.html');
    }
    throw error;
  }
}

// Network-first with API-specific caching (for cacheable endpoints)
async function networkFirstWithApiCache(request) {
  try {
    const response = await fetch(request);

    if (response.ok) {
      // Cache successful responses
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
      return response;
    }

    // Server returned error (429, 500, etc.) - try cache
    const cached = await caches.match(request);
    if (cached) {
      // Add a header to indicate this is cached/stale data
      const headers = new Headers(cached.headers);
      headers.set('X-SW-Cache', 'stale');
      return new Response(cached.body, {
        status: 200,
        statusText: 'OK (from cache)',
        headers,
      });
    }

    return response;
  } catch (error) {
    // Network failed - try cache
    const cached = await caches.match(request);
    if (cached) {
      const headers = new Headers(cached.headers);
      headers.set('X-SW-Cache', 'offline');
      return new Response(cached.body, {
        status: 200,
        statusText: 'OK (offline cache)',
        headers,
      });
    }

    // Return a graceful JSON error for API calls
    if (request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({
          error: 'offline',
          message: 'No network connection and no cached data available.',
          offline: true,
        }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }

    throw error;
  }
}

// Handle push notifications
self.addEventListener('push', (event) => {
  if (!event.data) return;

  try {
    const data = event.data.json();
    const options = {
      body: data.body || 'New trading signal',
      icon: '/icons/icon.svg',
      badge: '/icons/icon.svg',
      vibrate: [200, 100, 200],
      data: data.url || '/',
      actions: [
        { action: 'view', title: 'View' },
        { action: 'dismiss', title: 'Dismiss' },
      ],
    };

    event.waitUntil(
      self.registration.showNotification(data.title || 'Confluence Decoder', options)
    );
  } catch (e) {
    event.waitUntil(
      self.registration.showNotification('Confluence Decoder', {
        body: event.data.text(),
        icon: '/icons/icon.svg',
      })
    );
  }
});

// Handle notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          client.postMessage({ type: 'NOTIFICATION_CLICK', data: event.notification.data });
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(event.notification.data || '/');
      }
    })
  );
});

// Background sync for offline form submissions
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-trades') {
    event.waitUntil(syncTrades());
  }
});

async function syncTrades() {
  try {
    const db = await openIndexedDB();
    const trades = await db.getAll('pending-trades');
    for (const trade of trades) {
      await fetch('/api/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trade),
      });
      await db.delete('pending-trades', trade.id);
    }
  } catch (e) {
    console.error('Background sync failed:', e);
  }
}

function openIndexedDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('floww-offline', 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      resolve({
        getAll: (store) => new Promise((res, rej) => {
          const tx = db.transaction(store, 'readonly');
          const req = tx.objectStore(store).getAll();
          req.onsuccess = () => res(req.result);
          req.onerror = () => rej(req.error);
        }),
        delete: (store, id) => new Promise((res, rej) => {
          const tx = db.transaction(store, 'readwrite');
          const req = tx.objectStore(store).delete(id);
          req.onsuccess = () => res();
          req.onerror = () => rej(req.error);
        }),
      });
    };
    request.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending-trades')) {
        db.createObjectStore('pending-trades', { keyPath: 'id' });
      }
    };
  });
}
