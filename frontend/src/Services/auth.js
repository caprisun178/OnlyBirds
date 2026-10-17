// Services/auth.js — who's signed in. See docs/features/user-profiles.md#auth.
//
// Sign in with Google: the Login screen's Google button produces an ID
// token, which signInWithGoogle() trades for our own session token (POST
// /auth/google). That session is kept in localStorage so a reload stays
// signed in, and handed to apiClient so every request carries it. The
// backend rejects any user-scoped request that doesn't match it, so this is
// the one place screens should ask "who is the current user" — never pass a
// hardcoded id.
//
// Signed out, getCurrentUserId() is null: screens hide/disable anything
// user-based, and preview.js sends signed-out visits to user-only screens to
// the Login screen.

import { setAuthToken, setOnUnauthorized } from '../Dao/apiClient.js';
import { authDAO } from '../Dao/auth.js';
import { googleIdentity } from '../Dao/googleIdentity.js';

const STORAGE_KEY = 'ob-session';
const listeners = new Set();

let session = restore(); // { token, expiresAt, userId, name, isAdmin } | null
setAuthToken(session?.token);
// A 401 on a request that carried our token means the session is no longer
// valid server-side (expired, or SESSION_SECRET rotated) — sign out locally.
setOnUnauthorized(() => signOut());

function restore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const saved = raw ? JSON.parse(raw) : null;
    if (!saved?.token || !saved?.userId) return null;
    if (saved.expiresAt && new Date(saved.expiresAt) <= new Date()) return null;
    return saved;
  } catch {
    return null; // storage blocked or corrupt — just start signed out
  }
}

function persist() {
  try {
    if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage blocked (private mode etc.) — still signed in for this page load.
  }
}

function setSession(next) {
  session = next;
  setAuthToken(session?.token);
  persist();
  listeners.forEach((fn) => fn(session));
}

export function getCurrentUserId() {
  return session?.userId ?? null;
}

export function isSignedIn() {
  return session !== null;
}

// Google's display name — for greeting a user who hasn't picked a username.
export function getDisplayName() {
  return session?.name ?? null;
}

// Whether to show admin screens (ADMIN_EMAILS on the server). Display only:
// the backend re-checks on every admin request.
export function isAdmin() {
  return session?.isAdmin === true;
}

// Subscribe to sign-in / sign-out. Returns an unsubscribe function.
export function onAuthChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const authService = {
  // Null when the server has no GOOGLE_CLIENT_ID / SESSION_SECRET set.
  async getGoogleClientId() {
    const config = await authDAO.getConfig();
    return config.google_client_id || null;
  },

  renderGoogleButton(element, clientId, onCredential) {
    return googleIdentity.renderButton(element, clientId, onCredential);
  },

  async signInWithGoogle(credential) {
    const result = await authDAO.signInWithGoogle(credential);
    setSession({
      token: result.token,
      expiresAt: result.expires_at,
      userId: result.profile.id,
      name: result.name || null,
      isAdmin: result.is_admin === true,
    });
    return result.profile;
  },

  // Re-reads admin status from the server (GET /auth/me) — called once at
  // startup so a saved session picks up ADMIN_EMAILS changes without
  // signing out and back in. Listeners only hear about it if it changed.
  async refresh() {
    if (!session) return;
    try {
      const me = await authDAO.me();
      const nextIsAdmin = me.is_admin === true;
      if (session && nextIsAdmin !== isAdmin()) setSession({ ...session, isAdmin: nextIsAdmin });
    } catch {
      // A 401 already signed us out via apiClient; anything else (offline,
      // server asleep) just keeps the saved value.
    }
  },

  signOut,
};

function signOut() {
  if (!session) return;
  googleIdentity.disableAutoSelect();
  setSession(null);
}
