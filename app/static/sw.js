/* 手機通知用的 service worker。只處理推播，不快取網頁（資料一律即時從伺服器拿）。 */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { title: '通知', body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || '通知', {
    body: d.body || '', icon: '/static/icon.svg',
    tag: d.tag || undefined, renotify: !!d.tag, data: { url: d.url || '/' }
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ws => {
    for (const w of ws) { if (w.url.startsWith(self.location.origin)) { w.focus(); return w.navigate(url); } }
    return self.clients.openWindow(url);
  }));
});
