// services/bulkImport.js — the logic behind Presenters/BulkImport.js. No DOM
// in here: the presenter owns rendering, this owns the queue, the flags,
// and logging. See docs/features/bulk-import.md.
//
// Each photo is one ordinary POST /identify/photo?store=true call, run from
// the browser two at a time — no server-side job queue (§1, "Why the browser
// drives the loop").
import { identifyService } from './identify.js';
import { geocodingService } from './geocoding.js';
import { validateImageFile } from './uploads.js';
import { observationDAO } from '../Dao/observations.js';
import { lifeListDAO } from '../Dao/lifelist.js';

export const MAX_PHOTOS = 50; // decided 2026-10-13 — keeps review + undo manageable
export const LOW_CONFIDENCE = 0.5; // below this a card starts unticked
const CONCURRENCY = 2;
const DUPLICATE_MINUTES = 10;
const DUPLICATE_METERS = 200;
const GEOCODE_SPACING_MS = 1100; // Nominatim's usage policy: ~1 request/second

// One item per picked photo. `status`: 'queued' | 'identifying' | 'ready' | 'failed'.
export function makeItems(fileList) {
  const files = Array.from(fileList);
  const items = files.slice(0, MAX_PHOTOS).map((file, index) => ({
    index,
    file,
    previewUrl: URL.createObjectURL(file),
    status: 'queued',
    error: null,
    candidates: [],
    species: null, // { commonName, scientificName }
    confidence: null,
    userPicked: false, // true once the user chose the species (dropdown or search)
    photoUrl: null,
    observedAt: '', // datetime-local "YYYY-MM-DDTHH:MM"; '' = use the batch default
    dateFromPhoto: false,
    lat: null,
    lng: null,
    locationName: '',
    include: true,
    sex: '',
    lifeStage: '',
    notes: '',
  }));
  return { items, skipped: Math.max(0, files.length - MAX_PHOTOS) };
}

