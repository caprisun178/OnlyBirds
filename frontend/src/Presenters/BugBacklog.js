// Presenters/BugBacklog.js — admin-only bug report backlog. Lists every
// "Report a problem" submission (Components/ReportButton.js ->
// POST /feedback, app/routers/feedback.py) as a table; an admin can filter
// by status, change status (not started / investigating / not fixed /
// fixed), and take ownership of a report (PATCH /admin/bug-reports/{id}).
//
// No real access control yet — see app/routers/admin.py's own docstring for
// why: there's no auth/roles anywhere in this app (user-profiles.md is
// still "Planned"). "Admin-only" currently just means it's a distinct,
// clearly-labeled screen linked from Home's nav, nothing stronger. Gate it
// for real once real auth exists.
//
//   import { mount } from './Presenters/BugBacklog.js';
//   mount(document.getElementById('app'));

import { bugReportsService } from '../Services/bugReports.js';
import { escapeHtml } from '../Components/htmlUtils.js';

const STATUS_OPTIONS = [
  ['not_started', 'Not started'],
  ['investigating', 'Investigating'],
  ['not_fixed', 'Not fixed'],
  ['fixed', 'Fixed'],
];
const STATUS_LABELS = Object.fromEntries(STATUS_OPTIONS);

export function mount(container, props = {}) {
  const { onNavigate } = props; // optional — omitted when this screen is previewed standalone

  const state = {
    loading: true,
    error: null,
    reports: [],
    statusFilter: '', // '' = all
  };

  render();
  loadReports();

  async function loadReports() {
    state.loading = true;
    state.error = null;
    render();
    try {
      state.reports = await bugReportsService.list();
    } catch (err) {
      state.error = err.message || 'Could not load the bug backlog.';
      state.reports = [];
    } finally {
      state.loading = false;
      render();
    }
  }

  // Not-started bugs float to the top regardless of date; everything else
  // keeps the API's own newest-first order within its group — JS's sort is
  // stable, so this is a pure "promote not_started" pass, not a full resort.
  function visibleReports() {
    const filtered = state.statusFilter
      ? state.reports.filter((r) => r.status === state.statusFilter)
      : state.reports;
    return [...filtered].sort((a, b) => {
      const aTop = a.status === 'not_started' ? 0 : 1;
      const bTop = b.status === 'not_started' ? 0 : 1;
      return aTop - bTop;
    });
  }

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <h1>Bug backlog</h1>
        <p class="ob-text-muted ob-text-sm">Every bug submitted through the floating report button. Not started bugs always sort to the top. No real access control yet — see this screen's own file comment.</p>
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? renderLoading() : renderBody()}
      </div>
    `;
    if (onNavigate) {
      container.querySelector('[data-action="back-to-home"]').addEventListener('click', () => onNavigate('home'));
    }
    wire();
  }

  function renderLoading() {
    return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
  }

  function renderBody() {
    return `
      ${renderFilterBar()}
      ${state.reports.length === 0
        ? '<div class="ob-card ob-text-center"><p class="ob-card__body">No reports yet.</p></div>'
        : renderTable()}
    `;
  }

  function renderFilterBar() {
    return `
      <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2); max-width:260px;">
        <label class="ob-label" for="status-filter">Filter by status</label>
        <select id="status-filter" class="ob-select">
          <option value="">All statuses</option>
          ${STATUS_OPTIONS.map(([value, label]) => `<option value="${value}" ${value === state.statusFilter ? 'selected' : ''}>${label}</option>`).join('')}
        </select>
      </div>
    `;
  }

  function renderTable() {
    const visible = visibleReports();
    if (visible.length === 0) {
      return '<div class="ob-card ob-text-center"><p class="ob-card__body">No reports match this filter.</p></div>';
    }
    return `
      <div class="ob-card ob-card--flat" style="overflow-x:auto; padding:0;">
        <table class="ob-table">
          <thead>
            <tr>
              <th>Message</th>
              <th>Screen</th>
              <th>Reported</th>
              <th>User</th>
              <th>Owner</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${visible.map(renderRow).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderRow(r) {
    const dateLabel = new Date(r.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
    const tooltip = [r.url, r.user_agent].filter(Boolean).join('\n');
    return `
      <tr data-report-id="${escapeHtml(r.id)}">
        <td style="max-width:360px;" ${tooltip ? `title="${escapeHtml(tooltip)}"` : ''}>${escapeHtml(r.message)}</td>
        <td>${escapeHtml(r.screen || '—')}</td>
        <td style="white-space:nowrap;">${escapeHtml(dateLabel)}</td>
        <td>${escapeHtml(r.user_id || '—')}</td>
        <td>
          <input
            type="text"
            class="ob-input"
            style="width:120px;"
            placeholder="Unassigned"
            value="${escapeHtml(r.owner || '')}"
            data-action="edit-owner"
            data-report-id="${escapeHtml(r.id)}"
          />
        </td>
        <td>
          <select class="ob-select" style="width:auto;" data-action="set-status" data-report-id="${escapeHtml(r.id)}">
            ${STATUS_OPTIONS.map(([value, label]) => `<option value="${value}" ${value === r.status ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </td>
      </tr>
    `;
  }

  function wire() {
    container.querySelector('#status-filter')?.addEventListener('change', (e) => {
      state.statusFilter = e.target.value;
      render();
    });

    container.querySelectorAll('[data-action="set-status"]').forEach((select) => {
      select.addEventListener('change', () => updateReport(select.dataset.reportId, { status: select.value }, select));
    });

    container.querySelectorAll('[data-action="edit-owner"]').forEach((input) => {
      // Save on blur, not every keystroke — same reasoning as every other
      // inline-edit-on-blur field in this app (e.g. ObservationList.js).
      input.addEventListener('blur', () => {
        const report = state.reports.find((r) => r.id === input.dataset.reportId);
        const newOwner = input.value.trim();
        if ((report?.owner || '') === newOwner) return; // nothing actually changed
        updateReport(input.dataset.reportId, { owner: newOwner || null }, input);
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') input.blur(); // commit without needing to click elsewhere
      });
    });
  }

  // Optimistic for the field that was actually edited; reverts + shows an
  // error (via a full render, since the status-sort/filter may need to
  // change anyway) if the save fails.
  async function updateReport(id, patch, fieldEl) {
    const report = state.reports.find((r) => r.id === id);
    const previous = report ? { ...report } : null;
    if (report) Object.assign(report, patch);
    fieldEl.disabled = true;
    try {
      const updated = await bugReportsService.update(id, patch);
      if (report) Object.assign(report, updated);
      // A status change can move this row to the top (not_started) or
      // change whether it matches the current filter — re-render so the
      // table reflects that instead of leaving a stale sort order.
      if ('status' in patch) {
        render();
      } else {
        fieldEl.disabled = false;
      }
    } catch (err) {
      if (report && previous) Object.assign(report, previous);
      state.error = err.message || 'Could not update that report. Try again.';
      render();
    }
  }
}
