// services/uploads.js — validation in front of the upload DAO.
// Mirrors the limits enforced server-side (app/services/uploads.py) so bad
// files get rejected before spending a round trip.
import { uploadsDAO } from '../Dao/uploads.js';

// Exported so other image-upload flows (Services/identify.js's photo-ID
// upload) can reuse the exact same limits instead of redeclaring them.
export const MAX_BYTES = 8 * 1024 * 1024; // 8 MB
export const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

export const uploadsService = {
  async uploadPhoto(file) {
    const { photoUrl } = await this.uploadPhotoWithMetadata(file);
    return photoUrl;
  },

  // Same upload, plus where/when the photo says it was taken
  // (`photoMetadata`: `{ lat, lng, taken_at }` or null) — read server-side
  // before the stored copy is stripped. See docs/features/photo-metadata.md.
  async uploadPhotoWithMetadata(file) {
    if (!ALLOWED_TYPES.has(file.type)) {
      throw new Error('Please choose a JPEG, PNG, WebP, or GIF image.');
    }
    if (file.size > MAX_BYTES) {
      throw new Error('That image is too large (max 8 MB).');
    }
    const { photo_url: photoUrl, photo_metadata: photoMetadata } = await uploadsDAO.uploadPhoto(file);
    return { photoUrl, photoMetadata: photoMetadata || null };
  },
};
