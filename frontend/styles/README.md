# Styling standard

`base.css` is the one shared stylesheet. Every page and every reusable markup
block builds on it. It is plain CSS — **no build step, no framework.**

## Use it

Link it in every HTML page, **before** the page's own stylesheet:

```html
<!-- frontend/<page>/index.html -->
<link rel="stylesheet" href="../styles/base.css" />
<link rel="stylesheet" href="styles.css" />   <!-- this page's extras, optional -->
```

Then write markup with the `.ob-*` classes below. Don't add a second global
stylesheet or a CSS framework — this is the standard.

## Folder structure

```text
frontend/
  styles/
    base.css        design tokens + shared .ob-* classes  (this folder)
    README.md
  shared/           reusable markup blocks, copied or included into pages
    header.html
    footer.html
    species-card.html
    species-card.css   layout-only CSS for that block (tokens only)
  home/             one page = one folder
    index.html
    styles.css      page-only tweaks on top of base.css
    assets/         images for this page
  <page>/
    index.html
    styles.css
```

Rules:

1. **Tokens, not values.** Every colour, space, radius, and shadow is a
   `--ob-*` CSS variable defined at the top of `base.css`. In any CSS you write,
   use `var(--ob-space-4)`, never `16px`; `var(--ob-color-brand)`, never
   `#3aa0ff`. Need a value that doesn't exist? Add a token to `base.css` so
   everyone gets it.
2. **Class naming** — prefix `ob-`, BEM-style:
   | Kind | Pattern | Example |
   |---|---|---|
   | block | `.ob-<name>` | `.ob-card` |
   | element (part of a block) | `.ob-<name>__<part>` | `.ob-card__title` |
   | variant | `.ob-<name>--<variant>` | `.ob-btn--primary` |
3. A reusable block gets **at most one class of its own**, for layout
   (`.ob-species-card`), in its own small CSS file next to the markup. Anything
   visual — buttons, tags, inputs — reuses the shared `.ob-*` classes.
4. **Never** restyle an `.ob-*` class to get a one-off. Add a variant to
   `base.css` instead, so it's shared.
5. A page's `styles.css` is for that page's layout only (hero spacing, a grid).
   It must not redefine `.ob-*` classes.

## Class catalogue

| Class | Use | Variants / knobs |
|---|---|---|
| `.ob-container` | centered page column (max 1060px) | — |
| `.ob-stack` | vertical list with even gaps | set `--ob-stack-gap` |
| `.ob-cluster` | horizontal group that wraps | set `--ob-cluster-gap` |
| `.ob-grid` | responsive card grid | set `--ob-grid-min` (default 270px) |
| `.ob-skip-link` | keyboard skip-to-content link | — |
| `.ob-btn` | button or link styled as a button | `--primary` `--ghost` `--subtle`; `--sm` `--lg` `--block` |
| `.ob-card` | surface panel | `--flat` `--interactive`; parts `__title` `__body` |
| `.ob-tag` | small status pill | `--info` `--progress` `--success` `--warning` `--danger` |
| `.ob-badge` | round count bubble (e.g. unread) | — |
| `.ob-field` | label + control wrapper | `--error`; parts `.ob-label` `.ob-input` `.ob-select` `.ob-textarea` `.ob-hint` |
| `.ob-alert` | inline message | `--success` `--warning` `--danger` |
| `.ob-spinner` | loading indicator | — |
| `.ob-visually-hidden` | screen-reader-only text | — |
| `.ob-text-muted` / `.ob-text-center` / `.ob-text-sm` | tiny text utilities | — |

Token groups (top of `base.css`): `--ob-space-1..8`, `--ob-radius-*`,
`--ob-shadow-sm|md|lg`, `--ob-text-xs..3xl`, `--ob-weight-*`, and the semantic
`--ob-color-*` names — always use those, not the raw `--ob-blue-500` scale.

## Example — a reusable block

```html
<!-- frontend/shared/species-card.html -->
<article class="ob-card ob-card--interactive ob-species-card">
  <img class="ob-species-card__photo" src="" alt="" />
  <h3 class="ob-card__title">Barn Owl</h3>
  <span class="ob-tag ob-tag--success">On your list</span>
  <button class="ob-btn ob-btn--subtle ob-btn--sm" type="button">Pin</button>
</article>
```

```css
/* frontend/shared/species-card.css — layout only, tokens only */
.ob-species-card { display: flex; flex-direction: column; gap: var(--ob-space-3); }
.ob-species-card__photo {
  border-radius: var(--ob-radius-md);
  aspect-ratio: 4 / 3;
  object-fit: cover;
}
```

A page that uses the block links both the block's CSS and `base.css`:

```html
<link rel="stylesheet" href="../styles/base.css" />
<link rel="stylesheet" href="../shared/species-card.css" />
```

## Dark mode

`base.css` ships a dark palette that follows the OS setting automatically. A
future theme toggle just sets `document.documentElement.dataset.theme` to
`"dark"` or `"light"`. Because markup only uses `--ob-color-*` tokens, it
adapts for free — don't write per-theme rules in a page or block.

## The landing page

`frontend/home/` currently has a self-contained `styles.css` so it can deploy on
its own. It follows the same visual language. When convenient, switch it to
`<link href="../styles/base.css">` + a trimmed page `styles.css` so there's one
source of truth.
