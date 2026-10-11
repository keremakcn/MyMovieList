const VERSION='myshelf-shell-2026-10-11-2';
const SHELL=['/index.html','/style.css','/app.mjs','/hero.mjs','/people-model.mjs','/people-storage.mjs','/strings.mjs','/storage.mjs','/sync-model.mjs','/name-policy.mjs','/assets/logo.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(VERSION).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('myshelf-shell-') && k!==VERSION).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  // Never cache authentication, private sync responses, showcase visibility or
  // API errors. Offline personal records live in account-scoped IndexedDB.
  if(event.request.method!=='GET' || url.origin!==location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/u/'))return;
  const navigation=event.request.mode==='navigate';
  // Standalone pages must never replace the offline application's HTML shell.
  if(navigation && !/^\/(?:discover|library|account|updates|profile|people|(?:movie|person)\/[1-9]\d{0,9})?\/?$/.test(url.pathname))return;
  if(!navigation && !SHELL.includes(url.pathname) && !url.pathname.startsWith('/assets/avatars/'))return;
  event.respondWith((async()=>{
    const cache=await caches.open(VERSION),key=navigation ? '/index.html' : event.request;
    try{const result=await fetch(event.request);if(result.ok)await cache.put(key,result.clone());return result;}
    catch{const saved=await cache.match(key);return saved || new Response('Offline',{status:503});}
  })());
});
