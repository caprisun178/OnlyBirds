// services/uploads.js — validation in front of the upload DAO.
// Mirrors the limits enforced server-side (app/services/uploads.py) so bad
// files get rejected before spending a round trip.
import { uploadsDAO } from '../Dao/uploads.js';

const MAX_BYTES = 8 * 1024 * 1024; // 8 MB
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

export const uploadsService = {
  async uploadPhoto(file) {
    if (!ALLOWED_TYPES.has(file.type)) {
      throw new Error('Please choose a JPEG, PNG, WebP, or GIF image.');
    }
    if (file.size > MAX_BYTES) {
      throw new Error('That image is too large (max 8 MB).');
    }
    const { photo_url: photoUrl } = await uploadsDAO.uploadPhoto(file);
    return photoUrl;
  },
};
