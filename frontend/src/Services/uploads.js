// services/uploads.js — validation in front of the upload DAO.
// Mirrors the limits enforced server-side (app/services/uploads.py) so bad
// files get rejected before spending a round trip.
import { uploadsDAO } from '../Dao/uploads.js';

// Exported so other image-upload flows (Services/identify.js's photo-ID
// upload, Services/bulkImport.js) reuse the exact same limits instead of
// redeclaring them. 25 MB fits full-size camera JPEGs; the server stores a
// resized copy (docs/features/bulk-import.md, open question 1).
export const MAX_BYTES = 25 * 1024 * 1024; // 25 MB
export const ALLOWED_TYPES = new Set([
  'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif',
]);
// For <input type="file" accept>. HEIC needs the extensions too: Windows
// browsers don't know the MIME type and would otherwise grey the files out.
export const ACCEPT_ATTR = 'image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif,.heic,.heif';
export const TYPES_HINT = 'JPEG, PNG, WebP, GIF, or HEIC, up to 25 MB.';

// Windows browsers usually report .heic files with an empty type — fall
// back to the extension for those (the server does the same).
function effectiveType(file) {
  if (file.type) return file.type;
  return /\.(heic|heif)$/i.test(file.name || '') ? 'image/heic' : '';
}

// Throws a user-facing Error, or returns nothing if the file is fine.
export function validateImageFile(file) {
  if (!ALLOWED_TYPES.has(effectiveType(file))) {
    throw new Error('Please choose a JPEG, PNG, WebP, GIF, or HEIC image.');
  }
  if (file.size > MAX_BYTES) {
    throw new Error('That image is too large (max 25 MB).');
  }
}

export const uploadsService = {
  async uploadPhoto(file) {
    const { photoUrl } = await this.uploadPhotoWithMetadata(file);
    return photoUrl;
  },

  // Same upload, plus where/when the photo says it was taken
  // (`photoMetadata`: `{ lat, lng, taken_at }` or null) — read server-side
  // before the stored copy is stripped. See docs/features/photo-metadata.md.
  async uploadPhotoWithMetadata(file) {
    validateImageFile(file);
    const { photo_url: photoUrl, photo_metadata: photoMetadata } = await uploadsDAO.uploadPhoto(file);
    return { photoUrl, photoMetadata: photoMetadata || null };
  },
};
