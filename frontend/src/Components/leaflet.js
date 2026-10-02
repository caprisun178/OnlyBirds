// Components/leaflet.js — shared Leaflet CDN loader, used by any component
// that needs a live map (LocationPicker, SightingsMap). No build step means
// no bundled map library — pulled in at runtime instead, once, and cached
// on `window.L` so multiple map components sharing a page don't double-load it.

const LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
const LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';

let leafletLoading = null;

export function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletLoading) return leafletLoading;

  leafletLoading = new Promise((resolve, reject) => {
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = LEAFLET_CSS;
      document.head.appendChild(link);
    }
    const script = document.createElement('script');
    script.src = LEAFLET_JS;
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error('Could not load the map.'));
    document.head.appendChild(script);
  });
  return leafletLoading;
}

// Continental US — used only until a screen has something better (a real
// pin, a searched place, the user's own location).
export const DEFAULT_CENTER = [39.8, -98.6];

// Esri's "Light Gray Canvas" basemap — a plain, minimal reference map (light
// gray land/water, light street lines, no business/POI icons) instead of a
// dense navigable street map. Used to be CARTO's "Positron" tiles here, but
// CARTO started requiring a free API key for those in September 2026 (every
// anonymous request now comes back stamped "API KEY REQUIRED"); Esri's
// equivalent needs no key or account at all, which matters more for a
// no-build-step static frontend with nowhere sensible to keep a key out of
// the public JS anyway. Two layers stacked: `_Base` is the plain gray
// canvas, `_Reference` is a transparent overlay of place labels/boundaries —
// using the base alone would mean no city names at all, just shapes.
// NOTE: Esri's tile path is `{z}/{y}/{x}` (y before x), unlike the `{z}/{x}/{y}`
// convention most other providers (including the OSM tiles these replaced)
// use — easy to get backwards and see tiles the wrong-side-up.
const BASE_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}';
const REFERENCE_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}';
// Esri's tiles stop at z16 — maxNativeZoom lets Leaflet upscale its z16
// tiles for anything past that (map pins zoomed in close) instead of
// requesting a z17+ tile that doesn't exist and showing a blank square.
const MAX_NATIVE_ZOOM = 16;
const TILE_ATTRIBUTION = 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, DeLorme, NAVTEQ';

// Shared so LocationPicker and SightingsMap can't drift onto two different
// basemaps over time.
export function addBaseTileLayer(map, L) {
  const base = L.tileLayer(BASE_TILE_URL, {
    maxZoom: 20,
    maxNativeZoom: MAX_NATIVE_ZOOM,
    attribution: TILE_ATTRIBUTION,
  }).addTo(map);
  L.tileLayer(REFERENCE_TILE_URL, { maxZoom: 20, maxNativeZoom: MAX_NATIVE_ZOOM }).addTo(map);
  return base;
}
