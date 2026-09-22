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
  // `species` is `{ commonName, scientificName }`; `sense` is 'sight' | 'sound'
  // (from the describe step's "saw it" / "heard it" choice); `fieldNotes` is
  // `{ observedAt, locationName, lat, lng, photoUrl, sex, lifeStage, notes }`.
  // `identificationId` only matters mid-wizard (grading the candidate pick,
  // via identifyService) — the logged observation itself doesn't keep it.
  async createFromWizard(userId, { species, sense, fieldNotes }) {
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
      observed_at: fieldNotes.observedAt,
      location_name: fieldNotes.locationName || null,
      lat: fieldNotes.lat ?? null,
      lng: fieldNotes.lng ?? null,
      photo_url: fieldNotes.photoUrl || null,
      sex: fieldNotes.sex || null,
      life_stage: fieldNotes.lifeStage || null,
      detection_type: sense || null,
      notes: fieldNotes.notes || null,
      source: 'manual',
      status: 'logged',
    });

    return { observation: created, isNewSpecies: !alreadySeen };
  },
};
