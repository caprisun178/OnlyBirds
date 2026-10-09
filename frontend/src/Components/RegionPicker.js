// Components/RegionPicker.js — presentational cascading region select
// (country -> state/province -> county), same eBird hierarchy as the Life
// List region filter. No state of its own: the Presenter owns pickerCountry
// / pickerState / pickerCounty / countries / states / counties and re-renders
// this on every change, the same pattern LifeList.js uses inline.
//
// data-role attributes let the Presenter find the three <select> elements
// after render() replaces the markup, since plain innerHTML re-renders lose
// any listeners attached to the old nodes.

import { escapeHtml } from './htmlUtils.js';

export function renderRegionPicker({
  countries,
  states,
  counties,
  pickerCountry,
  pickerState,
  pickerCounty,
  loading = false,
}) {
  return `
    <div class="ob-grid" style="--ob-grid-min: 180px;" data-role="region-picker">
      <div class="ob-field">
        <label class="ob-label" for="region-picker-country">Country</label>
        <select id="region-picker-country" class="ob-select" data-role="region-country">
          <option value="">${loading && countries.length === 0 ? 'Loading…' : 'Select a country'}</option>
          ${countries
            .map(
              (c) =>
                `<option value="${escapeHtml(c.code)}" ${c.code === pickerCountry ? 'selected' : ''}>${escapeHtml(c.name)}</option>`
            )
            .join('')}
        </select>
      </div>
      <div class="ob-field">
        <label class="ob-label" for="region-picker-state">State / province</label>
        <select id="region-picker-state" class="ob-select" data-role="region-state" ${pickerCountry ? '' : 'disabled'}>
          <option value="">Whole country</option>
          ${states
            .map(
              (s) =>
                `<option value="${escapeHtml(s.code)}" ${s.code === pickerState ? 'selected' : ''}>${escapeHtml(s.name)}</option>`
            )
            .join('')}
        </select>
      </div>
      <div class="ob-field">
        <label class="ob-label" for="region-picker-county">County</label>
        <select id="region-picker-county" class="ob-select" data-role="region-county" ${pickerState ? '' : 'disabled'}>
          <option value="">Whole state</option>
          ${counties
            .map(
              (c) =>
                `<option value="${escapeHtml(c.code)}" ${c.code === pickerCounty ? 'selected' : ''}>${escapeHtml(c.name)}</option>`
            )
            .join('')}
        </select>
      </div>
    </div>
  `;
}