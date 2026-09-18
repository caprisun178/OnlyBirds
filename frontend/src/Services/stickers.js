import { stickersDAO } from '../Dao/stickers.js';

export async function getStickerShelf(userId) {
  // Normalize the API response and calculate the total for the presenter.
  const shelf = await stickersDAO.getForUser(userId);
  return {
    earned: shelf.earned || [],
    locked: shelf.locked || [],
    total: (shelf.earned || []).length + (shelf.locked || []).length,
  };
}