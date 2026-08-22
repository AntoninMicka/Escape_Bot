const CACHE_NAME = 'escape-bot-v66';
const ASSETS_TO_CACHE = [
    './',
    './index.html',
    './manifest.json',
    './icon.svg',
    './assets/puzzles/elara-clock-gallery.png',
    './assets/puzzles/bowling-binary-motor-v3.png',
    './assets/puzzles/terrace-morse-cats-hriste-v2.png',
    './assets/puzzles/sports-pigpen-hodiny.svg',
    './assets/puzzles/time-machine-jigsaw.png',
    'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cache) => {
                    if (cache !== CACHE_NAME) return caches.delete(cache);
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    // Vyhneme se cachování WebSocket spojení a backendových API (pokud nějaké budou)
    if (event.request.url.includes('/ws') || event.request.method !== 'GET') return;

    // HTML musí být po nasazení kompatibilní s aktuálním backendem. Při
    // navigaci proto preferujeme síť a cache používáme pouze při výpadku.
    if (event.request.mode === 'navigate' || new URL(event.request.url).pathname.endsWith('/index.html')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                    return response;
                })
                .catch(() => caches.match(event.request).then((response) => response || caches.match('./index.html')))
        );
        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then((response) => response || fetch(event.request))
    );
});
