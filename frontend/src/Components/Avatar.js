// Components/Avatar.js — presentational only: no state, no Dao/Service imports.
// Shows the user's photo, or their initials on a colored circle if there
// isn't one yet (avatar_url is null until the user uploads a photo).

import { escapeHtml } from './htmlUtils.js';

function initials(username) {
  if (!username) return '?';
  return username.slice(0, 2).toUpperCase();
}

export function renderAvatar({ username, avatarUrl, size = 'md' }) {
  const dims = { sm: 32, md: 56, lg: 96 }[size] || 56;
  const style = `width:${dims}px;height:${dims}px;border-radius:var(--ob-radius-md, 9999px);`;

  if (avatarUrl) {
    return `<img class="ob-avatar" style="${style} object-fit:cover;" src="${escapeHtml(avatarUrl)}" alt="${escapeHtml(username || '')}'s avatar" />`;
  }

  return `
    <div class="ob-avatar ob-avatar--initials" style="${style} display:flex; align-items:center; justify-content:center; background:var(--ob-color-brand, #3aa0ff); color:white; font-weight:var(--ob-weight-bold, 600);" aria-hidden="true">
      ${escapeHtml(initials(username))}
    </div>
  `;
}