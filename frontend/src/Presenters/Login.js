// Presenters/Login.js — "Sign in with Google." See docs/features/user-profiles.md#auth.
//
//  import { mount } from './Presenters/Login.js';
//    mount(document.getElementById('app'), { onNavigate, next: 'life-list' });
//
// `next` (+ `nextParams`) is where to go after signing in — preview.js sets
// it when a signed-out user tries to open a user-only screen; otherwise Home.

import { authService } from '../Services/auth.js';
import { escapeHtml } from '../Components/htmlUtils.js';

export function mount(container, props = {}) {
  const {
    onNavigate = (route) => console.log('navigate to:', route),
    next = 'home',
    nextParams,
  } = props;

  const state = { loading: true, signingIn: false, error: null, notConfigured: false };

  render();
  load();

  async function load() {
    try {
      const clientId = await authService.getGoogleClientId();
      if (!clientId) {
        state.notConfigured = true;
        return;
      }
      state.loading = false;
      render();
      await authService.renderGoogleButton(
        container.querySelector('[data-role="google-button"]'),
        clientId,
        handleCredential,
      );
    } catch (err) {
      state.error = err.message || 'Could not load sign-in.';
    } finally {
      state.loading = false;
      if (state.notConfigured || state.error) render();
    }
  }

  async function handleCredential(credential) {
    state.signingIn = true;
    state.error = null;
    renderStatus();
    try {
      await authService.signInWithGoogle(credential);
      onNavigate(next, nextParams);
    } catch (err) {
      state.signingIn = false;
      state.error = err.message || 'Sign-in failed. Please try again.';
      renderStatus();
    }
  }

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack" style="max-width: 28rem;">
        <div>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back">← Back to map</button>
        </div>
        <div class="ob-card ob-stack ob-text-center">
          <h1 style="margin:0;">Sign in</h1>
          <p class="ob-text-muted" style="margin:0;">
            Sign in to log sightings and keep your life list, pins, and stickers.
          </p>
          ${renderBody()}
          <div data-role="status"></div>
        </div>
      </div>
    `;
    container.querySelector('[data-action="back"]').addEventListener('click', () => onNavigate('home'));
    renderStatus();
  }

  function renderBody() {
    if (state.loading) return '<div class="ob-spinner" style="margin-inline:auto"></div>';
    if (state.notConfigured) {
      return `<div class="ob-alert ob-alert--warning">
        Sign-in isn't set up on this server yet (GOOGLE_CLIENT_ID / SESSION_SECRET).
      </div>`;
    }
    // Google renders its own button into this element.
    return '<div data-role="google-button" style="display:flex; justify-content:center;"></div>';
  }

  // Status/error only — re-rendering the whole screen would wipe the
  // Google button Google drew into the page.
  function renderStatus() {
    const el = container.querySelector('[data-role="status"]');
    if (!el) return;
    el.innerHTML = state.signingIn
      ? '<p class="ob-text-muted ob-text-sm" style="margin:0;">Signing you in…</p>'
      : state.error
        ? `<div class="ob-alert ob-alert--danger ob-text-sm">${escapeHtml(state.error)}</div>`
        : '';
  }
}
