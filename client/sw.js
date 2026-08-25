const CACHE_NAME = 'escape-bot-v106';
const ASSETS_TO_CACHE = [
    './',
    './index.html',
    './chronos3d.js',
    './chronos-webgl/dist/index.html',
    './chronos-webgl/dist/assets/chronos.js',
    './chronos-webgl/dist/assets/index.css',
    './chronos-webgl/dist/worlds/chronos-institute.json',
    './manifest.json',
    './icon.svg',
    './assets/puzzles/elara-clock-gallery.png',
    './assets/puzzles/bowling-binary-motor-v3.png',
    './assets/puzzles/terrace-morse-cats-hriste-v2.png',
    './assets/puzzles/sports-pigpen-hodiny.svg',
    './assets/puzzles/time-machine-jigsaw.png',
    './assets/textures/pardubice/facades.json',
    './assets/textures/pardubice/zelenabrana-facade-v2.png',
    './assets/textures/pardubice/zelenabrana-tower-east-v1.png',
    './assets/textures/pardubice/pernstynske-se-frontage-v1.png',
    './assets/voices/captain_crystal_recovered.mp3',
    './assets/voices/captain_final_countdown.mp3',
    './assets/voices/captain_first_contact.mp3',
    './assets/voices/captain_motor_recovered.mp3',
    './assets/voices/elara_first_contact.mp3',
    './assets/voices/elara_return_vector.mp3',
    './assets/voices/elara_returned.mp3',
    './assets/voices/elara_stabilizer_recovered.mp3',
    './assets/voices/elara_temporal_reveal.mp3',
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

self.addEventListener('message', (event) => {
    if (event.data?.type === 'GET_BUILD_VERSION') {
        event.source?.postMessage({type: 'BUILD_VERSION', version: CACHE_NAME.replace('escape-bot-', '')});
    }
});

self.addEventListener('fetch', (event) => {
    const requestUrl = new URL(event.request.url);
    // Dynamický backendový stav a mapová geometrie nesmí uvíznout ve statické
    // cache aplikace. Pro API vždy preferujeme přímo síťovou odpověď.
    if (requestUrl.pathname.startsWith('/api/')) {
        event.respondWith(fetch(event.request));
        return;
    }
    if (event.request.url.includes('/ws') || event.request.method !== 'GET') return;

    // HTML musí být po nasazení kompatibilní s aktuálním backendem. Při
    // navigaci proto preferujeme síť a cache používáme pouze při výpadku.
    if (event.request.mode === 'navigate' || requestUrl.pathname.endsWith('/index.html')) {
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
