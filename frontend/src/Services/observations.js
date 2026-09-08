// services/observations.js — business logic over the observation + life-list DAOs.
import { observationDAO } from '../Dao/observations';
import { lifeListDAO } from '../Dao/lifelist';

export const observationService = {
  async logObservation(userId, observationInput) {
    const created = await observationDAO.create(observationInput);
    const lifeList = await lifeListDAO.getAll(userId);
    const isNewSpecies = !lifeList.some(
      (e) => e.species_id === created.species_id,
    );
    return { observation: created, isNewSpecies };
  },

  async getSortedObservations(userId) {
    const raw = await observationDAO.getAll(userId);
    return [...raw].sort(
      (a, b) => new Date(b.observed_at) - new Date(a.observed_at),
    );
  },
};
