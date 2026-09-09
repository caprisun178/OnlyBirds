# Landing page

The public marketing page for Only Birds. Plain HTML + CSS, **no build step** —
this is separate from the React app that will live in `frontend/src/`.

## Preview it

Just open `index.html` in a browser. Or serve the folder so links behave like
production:

```bash
cd frontend/home
python -m http.server 4173
# visit http://localhost:4173
```

## Editing

- `index.html` — the content and structure. Loads the **Fredoka** font from
  Google Fonts via a `<link>`; if that's blocked/offline it falls back to the
  system font stack, no breakage.
- `styles.css` — all styling. The design tokens (colours, radius, shadows,
  fonts) are the `--variables` at the top of the file; change those to re-skin
  without touching the rest. The floating `.bubble` elements are decorative and
  respect `prefers-reduced-motion`.
- Feature cards live in the `<ul class="feature-grid">` in `index.html`. The
  `tag` / `tag-partial` class sets the "Planned" / "In progress" pill; keep it
  in sync with the status column in [`docs/features/overview.md`](../../docs/features/overview.md).

## Deploying

Point Vercel / Netlify / GitHub Pages at this folder (`frontend/home`) as the
publish directory. No framework preset needed — it is static files.
