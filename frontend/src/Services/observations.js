// services/observations.js — business logic over the observation + life-list DAOs.
import { observationDAO } from '../Dao/observations.js';
import { lifeListDAO } from '../Dao/lifelist.js';

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

  // Confirmed-species + field-notes step of the Add Observation wizard.
  // `species` is `{ commonName, scientificName }`; `fieldNotes` is
  // `{ observedAt, locationName, photoUrl, sex, lifeStage, notes }`.
  async createFromWizard(userId, { species, identificationId, fieldNotes }) {
    const priorLifeList = await lifeListDAO.getAll(userId);
    const alreadySeen = priorLifeList.some(
      (e) => e.species?.scientific_name === species.scientificName,
    );

    const created = await observationDAO.create({
      user_id: userId,
      species: {
        common_name: species.commonName,
        scientific_name: species.scientificName,
      },
      identification_id: identificationId || null,
      observed_at: fieldNotes.observedAt,
      location_name: fieldNotes.locationName || null,
      photo_url: fieldNotes.photoUrl || null,
      sex: fieldNotes.sex || null,
      life_stage: fieldNotes.lifeStage || null,
      notes: fieldNotes.notes || null,
      source: 'manual',
      status: 'logged',
    });

    return { observation: created, isNewSpecies: !alreadySeen };
  },
};
