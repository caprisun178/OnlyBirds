# Building a screen

## Preview your screen

No framework, no build step — a Presenter is a plain JS module the browser
loads directly. There's no router or nav yet, so `frontend/src/preview.js` is
the one dev-only mount point; you point it at whichever screen you're
building.

Serve `frontend/` (not `frontend/src/` — paths below are root-relative):

```bash
cd frontend
python -m http.server 4174
```

Open <http://localhost:4174/src/preview.html>. Then edit
`frontend/src/preview.js` to import and mount your Presenter instead of the
placeholder:

```js
import { mount } from './Presenters/LifeList.js';

mount(document.getElementById('app'), { userId: 'u1' });
```

A Presenter exports `mount(container, props)`, which renders into `container`
(e.g. `container.innerHTML = ...`) and wires up its own event listeners — no
build step means no JSX, so markup is built with template strings or the DOM
API, using the [class names below](#class-names).

There's no live-reload; refresh the page after saving. The page talks to the
backend at `http://localhost:8000` by default (already allowed in
`CORS_ORIGINS`) — start it too, see [Environment Setup](index.md#3-back-end-setup).

Don't commit your `preview.js` changes as part of a feature PR — revert it to
the placeholder first.

## The layers

| Layer | Folder | Job |
|---|---|---|
| DAO | `frontend/src/Dao/` | call our API, return raw JSON |
| Service | `frontend/src/Services/` | shape that JSON into what the screen needs |
| Presenter | `frontend/src/Presenters/` | one per screen — call a service, render, wire events |
| Component | `frontend/src/Components/` | reusable chunk of markup; no data, no state |

`Components/` never import from `Dao/` or `Services/` — only `Presenters/` do.

## Class names

Use the class names below when you write markup. **The actual look — colours,
spacing, polish — is set later in `frontend/styles/base.css`.** Don't hand-style
now; just pick the right class so everything stays consistent when we do the
visual pass.

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
