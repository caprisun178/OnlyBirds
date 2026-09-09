# Landing page assets

Brand images for the public landing page. Keep this folder self-contained so
`frontend/home/` can be deployed on its own.

- `logo.svg` — the mark used in the header and footer (currently an emoji
  placeholder in `index.html`).
- `wordmark.svg` — "Only Birds" set as type, if/when we have one.
- `favicon.svg` / `favicon.png` — browser tab icon.
- `og-image.png` — 1200×630 social preview (referenced from a `<meta property="og:image">` tag).

Prefer **SVG** for the logo and wordmark. Use PNG only for photos or as a
fallback. Optimise before committing (e.g. https://squoosh.app).

Reference them from `index.html` with a relative path, e.g.
`<img src="assets/logo.svg" alt="Only Birds" width="28" height="28" />`.
