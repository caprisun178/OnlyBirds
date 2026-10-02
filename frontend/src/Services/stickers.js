import { stickersDAO } from '../Dao/stickers.js';

export async function getStickerShelf(userId) {
  // Resolve API-hosted artwork and calculate the total for the presenter.
  const shelf = await stickersDAO.getForUser(userId);
  if (!Array.isArray(shelf?.earned) || !Array.isArray(shelf?.locked)) {
    throw new Error('The sticker shelf response was invalid.');
  }
  const withAssetUrls = (items) => items.map((sticker) => ({
    ...sticker,
    image_url: sticker.image_url ? stickersDAO.assetUrl(sticker.image_url) : null,
  }));
  const earned = withAssetUrls(shelf.earned);
  const locked = withAssetUrls(shelf.locked);
  return {
    earned,
    locked,
    total: earned.length + locked.length,
  };
}