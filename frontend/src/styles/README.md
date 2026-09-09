# Styling standard

`base.css` is the one stylesheet every screen and reusable block builds on.
Plain CSS, no build step. Link it in each HTML page **before** the page's own
stylesheet:

```html
<link rel="stylesheet" href="/src/styles/base.css" />
<link rel="stylesheet" href="page.css" />        <!-- this page's extras, optional -->
```

(If a bundler is added later, `import './styles/base.css'` once at the entry
point does the same thing.)

Then write markup with the `.ob-*` classes below. **Do not** add a second global
stylesheet or a CSS framework — this is the standard.

## The rules

1. **Tokens, not values.** Every colour, space, radius, and shadow is a
   `--ob-*` CSS variable. In component CSS, write `var(--ob-space-4)`, never
   `16px`; `var(--ob-color-brand)`, never `#3aa0ff`. New value needed? Add a
   token to `base.css` so everyone gets it.
2. **Class naming** — prefix `ob-`, BEM-style:
   | Kind | Pattern | Example |
   |---|---|---|
   | block | `.ob-<name>` | `.ob-card` |
   | element (part of a block) | `.ob-<name>__<part>` | `.ob-card__title` |
   | variant | `.ob-<name>--<variant>` | `.ob-btn--primary` |
3. **A component gets at most one class of its own**, for layout only
   (`.ob-species-card`), and it still uses tokens inside. Everything visual
   (buttons, tags, inputs) reuses the shared classes.
4. **Never** restyle an `.ob-*` class inside a component to get a one-off. Add a
   variant to `base.css` instead.
5. Reusable blocks stay presentational — markup + these classes, no data
   fetching (see [Contributing](../../../docs/contributing.md)).

## Class catalogue

| Class | Use | Variants / knobs |
|---|---|---|
| `.ob-container` | centered page column (max 1060px) | — |
| `.ob-stack` | vertical list with even gaps | set `--ob-stack-gap` |
| `.ob-cluster` | horizontal group that wraps | set `--ob-cluster-gap` |
| `.ob-grid` | responsive card grid | set `--ob-grid-min` (default 270px) |
| `.ob-skip-link` | keyboard skip-to-content link | — |
| `.ob-btn` | button / link-as-button | `--primary` `--ghost` `--subtle`, `--sm` `--lg` `--block` |
| `.ob-card` | surface panel | `--flat` `--interactive`; parts `__title` `__body` |
| `.ob-tag` | small status pill | `--info` `--progress` `--success` `--warning` `--danger` |
| `.ob-badge` | round count bubble (e.g. unread) | — |
| `.ob-field` | label + control wrapper | `--error`; parts `.ob-label` `.ob-input` `.ob-select` `.ob-textarea` `.ob-hint` |
| `.ob-alert` | inline message | `--success` `--warning` `--danger` |
| `.ob-spinner` | loading indicator | — |
| `.ob-visually-hidden` | screen-reader-only text | — |
| `.ob-text-muted` / `.ob-text-center` / `.ob-text-sm` | tiny text utilities | — |

Token groups (see the top of `base.css`): `--ob-space-1..8`, `--ob-radius-*`,
`--ob-shadow-sm|md|lg`, `--ob-text-xs..3xl`, `--ob-weight-*`, `--ob-color-*`
(always use the **semantic** `--ob-color-…` names, not the raw `--ob-blue-500`
scale).

## Example — a reusable block

```html
<!-- Components/species-card.html -->
<article class="ob-card ob-card--interactive ob-species-card">
  <img class="ob-species-card__photo" src="" alt="" />
  <h3 class="ob-card__title">Barn Owl</h3>
  <span class="ob-tag ob-tag--success">On your list</span>
  <button class="ob-btn ob-btn--subtle ob-btn--sm" type="button">Pin</button>
</article>
```

```css
/* Components/species-card.css — layout only, tokens only */
.ob-species-card { display: flex; flex-direction: column; gap: var(--ob-space-3); }
.ob-species-card__photo {
  border-radius: var(--ob-radius-md);
  aspect-ratio: 4 / 3;
  object-fit: cover;
}
```

## Dark mode

`base.css` ships a dark palette that follows the OS setting automatically. A
future toggle just sets `document.documentElement.dataset.theme` to `"dark"` or
`"light"`. Because markup only uses `--ob-color-*` tokens, it adapts for free —
don't write per-theme rules in a page or block.

## Relationship to the landing page

`frontend/home/` (the marketing page) has its own `styles.css` and is
deliberately standalone so it can deploy on its own. It follows the same visual
language. If it ever moves into the app, it adopts `base.css` like everything
else.
