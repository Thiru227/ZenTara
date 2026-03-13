// 1. Import OneSignal Service Worker Core
importScripts('https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js');

// 2. Custom Offline Caching Logic for ZenTara PWA
const CACHE_NAME = 'zentara-cache-v2';

// We only specify core shell assets here so the app can load offline
const ASSETS_TO_CACHE = [
  '/', // The landing page / dashboard
  '/manifest.json',
  '/static/icon-192x192.png',
  '/static/icon-512x512.png'
  // For external CDNs, we rely on browser caching or runtime caching below
];

// Install Event: Cache Core Assets
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // Best effort cache; don't fail if some routes demand auth
      return Promise.allSettled(
        ASSETS_TO_CACHE.map(url => cache.add(url).catch(err => console.log('Cache add failed for:', url)))
      );
    })
  );
});

// Activate Event: Cleanup Old Caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch Event: Network-first approach with fallback to cache
self.addEventListener('fetch', (event) => {
  // Ignore non-GET requests (POST, PUT, etc)
  if (event.request.method !== 'GET') return;

  // Ignore Chrome Extension schemes
  if (event.request.url.startsWith('chrome-extension://')) return;

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Only cache successful HTTP responses (avoid 404s/500s or opaque CDN errors mapping to core cache)
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // If network fails (offline), return from cache
        return caches.match(event.request);
      })
  ); // <--- Make sure this closes properly
});
