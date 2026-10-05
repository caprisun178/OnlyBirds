// Presenters/NotificationsFeed.js — the notification feed screen. See
// docs/features/pinned-birds.md#match--notify. Reached from the bell on
// Home.js (Components/NotificationBell.js).
//
//   import { mount } from './Presenters/NotificationsFeed.js';
//   mount(document.getElementById('app'), { userId: 'u1' });

import { notificationsService } from '../Services/notifications.js';
import { escapeHtml } from '../Components/htmlUtils.js';

export function mount(container, props = {}) {
  const { onNavigate, userId = 'u1' } = props;

  const state = {
    loading: true,
    error: null,
    notifications: [],
  };

  render();
  load();

  async function load() {
    state.loading = true;
    state.error = null;
    render();
    try {
      state.notifications = await notificationsService.list(userId);
    } catch (err) {
      state.error = err.message || 'Could not load your notifications.';
    } finally {
      state.loading = false;
      render();
    }
  }

  async function markOneRead(id) {
    const target = state.notifications.find((n) => n.id === id);
    if (!target || target.read_at) return;
    // Optimistic — the feed should feel instant on a single tap; a failure
    // just leaves it unread on the next load rather than needing its own
    // error state for one row.
    target.read_at = new Date().toISOString();
    render();
    try {
      await notificationsService.markRead(userId, [id]);
    } catch (err) {
      target.read_at = null;
      render();
    }
  }

  // The row's primary action — opening a notification reads it (same
  // convention as email/chat apps: viewing something marks it read, no
  // separate "mark read" tap needed) and, for a pin_hit (the only kind that
  // points at anything right now), jumps to the map (= 'home' — there's no
  // separate Explore Map route; Home IS the map screen, see preview.js)
  // centered on and showing the detail panel for the exact sighting that
  // triggered it.
  function openNotification(n) {
    markOneRead(n.id);
    if (!onNavigate) return; // standalone preview — nothing to navigate to
    const observationId = n.payload?.observation_id;
    if (observationId) onNavigate('home', { focusObservationId: observationId });
  }

  async function markAllRead() {
    const unread = state.notifications.filter((n) => !n.read_at);
    if (unread.length === 0) return;
    const now = new Date().toISOString();
    unread.forEach((n) => { n.read_at = now; });
    render();
    try {
      await notificationsService.markRead(userId);
    } catch (err) {
      state.error = 'Could not mark everything read. Try again in a moment.';
      render();
    }
  }

  function render() {
    const unreadCount = state.notifications.filter((n) => !n.read_at).length;
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <div class="ob-cluster" style="justify-content: space-between; align-items: center;">
          <h1 style="margin: 0;">Notifications</h1>
          ${unreadCount > 0
            ? `<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="mark-all-read">Mark all read</button>`
            : ''}
        </div>
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? renderLoading() : renderList()}
      </div>
    `;
    if (onNavigate) {
      container.querySelector('[data-action="back-to-home"]')?.addEventListener('click', () => onNavigate('home'));
    }
    container.querySelector('[data-action="mark-all-read"]')?.addEventListener('click', markAllRead);
    wireRows();
  }

  function renderLoading() {
    return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
  }

  function renderList() {
    if (state.notifications.length === 0) {
      return `
        <div class="ob-card ob-text-center">
          <p class="ob-card__body">No notifications yet. Pin a species from your Life List and you'll hear about it here when someone reports one nearby.</p>
        </div>
      `;
    }
    return `
      <ul class="ob-stack" style="--ob-stack-gap: var(--ob-space-2); margin: 0; padding: 0; list-style: none;">
        ${state.notifications.map(renderRow).join('')}
      </ul>
    `;
  }

  function renderRow(n) {
    const isUnread = !n.read_at;
    const hasMapTarget = Boolean(n.payload?.observation_id);
    const dateLabel = n.created_at
      ? new Date(n.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
      : '';
    return `
      <li
        class="ob-card ob-card--flat ob-cluster"
        data-notification-id="${escapeHtml(n.id)}"
        role="button"
        tabindex="0"
        style="justify-content: space-between; align-items: center; cursor: pointer; background: ${isUnread ? 'var(--ob-color-info-bg)' : 'var(--ob-color-surface-alt)'};"
      >
        <div>
          <p class="ob-card__body" style="margin: 0;">${renderBody(n)}</p>
          <p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-1) 0 0;">${escapeHtml(dateLabel)}</p>
        </div>
        ${hasMapTarget ? '<span class="ob-text-muted ob-text-sm" aria-hidden="true">View on map →</span>' : ''}
      </li>
    `;
  }

  function renderBody(n) {
    if (n.kind === 'pin_hit') {
      const name = n.payload?.common_name || n.payload?.species || 'A pinned species';
      const region = n.payload?.region;
      return region
        ? `<strong>${escapeHtml(name)}</strong> was just reported in ${escapeHtml(region)}`
        : `<strong>${escapeHtml(name)}</strong> was just reported nearby`;
    }
    // Forward-compatible fallback for a notification kind this screen
    // doesn't have specific copy for yet (e.g. a future sticker_awarded).
    return escapeHtml(n.kind.replace(/_/g, ' '));
  }

  function wireRows() {
    container.querySelectorAll('[data-notification-id]').forEach((row) => {
      const target = state.notifications.find((n) => n.id === row.dataset.notificationId);
      if (!target) return;
      row.addEventListener('click', () => openNotification(target));
      row.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openNotification(target);
        }
      });
    });
  }
}
