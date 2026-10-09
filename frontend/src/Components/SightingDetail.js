// Components/SightingDetail.js — presentational only. Full detail for one
// sighting: photo, name, date, location, notes, sex/life-stage, source.
// Used by the docked detail panel on Explore Map (Presenters/ExploreMap.js)
// when a pin is selected — everything here besides name/date/source is
// exactly the kind of detail a person logging a sighting would enter to
// help someone else relocate the same bird, so it's all worth surfacing.
import { escapeHtml } from './htmlUtils.js';

const SOURCE_LABELS = { ebird: 'eBird', inat: 'iNaturalist', manual: 'OnlyBirds' };
const LIFE_STAGE_LABELS = { adult: 'Adult', juvenile: 'Juvenile', fledgling: 'Fledgling' };
const SEX_LABELS = { male: 'Male', female: 'Female' };

export function renderSightingDetail(sighting) {
  const name = sighting.species?.common_name || 'Unknown species';
  const sci = sighting.species?.scientific_name;
  const date = sighting.observed_at
    ? new Date(sighting.observed_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : '';
  const sourceLabel = SOURCE_LABELS[sighting.source] || sighting.source;
  const detectionLabel = sighting.detection_type === 'sound' ? 'Heard' : sighting.detection_type === 'sight' ? 'Seen' : '';
  const tags = [SEX_LABELS[sighting.sex], LIFE_STAGE_LABELS[sighting.life_stage]].filter(Boolean);

  return `
    ${sighting.photo_url
      ? `<img
          src="${escapeHtml(sighting.photo_url)}"
          alt="${escapeHtml(name)} — click to enlarge"
          data-action="enlarge-photo"
          data-photo-url="${escapeHtml(sighting.photo_url)}"
          role="button"
          tabindex="0"
          style="width:100%;height:240px;object-fit:cover;border-radius:var(--ob-radius-md);margin-bottom:var(--ob-space-2);cursor:zoom-in;"
        />`
      : ''}
    <h3 class="ob-card__title" style="margin-bottom:0;">
      ${sci
        ? `<span
            data-action="view-profile"
            data-profile-scientific-name="${escapeHtml(sci)}"
            data-profile-common-name="${escapeHtml(name)}"
            role="button"
            tabindex="0"
            style="text-decoration: underline; text-decoration-style: dotted; cursor: pointer;"
          >${escapeHtml(name)}</span>`
        : escapeHtml(name)}
    </h3>
    ${sci ? `<p class="ob-text-sm" style="margin:0;"><em>${escapeHtml(sci)}</em></p>` : ''}
    ${date || detectionLabel
      ? `<p class="ob-text-sm ob-text-muted" style="margin:var(--ob-space-2) 0 0;">${escapeHtml(date)}${date && detectionLabel ? ' — ' : ''}${escapeHtml(detectionLabel)}</p>`
      : ''}
    ${sighting.location_name ? `<p class="ob-text-sm" style="margin:var(--ob-space-1) 0 0;">${escapeHtml(sighting.location_name)}</p>` : ''}
    ${sighting.notes ? `<p class="ob-text-sm" style="font-style:italic;margin:var(--ob-space-2) 0 0;">“${escapeHtml(sighting.notes)}”</p>` : ''}
    ${tags.length > 0 ? `<p class="ob-text-sm" style="margin:var(--ob-space-2) 0 0;">${tags.map(escapeHtml).join(' · ')}</p>` : ''}
    <span class="ob-tag ob-tag--info" style="margin-top:var(--ob-space-2);display:inline-block;">${escapeHtml(sourceLabel)}</span>
  `;
}
