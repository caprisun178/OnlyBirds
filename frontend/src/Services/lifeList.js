// services/lifeList.js — the region completion view + region-picker options.
// Sorting is done here, client-side, over data already fetched — changing
// sort order shouldn't cost a network round trip when we already have the
// checklist in hand.
import { regionsDAO } from '../Dao/regions.js';

export const lifeListService = {
  async getRegionOptions(parentCode, type) {
    return regionsDAO.getChildren(parentCode, type);
  },

  // { regionCode, total, seen, species } — species come back in taxonomic
  // order from the API; call sortSpecies() for the other sort modes.
  async getChecklist(regionCode, userId) {
    const data = await regionsDAO.getChecklist(regionCode, userId);
    return {
      regionCode: data.region_code,
      total: data.total,
      seen: data.seen,
      species: data.species,
    };
  },

  sortSpecies(species, sort) {
    const list = [...species];
    if (sort === 'alphabetical') {
      list.sort((a, b) => a.common_name.localeCompare(b.common_name));
    } else if (sort === 'recent') {
      list.sort((a, b) => {
        if (a.seen && b.seen) return new Date(b.first_observed_at) - new Date(a.first_observed_at);
        if (a.seen) return -1;
        if (b.seen) return 1;
        return a.common_name.localeCompare(b.common_name);
      });
    } else {
      // 'taxonomic' (default): species already come back in that order from
      // the API. Bucket observed birds first (still in taxonomic order among
      // themselves), then not-yet-seen birds — so the default "top 50" +
      // "show more" progression surfaces the user's own life list before it
      // works through the rest of the region's checklist.
      const seenList = list.filter((sp) => sp.seen);
      const unseenList = list.filter((sp) => !sp.seen);
      return [...seenList, ...unseenList];
    }
    return list;
  },

  // Distinct eBird family names ("bird type") present in a checklist, sorted
  // alphabetically — feeds the bird-type filter dropdown.
  getFamilies(species) {
    const names = new Set(species.map((sp) => sp.family_common_name).filter(Boolean));
    return [...names].sort((a, b) => a.localeCompare(b));
  },
};
