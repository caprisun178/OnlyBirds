# Building a screen

Use the class names below when you write markup. **The actual look — colours,
spacing, polish — is set later in `frontend/styles/base.css`.** Don't hand-style
now; just pick the right class so everything stays consistent when we do the
visual pass.

## The layers

| Layer | Folder | Job |
|---|---|---|
| DAO | `frontend/src/Dao/` | call our API, return raw JSON |
| Service | `frontend/src/Services/` | shape that JSON into what the screen needs |
| Presenter | `frontend/src/Presenters/` | one per screen — call a service, render, wire events |
| Component | `frontend/src/Components/` | reusable chunk of markup; no data, no state |

`Components/` never import from `Dao/` or `Services/` — only `Presenters/` do.

## Class names

### Layout

| Class | For |
|---|---|
| `ob-container` | centered page column |
| `ob-stack` | vertical list, even gaps |
| `ob-cluster` | horizontal row that wraps |
| `ob-grid` | responsive card grid |
| `ob-skip-link` | skip-to-content link (first element on the page) |

### Content

| Class | For |
|---|---|
| `ob-card` | a panel or tile — parts: `ob-card__title`, `ob-card__body`; add `ob-card--interactive` |
| `ob-btn` | button / link-as-button — `ob-btn--primary`, `ob-btn--ghost`, `ob-btn--subtle`, sizes `ob-btn--sm` / `ob-btn--lg` |
| `ob-tag` | status label — `ob-tag--info`, `ob-tag--progress`, `ob-tag--success`, `ob-tag--warning`, `ob-tag--danger` |
| `ob-badge` | small count bubble |
| `ob-field` | form control wrapper — with `ob-label`, `ob-input` / `ob-select` / `ob-textarea`, `ob-hint`; add `ob-field--error` |

### The three states every screen needs

| Class | For |
|---|---|
| `ob-spinner` | loading |
| `ob-alert` | a message — `ob-alert--success`, `ob-alert--warning`, `ob-alert--danger` |
| `ob-card` | empty state: a card with a short line and a button |

### Text helpers

`ob-text-muted`, `ob-text-center`, `ob-text-sm`, `ob-visually-hidden`.

## Example markup

```html
<article class="ob-card ob-card--interactive">
  <h3 class="ob-card__title">Barn Owl</h3>
  <span class="ob-tag ob-tag--success">On your list</span>
  <p class="ob-card__body ob-text-sm">Tyto alba</p>
</article>
```

## Rules

- Use these class names as-is. Don't add your own colours or spacing yet.
- If a screen needs something not in the list, note it in your PR — we add it to
  `base.css` so everyone shares it.

Full list and any updates: `frontend/styles/README.md`.
