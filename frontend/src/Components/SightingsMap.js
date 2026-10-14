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

// The pin shown in the docked detail panel (or jumped to from a
// notification) — bigger than every other marker and a color nothing else
// on this map uses (own-sighting is green; this is danger-red, same token
// `.ob-alert--danger` uses), so it's unambiguous which pin "this" is among
// a cluster of plain blue ones. Takes priority over ownSightingIcon when a
// sighting is both selected and the user's own.
function selectedSightingIcon(L) {
  return L.divIcon({
    className: 'ob-selected-sighting-marker',
    html: '<div style="width:22px;height:22px;border-radius:50%;background:var(--ob-color-danger-text);border:3px solid #fff;box-shadow:0 0 0 2px var(--ob-color-danger-text), 0 2px 6px rgba(0,0,0,0.45);"></div>',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
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
 * `isSelected(sighting)`, if given, marks the matching pin (there should
 * only ever be one) with a larger, red, highest-z-index icon — the sighting
 * currently shown in the docked detail panel, so it's unambiguous which pin
 * that panel is actually describing. Re-evaluated on every `setSightings()`
 * call, not just at mount — pass a live-reading closure (e.g.
 * `(s) => s.id === state.selectedSighting?.id`), same as `isOwnSighting`.
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
 *
 * `searchArea` — `{ lat, lng, radiusKm }` or omitted — draws a dashed
 * circle for the actual point+radius search area, so a wide radius (e.g.
 * 25km) doesn't leave the user unable to tell where their search boundary
 * actually is relative to the pins on screen (a real "I can't see where my
 * selected area is" report). `fitSearchArea: true` fits the initial view to
 * that whole circle instead of a fixed zoom on `initialLatLng` — a fixed
 * zoom can't suit every radius option (10km through 100km) at once.
 */
export async function mountSightingsMap(container, { initialLatLng, onSelectSighting, isOwnSighting, isSelected, searchArea, fitSearchArea } = {}) {
  const L = await loadLeaflet();

  const map = L.map(container).setView(initialLatLng || DEFAULT_CENTER, initialLatLng ? LOCATED_ZOOM : DEFAULT_ZOOM);

  addBaseTileLayer(map, L);

  if (searchArea && searchArea.lat != null && searchArea.lng != null && searchArea.radiusKm) {
    const circle = L.circle([searchArea.lat, searchArea.lng], {
      radius: searchArea.radiusKm * 1000,
      color: '#3aa0ff',
      weight: 2,
      dashArray: '6 6',
      fillColor: '#3aa0ff',
      fillOpacity: 0.04,
      interactive: false, // reference outline only — never swallow a click meant for a pin
    }).addTo(map);
    if (fitSearchArea) {
      // The container was just inserted into the DOM this render (every
      // render() here fully rebuilds the map's container), so Leaflet's
      // internal size cache can still be stale/zero at this exact point —
      // zoom-for-bounds math reads that cached size, so computing it before
      // a fresh measurement silently gets the wrong answer (or none at
      // all) instead of actually zooming to fit the circle.
      // invalidateSize() forces a real measurement first. focusArea()
      // below doesn't need this — it only ever runs well after mount, on a
      // later click, once the container's size is already settled.
      map.invalidateSize();

      // Plain fitBounds()/getBoundsZoom() ("contain" framing) guarantees
      // the whole circle stays visible on *both* axes — on a wide-but-short
      // map container (common: this screen's map is a fixed 480px tall but
      // often 1000px+ wide), that guarantee is bottlenecked by the short
      // height, leaving most of the width as empty unused map. A first fix
      // nudged a couple of zoom levels past strict containment, but that
      // still wasn't tight enough (confirmed live: a real "still not
      // zoomed in enough" report after trying it). This computes true
      // "cover" framing instead — fill the frame on whichever axis is
      // tighter (here, almost always width), letting the other axis crop —
      // using the same Web Mercator meters-per-pixel formula Leaflet
      // itself uses internally (`156543.03392 * cos(lat) / 2^zoom`), since
      // Leaflet has no public "cover" equivalent of getBoundsZoom() to
      // call directly. A pin right at the circle's top/bottom edge can now
      // land just outside the visible map — an accepted tradeoff for
      // "fill the frame" over "guarantee every pin is always on-screen."
      const size = map.getSize();
      const diameterMeters = searchArea.radiusKm * 1000 * 2;
      const metersPerPixelAtZ0 = 156543.03392 * Math.cos((searchArea.lat * Math.PI) / 180);
      const zoomToFillSpan = (spanPx) => Math.log2((metersPerPixelAtZ0 * spanPx) / diameterMeters);
      const padding = 16;
      const coverZoom = Math.max(
        zoomToFillSpan(Math.max(size.x - padding * 2, 50)),
        zoomToFillSpan(Math.max(size.y - padding * 2, 50)),
      );
      // Pure "fill the frame" cover framing read as a bit too tight once
      // actually tried live — backed off one level from the strict cover
      // calculation as a deliberate, easy-to-retune breathing-room margin.
      const COVER_ZOOM_BACKOFF = 1;
      const zoom = Math.floor(coverZoom) - COVER_ZOOM_BACKOFF;
      map.setView([searchArea.lat, searchArea.lng], Math.min(Math.max(zoom, 2), 17));
    }
  }

  const ownIcon = ownSightingIcon(L);
  const selectedIcon = selectedSightingIcon(L);
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
        const selected = isSelected?.(s);
        const options = selected
          ? { icon: selectedIcon, zIndexOffset: 1000 } // always drawn above every other pin, even in a cluster
          : isOwnSighting?.(s)
            ? { icon: ownIcon }
            : undefined;
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
