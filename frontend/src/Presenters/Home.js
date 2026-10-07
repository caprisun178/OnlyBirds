// frontend/src/Presenters/Home.js
// The app's landing screen: a header with quick links (Life List, Add
// Observation, Login) and Explore Map embedded directly below it, so you
// can start filtering sightings the moment the app loads — no separate
// welcome page to click through first. No router yet, so navigation goes
// through an optional onNavigate callback (it just logs for now). Auth/
// login is separate in-progress work — the header's Login button has
// nowhere to go yet, so it hits the same "no screen yet" fallback every
// other not-yet-built route already does.
//
// Deliberately no `ob-container` here (unlike AddObservation/LifeList/
// ObservationList, which each opt into it on their own top-level element) —
// a map screen wants the full viewport width, not a narrow centered reading
// column with large empty margins on a wide screen. `#app` itself carries
// no side padding either (see preview.html), so this provides its own — a
// literal 0.5in (not a `--ob-space-*` token) so it stays exactly that
// regardless of any future change to the spacing scale.

import { mount as mountExploreMap } from './ExploreMap.js';
import { renderNotificationBell } from '../Components/NotificationBell.js';
import { notificationsService } from '../Services/notifications.js';

export function mount(container, props = {}) {
  const { onNavigate = (route) => console.log('navigate to:', route), userId = 'u1' } = props;

  // The bell's own little piece of state — open/closed, its preview list,
  // and the badge count. Kept separate from the rest of this screen (which
  // has none) so updating it only ever touches its own `[data-role]` span,
  // never a full re-render that would also remount ExploreMap's live
  // Leaflet instance for no reason.
  const bell = { open: false, loading: false, unreadCount: 0, unread: [] };
  let outsideClickListener = null;

  container.innerHTML = `
    <div class="ob-stack" style="padding-inline: 0.5in;">
      <header class="ob-cluster" style="justify-content: space-between; align-items: center;">
        <h1 style="margin: 0;">Only Birds</h1>
        <nav class="ob-cluster" aria-label="Main">
          <button type="button" class="ob-btn ob-btn--ghost" data-route="life-list">Life List</button>
          <button type="button" class="ob-btn ob-btn--ghost" data-route="add-observation">Add Observation</button>
          <button type="button" class="ob-btn ob-btn--ghost" data-route="plan-a-trip">Plan a Trip</button>
          <button type="button" class="ob-btn ob-btn--ghost" data-route="test-your-skill">Test Your Skill</button>
          <button type="button" class="ob-btn ob-btn--ghost" data-route="admin-bug-backlog">Bug Backlog</button>
          <span data-role="notification-bell">${renderNotificationBell(bell)}</span>
          <button type="button" class="ob-btn ob-btn--primary" data-route="login">Log in</button>
        </nav>
      </header>
      <div data-role="explore-map"></div>
    </div>
  `;

  container.querySelectorAll('[data-route]').forEach((el) => {
    el.addEventListener('click', () => {
      // Navigating away via any of these tears down this whole screen
      // (preview.js's router clears #app and mounts the next one) — if the
      // dropdown's document-level listeners (closeDropdown() below) were
      // left attached, they'd leak: Home.js remounts fresh every time you
      // navigate back here, so a stray pair would pile up per round trip.
      closeDropdown();
      onNavigate(el.dataset.route);
    });
  });
  wireBell();

  mountExploreMap(container.querySelector('[data-role="explore-map"]'), { ...props, onNavigate, embedded: true });

  // Fetched after the initial render (not blocking it) — see the `bell`
  // comment above for why this only ever patches its own span.
  loadUnreadCount();

  function updateBellDom() {
    const bellSpan = container.querySelector('[data-role="notification-bell"]');
    if (!bellSpan) return;
    bellSpan.innerHTML = renderNotificationBell(bell);
    wireBell();
  }

  function wireBell() {
    const bellSpan = container.querySelector('[data-role="notification-bell"]');
    bellSpan?.querySelector('[data-action="toggle-notifications"]')?.addEventListener('click', (e) => {
      e.stopPropagation(); // don't immediately re-trigger the outside-click closer below
      toggleDropdown();
    });
    bellSpan?.querySelector('[data-action="view-all-notifications"]')?.addEventListener('click', () => {
      closeDropdown();
      onNavigate('notifications', { userId });
    });
    bellSpan?.querySelectorAll('[data-notification-id]').forEach((row) => {
      const open = () => openNotification(row.dataset.notificationId);
      row.addEventListener('click', open);
      row.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      });
    });
  }

  function toggleDropdown() {
    if (bell.open) {
      closeDropdown();
      return;
    }
    bell.open = true;
    updateBellDom();
    loadUnreadList();

    // Attached only while open, torn down on close — same reasoning as the
    // lightbox's document-level Escape listener elsewhere in this app
    // (ExploreMap.js): nothing should accumulate on `document` for the
    // lifetime of a screen that gets fully remounted on every navigation.
    outsideClickListener = (e) => {
      if (!container.querySelector('[data-role="notification-bell"]')?.contains(e.target)) closeDropdown();
    };
    document.addEventListener('click', outsideClickListener);
    document.addEventListener('keydown', handleDropdownKeydown);
  }

  function closeDropdown() {
    bell.open = false;
    if (outsideClickListener) {
      document.removeEventListener('click', outsideClickListener);
      outsideClickListener = null;
    }
    document.removeEventListener('keydown', handleDropdownKeydown);
    updateBellDom();
  }

  function handleDropdownKeydown(e) {
    if (e.key === 'Escape') closeDropdown();
  }

  async function loadUnreadList() {
    bell.loading = true;
    updateBellDom();
    try {
      bell.unread = await notificationsService.list(userId, true);
      bell.unreadCount = bell.unread.length;
    } catch (err) {
      // Leave whatever was there before (likely nothing) — the dropdown's
      // own "you're all caught up" / loading states cover this well enough
      // without a dedicated error message for a preview list.
    } finally {
      bell.loading = false;
      updateBellDom();
    }
  }

  // Opening a preview row reads it (same convention as the full feed screen
  // — see NotificationsFeed.js#openNotification) and, for a pin_hit, jumps
  // to the map (= 'home' — there's no separate Explore Map route; Home IS
  // the map screen, see preview.js) centered on the exact sighting that
  // triggered it.
  function openNotification(id) {
    const target = bell.unread.find((n) => n.id === id);
    if (!target) return;
    markRowRead(id);
    const observationId = target.payload?.observation_id;
    if (observationId) {
      closeDropdown();
      onNavigate('home', { focusObservationId: observationId });
    }
  }

  async function markRowRead(id) {
    const wasUnread = bell.unread.some((n) => n.id === id);
    if (!wasUnread) return;
    // Optimistic — a tap should feel instant; on failure this just stays
    // marked read locally until the next full list load corrects it,
    // rather than needing its own error state for one row in a preview.
    bell.unread = bell.unread.filter((n) => n.id !== id);
    bell.unreadCount = bell.unread.length;
    updateBellDom();
    try {
      await notificationsService.markRead(userId, [id]);
    } catch (err) {
      // See comment above.
    }
  }

  async function loadUnreadCount() {
    try {
      bell.unreadCount = await notificationsService.unreadCount(userId);
      updateBellDom();
    } catch (err) {
      // Leave the bell at its default (unread count 0) — not worth an
      // error state for a badge.
    }
  }
}
