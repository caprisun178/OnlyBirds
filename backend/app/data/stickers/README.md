# Sticker art

One image per sticker in the catalog, named by the sticker `code` from
[docs/features/stickers.md](../../../../docs/features/stickers.md):

```
first_bird.svg
first_owl.svg
first_eagle.svg
all_eagles.svg
species_100.svg
...
```

- Prefer **SVG**. If raster, use PNG at 512×512 with transparency.
- The backend serves this folder as static files at `/static/stickers/<code>.svg`.
- The seed script sets `stickers.image_url = '/static/stickers/<code>.svg'` for
  each row. A locked sticker is the same image shown greyed out by the client
  (`Components/Sticker`), so no separate "locked" art is needed.
- Add the art in the same PR that adds the sticker to the catalog fixture, so
  the catalog and its images stay in sync.

Move to a Supabase Storage bucket only if this set grows large or non-developers
need to upload art without opening a PR.
