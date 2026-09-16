// services/identify.js — business logic over the identify DAO.
// The free-text description is part of validation: it must say enough that
// the identify service has something to match against before we call the API.
import { identifyDAO } from '../Dao/identify.js';

const MIN_DESCRIPTION_LENGTH = 3;

export const identifyService = {
  validateDescription(text) {
    const trimmed = (text || '').trim();
    if (trimmed.length < MIN_DESCRIPTION_LENGTH) {
      return 'Describe the bird in a few more words (size, color, where you saw it) so we can suggest matches.';
    }
    return null;
  },

  async describe(text, hints) {
    const error = identifyService.validateDescription(text);
    if (error) throw new Error(error);
    const cleanHints = hints
      ? Object.fromEntries(
          Object.entries(hints).filter(([, value]) => value != null && value !== ''),
        )
      : undefined;
    return identifyDAO.describe(text.trim(), cleanHints && Object.keys(cleanHints).length ? cleanHints : undefined);
  },

  // `speciesCode: null` means "none of these match what I saw".
  async selectCandidate(identificationId, speciesCode) {
    return identifyDAO.select(identificationId, speciesCode);
  },
};
