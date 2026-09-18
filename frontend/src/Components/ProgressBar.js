// Components/ProgressBar.js — presentational only. "seen / total" + a bar.
export function renderProgressBar(seen, total) {
  const pct = total > 0 ? Math.round((seen / total) * 100) : 0;
  return `
    <div class="ob-stack" style="--ob-stack-gap: var(--ob-space-2);">
      <div class="ob-cluster" style="justify-content: space-between;">
        <strong>${seen} / ${total} species</strong>
        <span class="ob-text-muted ob-text-sm">${pct}%</span>
      </div>
      <div style="height:10px;border-radius:var(--ob-radius-pill);background:var(--ob-color-surface-alt);overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:var(--ob-color-brand);border-radius:var(--ob-radius-pill);"></div>
      </div>
    </div>
  `;
}
