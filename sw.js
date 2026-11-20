// 지역 동향 모니터 - 서비스워커 (GitHub Pages 하위 경로에서도 동작하도록 상대경로 사용)
// 화면·데이터 모두 '네트워크 우선, 실패하면 저장본' → 지하철 등 오프라인에서도 마지막 내용 열람
const CACHE = "region-news-v3";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const key = url.origin + url.pathname;            // ?t= 캐시버스터 무시하고 저장
  e.respondWith(
    fetch(e.request).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(key, copy)); }
      return res;
    }).catch(async () => (await caches.match(key)) || (await caches.match(new URL("./", location).href)) || Response.error())
  );
});
