// Components/NotificationBell.js — presentational only. A bell-icon button
// with an unread-count badge that opens a dropdown preview of unread
// notifications. The Presenter that mounts it (Home.js) owns fetching,
// open/closed state, and wiring every click below — this just renders
// markup for whatever state it's given.
//
// An inline SVG outline icon, not a bell emoji — this app went through a
// deliberate pass removing emoji ("feels cheap," see git history); a
// monochrome vector icon (inherits color via `currentColor`, same as any
// other icon this app might add later) is a different, intentional choice,
// not a reversal of that.
import { escapeHtml } from './htmlUtils.js';

const MAX_PREVIEW_ROWS = 5;

function bellIcon() {
  return `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="display: block;">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"></path>
      <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
    </svg>
  `;
}

export function renderNotificationBell({ unreadCount = 0, open = false, loading = false, unread = [] } = {}) {
  const hasUnread = unreadCount > 0;
  const label = hasUnread ? `Notifications, ${unreadCount} unread` : 'Notifications';
  return `
    <div style="position: relative;">
      <button
        type="button"
        class="ob-btn ob-btn--ghost"
        data-action="toggle-notifications"
        aria-label="${escapeHtml(label)}"
        aria-haspopup="true"
        aria-expanded="${open}"
        style="position: relative;"
      >
        ${bellIcon()}
        ${hasUnread
          ? `<span
              class="ob-tag ob-tag--info"
              aria-hidden="true"
              style="position: absolute; top: -6px; right: -6px; min-width: 18px; padding: 0 5px; border-radius: 999px; font-size: 0.7rem; line-height: 1.5; text-align: center;"
            >${unreadCount > 99 ? '99+' : unreadCount}</span>`
          : ''}
      </button>
      ${open ? renderDropdown({ loading, unread }) : ''}
    </div>
  `;
}

function renderDropdown({ loading, unread }) {
  return `
    <div
      class="ob-card ob-card--flat"
      data-role="notification-dropdown"
      style="position: absolute; top: 100%; right: 0; margin-top: 4px; width: 320px; max-height: 360px; overflow-y: auto; z-index: var(--ob-z-modal); padding: var(--ob-space-2); background: var(--ob-color-surface); box-shadow: var(--ob-shadow-md);"
    >
      <p class="ob-text-sm" style="margin: 0 0 var(--ob-space-2); font-weight: 600;">Unread</p>
      ${loading
        ? '<p class="ob-text-muted ob-text-sm" style="margin:0;"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Loading…</p>'
        : unread.length === 0
          ? '<p class="ob-text-muted ob-text-sm" style="margin:0;">You’re all caught up.</p>'
          : `
            <ul style="list-style: none; margin: 0; padding: 0;">
              ${unread.slice(0, MAX_PREVIEW_ROWS).map(renderRow).join('')}
            </ul>
            ${unread.length > MAX_PREVIEW_ROWS
              ? `<p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-1) 0 0;">+${unread.length - MAX_PREVIEW_ROWS} more</p>`
              : ''}
          `}
      <button
        type="button"
        class="ob-btn ob-btn--ghost ob-btn--sm"
        data-action="view-all-notifications"
        style="width: 100%; margin-top: var(--ob-space-2);"
      >View all notifications</button>
    </div>
  `;
}

function renderRow(n) {
  const name = n.payload?.common_name || n.payload?.species || 'A pinned species';
  const region = n.payload?.region;
  const body = region
    ? `<strong>${escapeHtml(name)}</strong> reported in ${escapeHtml(region)}`
    : `<strong>${escapeHtml(name)}</strong> reported nearby`;
  return `
    <li
      class="ob-text-sm"
      data-notification-id="${escapeHtml(n.id)}"
      role="button"
      tabindex="0"
      style="padding: var(--ob-space-2); border-radius: var(--ob-radius-sm); background: var(--ob-color-info-bg); margin-bottom: var(--ob-space-1); cursor: pointer;"
    >${body}</li>
  `;
}
