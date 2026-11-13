/**
 * A small self-contained map page for a WebView: map tiles plus an SVG overlay with
 * the campus geofences and the person's point. No external script is loaded; only
 * tile images, and the coordinates never leave the phone except in tile requests
 * for the area being shown.
 */

export type LatLng = [number, number];
export type MapBase = "satellite" | "street";

export interface MapData {
  geofences: { ring: LatLng[]; active: boolean }[];
  point: { position: LatLng; accuracyM: number | null; color: string } | null;
  base: MapBase;
}

const TILES: Record<MapBase, { url: string; maxZoom: number; attribution: string }> = {
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxZoom: 18,
    attribution: "Imágenes © Esri, Maxar",
  },
  street: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    maxZoom: 19,
    attribution: "© OpenStreetMap",
  },
};

/** GeoJSON polygon positions are [lng, lat]. */
export function ringFromGeoJson(coordinates: number[][][]): LatLng[] {
  return (coordinates[0] ?? []).map(([lng, lat]) => [lat ?? 0, lng ?? 0] as LatLng);
}

/** JSON that is safe to embed inside a <script> element. */
export function scriptJson(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026");
}

export function buildMapHtml(data: MapData): string {
  const tiles = TILES[data.base];
  const payload = scriptJson({ ...data, tiles });
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<style>
html,body{margin:0;height:100%;overflow:hidden;background:#dfe5df;font-family:sans-serif;-webkit-user-select:none;user-select:none}
#map{position:relative;width:100%;height:100%;overflow:hidden;touch-action:none}
#tiles img{position:absolute;width:256px;height:256px;pointer-events:none}
svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#attr{position:absolute;right:4px;bottom:3px;font-size:10px;color:#17222b;background:rgba(255,255,255,.75);padding:1px 4px;border-radius:3px}
#ctl{position:absolute;left:8px;bottom:8px;display:flex;flex-direction:column;gap:6px}
#ctl button{width:40px;height:40px;border:0;border-radius:10px;background:rgba(255,255,255,.95);color:#123a47;font-size:22px;font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,.25)}
#ctl button.wide{width:auto;padding:0 10px;font-size:13px}
</style></head>
<body><div id="map"><div id="tiles"></div></div>
<script>
(function(){
  var d = ${payload};
  var el = document.getElementById("map"), layer = document.getElementById("tiles");
  var W = el.clientWidth, H = el.clientHeight, PAD = 30, T = 256;
  var MAXZ = d.tiles.maxZoom, MINZ = 3;
  var ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
  el.appendChild(svg);
  function world(z){ return T * Math.pow(2, z); }
  function px(p, z){
    var s = world(z), lat = p[0] * Math.PI / 180;
    return [ (p[1] + 180) / 360 * s, (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * s ];
  }
  function fit(points){
    for (var z = MAXZ; z > MINZ; z--) {
      var q = points.map(function(p){ return px(p, z); });
      var xs = q.map(function(v){ return v[0]; }), ys = q.map(function(v){ return v[1]; });
      var w = Math.max.apply(null, xs) - Math.min.apply(null, xs), h = Math.max.apply(null, ys) - Math.min.apply(null, ys);
      if (w <= W - 2 * PAD && h <= H - 2 * PAD) {
        return { z: z, cx: (Math.max.apply(null, xs) + Math.min.apply(null, xs)) / 2, cy: (Math.max.apply(null, ys) + Math.min.apply(null, ys)) / 2 };
      }
    }
    var c = px(points[0], MINZ); return { z: MINZ, cx: c[0], cy: c[1] };
  }
  var fences = [];
  d.geofences.forEach(function(g){ fences = fences.concat(g.ring); });
  var view;
  function focusPoint(){
    var p = d.point ? d.point.position : (fences[0] || [2.4419, -76.6063]);
    var z = Math.min(17, MAXZ), c = px(p, z); view = { z: z, cx: c[0], cy: c[1] };
  }
  function focusAll(){ var all = fences.concat(d.point ? [d.point.position] : []); view = all.length ? fit(all) : null; if (!view) focusPoint(); }
  // Start close to the person; include the campus only when it is near enough to read.
  focusAll();
  if (d.point && view.z < 16) focusPoint();

  var cache = {};
  function render(){
    var left = view.cx - W / 2, top = view.cy - H / 2, z = view.z, n = Math.pow(2, z), used = {};
    for (var tx = Math.floor(left / T); tx <= Math.floor((left + W) / T); tx++) {
      for (var ty = Math.floor(top / T); ty <= Math.floor((top + H) / T); ty++) {
        if (ty < 0 || ty >= n) continue;
        var key = z + "/" + tx + "/" + ty, img = cache[key];
        if (!img) {
          img = document.createElement("img");
          img.src = d.tiles.url.replace("{z}", z).replace("{x}", ((tx % n) + n) % n).replace("{y}", ty);
          img.alt = ""; cache[key] = img; layer.appendChild(img);
        }
        img.style.left = (tx * T - left) + "px"; img.style.top = (ty * T - top) + "px";
        used[key] = true;
      }
    }
    Object.keys(cache).forEach(function(k){ if (!used[k]) { layer.removeChild(cache[k]); delete cache[k]; } });
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    function sp(p){ var q = px(p, z); return [q[0] - left, q[1] - top]; }
    d.geofences.forEach(function(g){
      var poly = document.createElementNS(ns, "polygon");
      poly.setAttribute("points", g.ring.map(function(p){ return sp(p).join(","); }).join(" "));
      var c = g.active ? "#1e6b52" : "#8a948c";
      poly.setAttribute("fill", c); poly.setAttribute("fill-opacity", g.active ? "0.22" : "0.08");
      poly.setAttribute("stroke", c); poly.setAttribute("stroke-width", "3");
      if (!g.active) poly.setAttribute("stroke-dasharray", "6 6");
      svg.appendChild(poly);
    });
    if (d.point) {
      var c = sp(d.point.position);
      if (d.point.accuracyM) {
        var mpp = 156543.03392 * Math.cos(d.point.position[0] * Math.PI / 180) / Math.pow(2, z);
        var acc = document.createElementNS(ns, "circle");
        acc.setAttribute("cx", c[0]); acc.setAttribute("cy", c[1]); acc.setAttribute("r", Math.max(d.point.accuracyM / mpp, 6));
        acc.setAttribute("fill", d.point.color); acc.setAttribute("fill-opacity", "0.18");
        acc.setAttribute("stroke", d.point.color); acc.setAttribute("stroke-width", "1.5");
        svg.appendChild(acc);
      }
      var dot = document.createElementNS(ns, "circle");
      dot.setAttribute("cx", c[0]); dot.setAttribute("cy", c[1]); dot.setAttribute("r", "9");
      dot.setAttribute("fill", d.point.color); dot.setAttribute("stroke", "#fff"); dot.setAttribute("stroke-width", "3");
      svg.appendChild(dot);
    }
  }
  // Zoom keeping the given screen point (default: centre) in place.
  function zoom(delta, sx, sy){
    var z2 = Math.max(MINZ, Math.min(MAXZ, view.z + delta));
    if (z2 === view.z) return;
    sx = sx === undefined ? W / 2 : sx; sy = sy === undefined ? H / 2 : sy;
    var k = Math.pow(2, z2 - view.z), wx = view.cx - W / 2 + sx, wy = view.cy - H / 2 + sy;
    view = { z: z2, cx: wx * k - sx + W / 2, cy: wy * k - sy + H / 2 };
    render();
  }

  // One finger pans, two fingers pinch, a double tap zooms in.
  var pointers = {}, startDist = 0, lastTap = 0;
  function dist(){ var p = Object.keys(pointers).map(function(k){ return pointers[k]; }); return p.length < 2 ? 0 : Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y); }
  el.addEventListener("pointerdown", function(e){
    if (e.target.tagName === "BUTTON") return;
    el.setPointerCapture(e.pointerId);
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
    startDist = dist();
    var now = Date.now();
    if (Object.keys(pointers).length === 1 && now - lastTap < 300) zoom(1, e.clientX, e.clientY);
    lastTap = now;
  });
  el.addEventListener("pointermove", function(e){
    var prev = pointers[e.pointerId]; if (!prev) return;
    var count = Object.keys(pointers).length;
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
    if (count === 1) { view.cx -= e.clientX - prev.x; view.cy -= e.clientY - prev.y; render(); return; }
    var now = dist();
    if (startDist && now / startDist > 1.5) { zoom(1); startDist = now; }
    else if (startDist && now / startDist < 0.67) { zoom(-1); startDist = now; }
  });
  function up(e){ delete pointers[e.pointerId]; startDist = dist(); }
  el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);

  var ctl = document.createElement("div"); ctl.id = "ctl";
  function button(label, title, action, wide){
    var b = document.createElement("button"); b.textContent = label; b.title = title; b.setAttribute("aria-label", title);
    if (wide) b.className = "wide";
    b.addEventListener("click", function(ev){ ev.stopPropagation(); action(); }); ctl.appendChild(b);
  }
  button("+", "Acercar", function(){ zoom(1); });
  button("−", "Alejar", function(){ zoom(-1); });
  if (d.point) button("Yo", "Centrar en mi ubicación", function(){ focusPoint(); render(); }, true);
  if (fences.length) button("Sede", "Ver la sede completa", function(){ focusAll(); render(); }, true);
  el.appendChild(ctl);

  var a = document.createElement("div"); a.id = "attr"; a.textContent = d.tiles.attribution; el.appendChild(a);
  render();
})();
</script></body></html>`;
}
