# Sticker art

One image per illustrated sticker in the catalog from
[docs/features/stickers.md](../../../../docs/features/stickers.md). Use the
sticker `code` as the filename, with its actual file extension:

```
first_bird.png
night_owl.png
eagle_eye.png
...
```

- Prefer **SVG**. If raster, use PNG at 512×512 with transparency.
- The backend serves this folder as static files at `/static/stickers/<filename>`.
- Set the matching catalog entry's `image_url` in `backend/app/data/stickers.json`
  to `/static/stickers/<filename>`. A locked sticker is the same image shown
  greyed out by the client (`Components/StickerCard`), so no separate "locked"
  art is needed.
- Add the art in the same PR that adds the sticker to the catalog fixture, so
  the catalog and its images stay in sync.

Move to a Supabase Storage bucket only if this set grows large or non-developers
need to upload art without opening a PR.
