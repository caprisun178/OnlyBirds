// services/identify.js — business logic over the identify DAO.
// The free-text description is part of validation: it must say enough that
// the identify service has something to match against before we call the API.
import { identifyDAO } from '../Dao/identify.js';
import { ALLOWED_TYPES, MAX_BYTES } from './uploads.js';

const MIN_DESCRIPTION_LENGTH = 3;

export const identifyService = {
  validateDescription(text) {
    const trimmed = (text || '').trim();
    if (trimmed.length < MIN_DESCRIPTION_LENGTH) {
      return 'Describe the bird in a few more words (size, color, where you saw it) so we can suggest matches.';
    }
    return null;
  },

  // `sense` is 'sight' (default, "I saw it") or 'sound' ("I heard it") —
  // decides whether candidates carry a call/song recording alongside the photo.
  // `location` is `{ lat, lng, observedAt }` (observedAt a "YYYY-MM-DD" date,
  // not a full datetime-local value — eBird's regional checklist is per
  // calendar day), all optional — see AddObservation.js's when/where step.
  async describe(text, hints, sense = 'sight', location) {
    const error = identifyService.validateDescription(text);
    if (error) throw new Error(error);
    const cleanHints = hints
      ? Object.fromEntries(
          Object.entries(hints).filter(([, value]) => value != null && value !== ''),
        )
      : undefined;
    return identifyDAO.describe(
      text.trim(),
      cleanHints && Object.keys(cleanHints).length ? cleanHints : undefined,
      sense,
      toRegional(location),
    );
  },

  // `speciesCode: null` means "none of these match what I saw".
  async selectCandidate(identificationId, speciesCode) {
    return identifyDAO.select(identificationId, speciesCode);
  },

  // Same validation as uploadsService.uploadPhoto() (identical limits,
  // reused not redeclared) — the classifier never sees a file the server
  // would reject anyway.
  async identifyPhoto(file, location) {
    if (!ALLOWED_TYPES.has(file.type)) {
      throw new Error('Please choose a JPEG, PNG, WebP, or GIF image.');
    }
    if (file.size > MAX_BYTES) {
      throw new Error('That image is too large (max 8 MB).');
    }
    return identifyDAO.identifyPhoto(file, toRegional(location));
  },
};

// `{ lat, lng, observedAt }` -> `{ lat, lng, observed_at }`, same camelCase
// -> snake_case convention as Services/observations.js. `observedAt` here is
// expected to already be a plain "YYYY-MM-DD" date (truncated by the caller
// from the when/where step's datetime-local value) — eBird's regional
// checklist lookup is per calendar day, not per minute.
function toRegional(location) {
  if (!location) return undefined;
  const { lat, lng, observedAt } = location;
  if (lat == null && lng == null && !observedAt) return undefined;
  return { lat, lng, observed_at: observedAt || undefined };
}
