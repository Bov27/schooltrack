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
html,body{margin:0;height:100%;overflow:hidden;background:#dfe5df;font-family:sans-serif}
#map{position:relative;width:100%;height:100%;overflow:hidden}
#map img{position:absolute;width:256px;height:256px;user-select:none}
svg{position:absolute;inset:0;width:100%;height:100%}
#attr{position:absolute;right:4px;bottom:3px;font-size:10px;color:#17222b;background:rgba(255,255,255,.75);padding:1px 4px;border-radius:3px}
</style></head>
<body><div id="map"></div>
<script>
(function(){
  var d = ${payload};
  var el = document.getElementById("map");
  var W = el.clientWidth, H = el.clientHeight, PAD = 28, T = 256;
  function px(p, z){
    var s = T * Math.pow(2, z), lat = p[0] * Math.PI / 180;
    return [ (p[1] + 180) / 360 * s, (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * s ];
  }
  var pts = [];
  d.geofences.forEach(function(g){ pts = pts.concat(g.ring); });
  if (d.point) pts.push(d.point.position);
  if (!pts.length) pts.push([2.4419, -76.6063]);
  var z = d.tiles.maxZoom;
  for (; z > 3; z--) {
    var xs = pts.map(function(p){ return px(p, z); });
    var minX = Math.min.apply(null, xs.map(function(q){return q[0];})), maxX = Math.max.apply(null, xs.map(function(q){return q[0];}));
    var minY = Math.min.apply(null, xs.map(function(q){return q[1];})), maxY = Math.max.apply(null, xs.map(function(q){return q[1];}));
    if (maxX - minX <= W - 2 * PAD && maxY - minY <= H - 2 * PAD) break;
  }
  if (pts.length === 1) z = Math.min(z, 17);
  var all = pts.map(function(p){ return px(p, z); });
  var cx = (Math.min.apply(null, all.map(function(q){return q[0];})) + Math.max.apply(null, all.map(function(q){return q[0];}))) / 2;
  var cy = (Math.min.apply(null, all.map(function(q){return q[1];})) + Math.max.apply(null, all.map(function(q){return q[1];}))) / 2;
  var left = cx - W / 2, top = cy - H / 2, n = Math.pow(2, z);
  for (var tx = Math.floor(left / T); tx <= Math.floor((left + W) / T); tx++) {
    for (var ty = Math.floor(top / T); ty <= Math.floor((top + H) / T); ty++) {
      if (ty < 0 || ty >= n) continue;
      var img = document.createElement("img");
      img.src = d.tiles.url.replace("{z}", z).replace("{x}", ((tx % n) + n) % n).replace("{y}", ty);
      img.style.left = (tx * T - left) + "px"; img.style.top = (ty * T - top) + "px";
      img.alt = ""; el.appendChild(img);
    }
  }
  function sp(p){ var q = px(p, z); return [q[0] - left, q[1] - top]; }
  var ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
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
  el.appendChild(svg);
  var a = document.createElement("div"); a.id = "attr"; a.textContent = d.tiles.attribution; el.appendChild(a);
})();
</script></body></html>`;
}
