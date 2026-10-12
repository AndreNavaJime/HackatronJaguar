/* PantheraLAB 3.0 blue edition: cache ONLY public app-shell assets, NEVER API responses or wildlife data. */
const CACHE_NAME = 'pantheralab-3-pwa-v1';
const STATIC = ['/offline.html', '/manifest.webmanifest',
  '/icons/pantheralab-3-180.png', '/icons/pantheralab-3-192.png',
  '/icons/pantheralab-3-512.png', '/icons/pantheralab-3-maskable-512.png',
  '/branding/pantheralab-3-original.webp'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys
      .filter(key => key.startsWith('pantheralab-3-pwa-') && key !== CACHE_NAME)
      .map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || req.headers.has('range')) return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  // Online-first navigation; save the *production* app shell only.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(response => {
        if (response.ok && (response.headers.get('content-type') || '').includes('text/html')) {
          event.waitUntil(
            response.clone().text().then(html => {
              // Don't persist the Vite dev entrypoint in the SW cache.
              if (html.includes('/@vite/client')) return;
              return caches.open(CACHE_NAME).then(cache =>
                cache.put('/__pantheralab_3_app_shell__', new Response(html, {
                  headers: { 'Content-Type': 'text/html; charset=utf-8' }
                })));
            }).catch(() => undefined)
          );
        }
        return response;
      }).catch(async () => (await caches.match('/__pantheraid_app_shell__'))
        || (await caches.match('/offline.html')))
    );
    return;
  }

  // Keep install metadata fresh so an old manifest cannot restore a stale splash icon.
  if (url.pathname === '/manifest.webmanifest') {
    event.respondWith(fetch(req).then(response => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.put(req, copy)));
      }
      return response;
    }).catch(() => caches.match(req)));
    return;
  }

  const isAsset = url.pathname.startsWith('/assets/')
    || url.pathname.startsWith('/icons/')
    || url.pathname === '/manifest.webmanifest'
    || url.pathname === '/offline.html';
  if (!isAsset) return;

  // Cache immutable bundled JS/CSS and public icons. Never cache media uploads,
  // generated detections, scientific results, or backend downloads.
  event.respondWith(
    caches.match(req).then(cached => cached || fetch(req).then(response => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.put(req, copy)));
      }
      return response;
    }))
  );
});
