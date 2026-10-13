// components/MigrationBarStrip.js — one species' year as 52 weekly bars,
// eBird bar-chart style: bar height = how common the bird is that week,
// relative to its own peak. Presentational only.
import { escapeHtml } from './CandidateList.js';

const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

// `weekly`: 52 values 0–1. `currentWeek`: 1–52, highlighted. `label`: the
// plain-language summary read out instead of 52 bars.
export function renderBarStrip(weekly, { currentWeek, label = '' } = {}) {
  return `
    <div role="img" aria-label="${escapeHtml(label)}"
         style="display:grid;grid-template-columns:repeat(52,1fr);gap:1px;height:22px;">
      ${weekly.map((v, i) => {
        const h = v > 0 ? Math.max(8, Math.round(v * 100)) : 0;
        // This week: a shaded track behind the bar, so the bar itself still
        // shows the real value.
        const track = currentWeek === i + 1 ? 'background:var(--ob-color-surface-alt);outline:1px solid var(--ob-color-text-muted);' : '';
        return `<div style="display:flex;align-items:flex-end;${track}"><div style="width:100%;height:${h}%;background:var(--ob-color-brand);border-radius:1px;"></div></div>`;
      }).join('')}
    </div>
  `;
}

// Month initials spaced to line up with renderBarStrip's 52 columns.
export function renderMonthAxis() {
  return `
    <div aria-hidden="true" class="ob-text-muted" style="display:grid;grid-template-columns:repeat(12,1fr);font-size:11px;">
      ${MONTHS.map((m) => `<span>${m}</span>`).join('')}
    </div>
  `;
}
