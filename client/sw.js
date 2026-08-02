const CACHE_NAME = 'escape-bot-v50';
const ASSETS_TO_CACHE = [
    './',
    './index.html',
    './manifest.json',
    './icon.svg',
    './assets/puzzles/elara-clock-gallery.png',
    './assets/puzzles/bowling-binary-motor-v3.png',
    './assets/puzzles/terrace-morse-cats-hriste-v2.png',
    './assets/puzzles/sports-pigpen-hodiny.svg',
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

    event.respondWith(
        caches.match(event.request)
            .then((response) => response || fetch(event.request))
    );
});