// Identifies every queued/failed item, CONCURRENCY at a time. `onChange(item)`
// fires on each status change so the presenter can repaint just that card.
export async function scanAll(items, onChange) {
  const pending = items.filter((it) => it.status === 'queued' || it.status === 'failed');
  let next = 0;
  async function worker() {
    while (next < pending.length) {
      const item = pending[next];
      next += 1;
      await scanOne(item, onChange);
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
}

async function scanOne(item, onChange) {
  item.status = 'identifying';
  item.error = null;
  onChange(item);
  try {
    validateImageFile(item.file);
    // No location/date sent: the server reads them from the photo itself.
    const response = await identifyService.identifyPhoto(item.file, undefined, { store: true });
    item.candidates = response.candidates || [];
    const top = item.candidates[0];
    item.species = top ? { commonName: top.common_name, scientificName: top.scientific_name } : null;
    item.confidence = top ? top.confidence : null;
    item.include = Boolean(top) && top.confidence >= LOW_CONFIDENCE;
    item.photoUrl = response.photo_url || null;
    const meta = response.photo_metadata;
    if (meta?.taken_at) {
      item.observedAt = meta.taken_at.slice(0, 16);
      item.dateFromPhoto = true;
    }
    if (meta?.lat != null && meta?.lng != null) {
      item.lat = meta.lat;
      item.lng = meta.lng;
    }
    item.status = 'ready';
  } catch (err) {
    item.status = 'failed';
    item.error = err.message || 'Could not identify this photo.';
    item.include = false;
  }
  onChange(item);
}

// Per-item warning flags for the review card. Recomputed after any edit
// that could change them (species, date, location).
export function computeFlags(items) {
  const flags = new Map();
  for (const it of items) {
    flags.set(it.index, {
      noLocation: it.status === 'ready' && (it.lat == null || it.lng == null),
      // Only the model's own guess can be "low confidence" — once the user
      // picks a species themselves, it's their call.
      lowConfidence: it.status === 'ready' && !it.userPicked && (it.confidence ?? 0) < LOW_CONFIDENCE,
      possibleDuplicate: false,
    });
  }
  // Same species within ~10 minutes and ~200 m of an earlier card: usually a
  // burst of shots of one bird. Flag only — the user decides.
  const ready = items.filter((it) => it.status === 'ready' && it.species && it.observedAt);
  for (let i = 0; i < ready.length; i += 1) {
    for (let j = 0; j < i; j += 1) {
      const a = ready[i];
      const b = ready[j];
      if (a.species.scientificName !== b.species.scientificName) continue;
      const minutes = Math.abs(new Date(a.observedAt) - new Date(b.observedAt)) / 60000;
      if (minutes > DUPLICATE_MINUTES) continue;
      const bothPlaced = a.lat != null && b.lat != null;
      if (bothPlaced && distanceMeters(a.lat, a.lng, b.lat, b.lng) > DUPLICATE_METERS) continue;
      flags.get(a.index).possibleDuplicate = true;
    }
  }
  return flags;
}

function distanceMeters(lat1, lng1, lat2, lng2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371000 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Fills `locationName` for every item with a point but no label. Points are
// rounded to ~100 m and cached, so photos from one park cost one or two
// lookups, spaced to respect Nominatim's rate limit. `onChange(item)` per fill.
export async function labelLocations(items, onChange) {
  const cache = new Map();
  let lastCall = 0;
  for (const it of items) {
    if (it.lat == null || it.lng == null || it.locationName) continue;
    const key = `${it.lat.toFixed(3)},${it.lng.toFixed(3)}`;
    if (!cache.has(key)) {
      const wait = lastCall + GEOCODE_SPACING_MS - Date.now();
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
      lastCall = Date.now();
      try {
        const place = await geocodingService.reverse(it.lat, it.lng);
        cache.set(key, place?.display_name || '');
      } catch {
        cache.set(key, '');
      }
    }
    if (!it.locationName && cache.get(key)) {
      it.locationName = cache.get(key);
      onChange(it);
    }
  }
}

// Logs every ticked, identified item as its own observation, sharing one
// import batch id (so it can be undone). Sequential on purpose: up to 50
// calls is fine, and per-item failures stay easy to report and retry.
// `batchDefaultAt` (datetime-local) is used for items whose photo had no date.
// Pass back the returned `seenBefore` when retrying failures, so species
// logged by the first attempt still count as new in the summary.
export async function logAll(items, { userId, importBatchId, batchDefaultAt, onProgress, seenBefore = null }) {
  const toLog = items.filter((it) => it.include && it.status === 'ready' && it.species && !it.loggedId);
  if (!seenBefore) {
    const priorLifeList = await lifeListDAO.getAll(userId);
    seenBefore = new Set(priorLifeList.map((e) => e.species?.scientific_name).filter(Boolean));
  }

  const failed = [];
  let done = 0;
  for (const it of toLog) {
    try {
      const localValue = it.observedAt || batchDefaultAt;
      const created = await observationDAO.create({
        user_id: userId,
        species: { common_name: it.species.commonName, scientific_name: it.species.scientificName },
        observed_at: new Date(localValue).toISOString(),
        location_name: it.locationName || null,
        lat: it.lat,
        lng: it.lng,
        photo_url: it.photoUrl,
        sex: it.sex || null,
        life_stage: it.lifeStage || null,
        notes: it.notes || null,
        detection_type: 'sight',
        source: 'manual',
        status: 'logged',
        import_batch_id: importBatchId,
      });
      it.loggedId = created.id;
    } catch (err) {
      failed.push(it);
    }
    done += 1;
    onProgress?.(done, toLog.length);
  }

  const loggedItems = items.filter((it) => it.loggedId);
  const newSpecies = new Set(
    loggedItems.map((it) => it.species.scientificName).filter((sci) => !seenBefore.has(sci)),
  );
  return { logged: loggedItems.length, failed, newSpecies: [...newSpecies], seenBefore };
}

export async function undoImport(userId, importBatchId) {
  return observationDAO.undoImport(userId, importBatchId);
}

export function newImportBatchId() {
  return crypto.randomUUID ? crypto.randomUUID() : `batch-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
