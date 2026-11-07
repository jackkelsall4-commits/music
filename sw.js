// Keeps the app working with no internet. Songs and cover art are stored by the page
// (Cache "om-songs", under media/...); this worker serves cover art from there and keeps
// a copy of the app itself.
const SHELL = 'om-phone-shell-v1';
const BASE = new URL('./', self.location).href;
const FILES = ['./', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png']
  .map(f => new URL(f, BASE).href);

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('om-phone-shell-') && k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const href = url.origin + url.pathname;
  if (href.startsWith(BASE + 'media/')) {
    e.respondWith(caches.open('om-songs').then(c => c.match(href))
      .then(hit => hit || new Response('', { status: 404 })));
    return;
  }
  const isShell = e.request.mode === 'navigate' || FILES.includes(href);
  if (!isShell) return;
  const key = e.request.mode === 'navigate' ? BASE : href;
  // network first (so updates show up), but give up after 3s and use the saved copy
  e.respondWith((async () => {
    const cache = await caches.open(SHELL);
    try {
      const res = await Promise.race([
        fetch(e.request),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000)),
      ]);
      if (res.ok) cache.put(key, res.clone());
      return res;
    } catch {
      return (await cache.match(key)) || Response.error();
    }
  })());
});
