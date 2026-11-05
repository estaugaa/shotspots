const V="ss2-v10";
const SHELL=["./","index.html","style.css","app.js","live.js","sky.js","feed.js","shots.js","research.js","astro.js","data.js","manifest.webmanifest","icon-180.png","icon-192.png",
"https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js","https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"];
self.addEventListener("install",e=>{e.waitUntil(caches.open(V).then(c=>Promise.all(SHELL.map(u=>c.add(u).catch(()=>{})))).then(()=>self.skipWaiting()));});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V&&k!=="ss2-tiles"&&k!=="ss2-feed").map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener("fetch",e=>{
  const u=new URL(e.request.url); if(e.request.method!=="GET")return;
  // live data: always network (the app keeps its own cached copy)
  if(/open-meteo|weather\.gov|swpc|osrm|nominatim|inaturalist|ebird|tidesandcurrents|usgs|7timer/.test(u.host))return;
  // pipeline feed: network first, cached copy when offline
  if(u.origin===location.origin&&u.pathname.startsWith("/feed/")){e.respondWith(fetch(e.request).then(n=>{if(n.ok){const c2=n.clone();caches.open("ss2-feed").then(c=>c.put(e.request,c2));}return n;}).catch(()=>caches.open("ss2-feed").then(c=>c.match(e.request,{ignoreSearch:true}))));return;}
  // map tiles: cache as you browse so the map works offline where you've looked
  if(/tile\.openstreetmap\.org/.test(u.host)){e.respondWith(caches.open("ss2-tiles").then(c=>c.match(e.request).then(r=>r||fetch(e.request).then(n=>{c.put(e.request,n.clone());return n;}))));return;}
  // app shell and fonts: cache first, update in the background
  e.respondWith(caches.open(V).then(c=>c.match(e.request,{ignoreSearch:u.origin===location.origin}).then(r=>{
    const net=fetch(e.request).then(n=>{if(n.ok||n.type==="opaque")c.put(e.request,n.clone());return n;}).catch(()=>r);
    return r||net;})));
});
