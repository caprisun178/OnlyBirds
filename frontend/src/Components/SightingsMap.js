// Components/SightingsMap.js — a Leaflet map showing many (non-draggable)
// sighting pins. Like LocationPicker, this owns its own live DOM/Leaflet
// instance rather than being re-rendered from a template string — a
// Presenter mounts it and calls `setSightings()`/`setView()` imperatively
// as data changes.
//
// Pins don't carry their own popup — clicking one calls back to the
// Presenter via `onSelectSighting`, which is expected to show the detail
// somewhere more useful than a small map bubble (Explore Map's docked
// detail panel; see `Components/SightingDetail.js`).

import { loadLeaflet, DEFAULT_CENTER, addBaseTileLayer } from './leaflet.js';

const DEFAULT_ZOOM = 4;
const LOCATED_ZOOM = 10;

// A plain colored dot (not an image asset, unlike Leaflet's default blue
// pin) so the logged-in user's own sightings stand out at a glance without
// needing a second marker-icon image file. Uses the same green the rest of
// the app already uses for "yours" (Life List's "seen" tag), so the color
// reads consistently app-wide rather than introducing a one-off meaning.
// `L.divIcon`'s HTML becomes real DOM inside the page (not an iframe), so
// `var(--ob-color-success-text)` resolves against the page's own theme,
// light or dark, same as any other element.
function ownSightingIcon(L) {
  return L.divIcon({
    className: 'ob-own-sighting-marker',
    html: '<div style="width:14px;height:14px;border-radius:50%;background:var(--ob-color-success-text);border:2px solid #fff;box-shadow:0 0 0 1px var(--ob-color-success-text);"></div>',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

// eBird hotspot checklists all report the exact same lat/lng — a busy
// hotspot's 35 species over a week are 35 sightings stacked on the identical
// point, which without this renders as what looks like a single pin (found
// via a real "it says 35 sightings but there's only one visible" report).
// There's no marker-clustering library wired in (see explore-map.md's "Not
// built" list), so this fans exact-coordinate duplicates out into a small
// ring around the true point instead — cheap, no new dependency, and every
// pin stays individually clickable. `onSelectSighting` still receives the
// unmodified sighting (true lat/lng), so the detail panel/distance math
// downstream is never affected — only where the *marker* is drawn shifts.
const DUPLICATE_COORD_PRECISION = 5; // ~1m — sightings this close are read as "the same point"
const JITTER_RADIUS_DEG = 0.00008; // ~8m — enough to visually separate pins without misplacing them

function layoutMarkerPositions(sightings) {
  const groups = new Map();
  for (const s of sightings) {
    const key = `${s.lat.toFixed(DUPLICATE_COORD_PRECISION)},${s.lng.toFixed(DUPLICATE_COORD_PRECISION)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }
  const positioned = [];
  for (const group of groups.values()) {
    group.forEach((s, i) => {
      if (group.length === 1) {
        positioned.push({ sighting: s, lat: s.lat, lng: s.lng });
        return;
      }
      const angle = (2 * Math.PI * i) / group.length;
      const latRad = (s.lat * Math.PI) / 180;
      positioned.push({
        sighting: s,
        lat: s.lat + JITTER_RADIUS_DEG * Math.sin(angle),
        lng: s.lng + (JITTER_RADIUS_DEG * Math.cos(angle)) / Math.cos(latRad),
      });
    });
  }
  return positioned;
}

/**
 * Mounts a map into `container` (give it a fixed height via CSS first).
 * `initialLatLng` is `[lat, lng]` or omitted (starts at `DEFAULT_CENTER`).
 * `onSelectSighting(sighting)` fires when a pin is clicked. `isOwnSighting(sighting)`,
 * if given, marks matching pins with a distinct highlighted icon instead of
 * Leaflet's default pin — the logged-in user's own observations.
 *
 * Returns `{ setView(lat, lng, zoom?), getView(), setSightings(list), focusArea(bounds), destroy() }`.
 * `getView()` reads the map's current center/zoom — used to preserve the
 * user's pan/zoom across a remount (see `Presenters/ExploreMap.js`; this
 * repo's screens fully rebuild their DOM on every render, which would
 * otherwise snap the map back to the searched location on every filter
 * change). `focusArea(bounds)` — `bounds` is `[[minLat, minLng], [maxLat,
 * maxLng]]` or `null` — zooms to fit that area and draws a rectangle
 * outline around it (used by Explore Map's "top spots" list, so clicking
 * one shows exactly which pins it covers); a later call replaces the
 * outline, and `null` just clears it.
 */
export async function mountSightingsMap(container, { initialLatLng, onSelectSighting, isOwnSighting } = {}) {
  const L = await loadLeaflet();

  const map = L.map(container).setView(initialLatLng || DEFAULT_CENTER, initialLatLng ? LOCATED_ZOOM : DEFAULT_ZOOM);

  addBaseTileLayer(map, L);

  const ownIcon = ownSightingIcon(L);
  let markers = [];
  let areaHighlight = null;

  return {
    setView(lat, lng, zoom = LOCATED_ZOOM) {
      map.setView([lat, lng], zoom);
    },
    getView() {
      const center = map.getCenter();
      return { lat: center.lat, lng: center.lng, zoom: map.getZoom() };
    },
    setSightings(sightings) {
      markers.forEach((m) => map.removeLayer(m));
      const located = sightings.filter((s) => s.lat != null && s.lng != null);
      markers = layoutMarkerPositions(located).map(({ sighting: s, lat, lng }) => {
        const options = isOwnSighting?.(s) ? { icon: ownIcon } : undefined;
        const marker = L.marker([lat, lng], options).addTo(map);
        marker.on('click', () => onSelectSighting?.(s));
        return marker;
      });
    },
    focusArea(bounds) {
      if (areaHighlight) {
        map.removeLayer(areaHighlight);
        areaHighlight = null;
      }
      if (!bounds) return;
      // A single-point area (every sighting at the exact same coordinate)
      // would draw a zero-size rectangle and fitBounds() couldn't zoom
      // sensibly — pad it out a bit either way, proportional to its size so
      // a wide area doesn't get a barely-visible sliver of padding.
      const [[minLat, minLng], [maxLat, maxLng]] = bounds;
      const latPad = Math.max((maxLat - minLat) * 0.2, 0.003);
      const lngPad = Math.max((maxLng - minLng) * 0.2, 0.003);
      const padded = [
        [minLat - latPad, minLng - lngPad],
        [maxLat + latPad, maxLng + lngPad],
      ];
      areaHighlight = L.rectangle(padded, {
        color: '#ff6a00',
        weight: 3,
        fillColor: '#ff6a00',
        fillOpacity: 0.08,
      }).addTo(map);
      map.fitBounds(padded, { maxZoom: 15, padding: [20, 20] });
    },
    destroy() {
      map.remove();
    },
  };
}
