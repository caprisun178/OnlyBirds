// dao/googleIdentity.js — Google Identity Services ("Sign in with Google").
// Loads Google's script on demand and renders its button; the button hands
// back an ID token (`credential`), which Services/auth.js trades for our own
// session via POST /auth/google. No build step, so the script is injected
// here rather than bundled.
// Docs: https://developers.google.com/identity/gsi/web/guides/display-button

const SCRIPT_URL = 'https://accounts.google.com/gsi/client';
let scriptPromise = null;

function loadScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        scriptPromise = null; // let a later attempt retry
        reject(new Error('Could not load Google sign-in. Check your connection and try again.'));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

export const googleIdentity = {
  async renderButton(element, clientId, onCredential) {
    await loadScript();
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response) => onCredential(response.credential),
    });
    window.google.accounts.id.renderButton(element, { theme: 'outline', size: 'large', text: 'signin_with' });
  },

  // Stops Google auto-selecting this account next time, so "Sign out" then
  // "Sign in" lets the user pick a different one.
  disableAutoSelect() {
    window.google?.accounts?.id?.disableAutoSelect();
  },
};
