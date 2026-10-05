// Components/ReportButton.js — a floating "Report a problem" button, present
// on every screen for the beta. Mounted once, directly to <body> (not inside
// `#app`), by preview.js — `#app` gets torn down and rebuilt on every
// navigate() (see preview.js), which would kill a per-screen button on every
// route change; living outside it means zero wiring per screen and nothing
// to add when a new screen is built.
//
// This is scaffolding for the beta, not a permanent feature — to remove it
// after beta testing wraps, delete the `mountReportButton()` call in
// preview.js and this file. No backend change needed to pull it: POST
// /feedback simply stops being called.
//
// Self-contained: owns its own open/closed + sending state, renders into a
// container it creates itself, and re-renders by replacing that container's
// innerHTML (same targeted-update pattern as NotificationBell's dropdown).
import { escapeHtml } from './htmlUtils.js';
import { feedbackService } from '../Services/feedback.js';

export function mount({ userId = 'u1' } = {}) {
  const el = document.createElement('div');
  el.setAttribute('data-role', 'report-widget');
  el.style.cssText = 'position: fixed; right: var(--ob-space-3); bottom: var(--ob-space-3); z-index: var(--ob-z-modal);';
  document.body.appendChild(el);

  const state = { open: false, screen: 'home', message: '', status: 'idle', error: null };

  render();

  return {
    // preview.js's navigate() calls this on every route change, so a report
    // sent from any screen says which one without the reporter typing it.
    setScreen(screen) {
      state.screen = screen;
    },
  };

  function render() {
    el.innerHTML = state.open ? panel() : trigger();
    wire();
  }

  function trigger() {
    return `
      <button type="button" class="ob-btn ob-btn--sm" data-action="open-report" style="box-shadow: var(--ob-shadow-md);">
        Report a problem
      </button>
    `;
  }

  function panel() {
    const sending = state.status === 'sending';
    const sent = state.status === 'sent';
    return `
      <div class="ob-card ob-stack" style="width: 300px; box-shadow: var(--ob-shadow-md);">
        ${sent
          ? `<p class="ob-text-sm" style="margin:0;">Thanks — sent.</p>`
          : `
            <div class="ob-field">
              <label class="ob-label" for="report-message">What's off?</label>
              <textarea id="report-message" class="ob-textarea" rows="4" placeholder="What happened, and what did you expect instead?">${escapeHtml(state.message)}</textarea>
            </div>
            ${state.error ? `<div class="ob-alert ob-alert--danger ob-text-sm">${escapeHtml(state.error)}</div>` : ''}
            <div class="ob-cluster" style="justify-content: flex-end;">
              <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="cancel-report" ${sending ? 'disabled' : ''}>Cancel</button>
              <button type="button" class="ob-btn ob-btn--primary ob-btn--sm" data-action="send-report" ${sending ? 'disabled' : ''}>${sending ? 'Sending…' : 'Send'}</button>
            </div>
          `}
      </div>
    `;
  }

  function wire() {
    el.querySelector('[data-action="open-report"]')?.addEventListener('click', () => {
      state.open = true;
      state.status = 'idle';
      state.error = null;
      render();
      el.querySelector('#report-message')?.focus();
    });
    el.querySelector('[data-action="cancel-report"]')?.addEventListener('click', () => {
      state.open = false;
      render();
    });
    el.querySelector('#report-message')?.addEventListener('input', (e) => {
      state.message = e.target.value;
    });
    el.querySelector('[data-action="send-report"]')?.addEventListener('click', send);
  }

  async function send() {
    const message = state.message.trim();
    if (!message) {
      state.error = "Describe what's off before sending.";
      render();
      return;
    }
    state.status = 'sending';
    state.error = null;
    render();
    try {
      await feedbackService.sendReport({ message, screen: state.screen, userId });
      state.status = 'sent';
      state.message = '';
      render();
      setTimeout(() => {
        state.open = false;
        state.status = 'idle';
        render();
      }, 2000);
    } catch (err) {
      state.status = 'idle';
      state.error = err.message || 'Could not send that — try again.';
      render();
    }
  }
}
