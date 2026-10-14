// Components/LocationPicker.js — a Leaflet map + single draggable marker,
// "click to drop a pin for exactly where you saw it" (like iNaturalist).
//
// Unlike the other Components here, this one isn't stateless markup — a
// live map instance has to survive across interactions, so it owns its own
// DOM subtree and Leaflet object rather than being re-rendered from a
// template string. It still never imports Dao/Services: it only reports
// position changes via `onPositionChange`, and the Presenter decides what
// to do with them (reverse-geocode, save to state, etc.).
//
// Leaflet itself is loaded from a CDN (see `leaflet.js`) — this repo has no
// build step, so a screen pulls in what it needs at runtime.

import { loadLeaflet, DEFAULT_CENTER, addBaseTileLayer } from './leaflet.js';

const DEFAULT_ZOOM = 4;
const PIN_ZOOM = 15;

/**
 * Mounts a map into `container` (give it a fixed height via CSS first).
 * `initialLatLng` is `[lat, lng]` or omitted. `onPositionChange(lat, lng)`
 * fires on every click-to-place or marker drag.
 *
 * Returns `{ setView(lat, lng, zoom?), destroy() }`.
 */
export async function mountLocationPicker(container, { initialLatLng, onPositionChange } = {}) {
  const L = await loadLeaflet();

  const map = L.map(container).setView(
    initialLatLng || DEFAULT_CENTER,
    initialLatLng ? PIN_ZOOM : DEFAULT_ZOOM,
  );

  addBaseTileLayer(map, L);

  let marker = null;

  function placeMarker(lat, lng) {
    if (marker) {
      marker.setLatLng([lat, lng]);
      return;
    }
    marker = L.marker([lat, lng], { draggable: true }).addTo(map);
    marker.on('dragend', () => {
      const pos = marker.getLatLng();
      onPositionChange?.(pos.lat, pos.lng);
    });
  }

  if (initialLatLng) placeMarker(...initialLatLng);

  map.on('click', (e) => {
    placeMarker(e.latlng.lat, e.latlng.lng);
    onPositionChange?.(e.latlng.lat, e.latlng.lng);
  });

  // A nicer starting view than "the whole country," if the browser allows it
  // and there's no pin yet to preserve instead.
  if (!initialLatLng && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => map.setView([pos.coords.latitude, pos.coords.longitude], 11),
      () => {}, // denied or timed out — the default view still works
      { timeout: 4000 },
    );
  }

  return {
    setView(lat, lng, zoom = PIN_ZOOM) {
      map.setView([lat, lng], zoom);
      placeMarker(lat, lng);
    },
    destroy() {
      map.remove();
    },
  };
}
