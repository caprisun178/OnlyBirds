"""Pre-warm the species-photo cache for a set of common species, so the
*first* lookup for any of them is already instant instead of waiting on a
live Commons round-trip (see app/dao/bird_photos.py's docstring for how the
persistent, disk-backed cache itself works — this script just front-loads
it). Backs Life List, Explore Map's species-filter suggestions, and the
describe & guess flow's fallback photos.

Default species list is app/data/birds.py's existing canned reference set
(~70 common North American species, already hand-picked for the describe &
guess flow — songbirds, raptors, owls, waterfowl, woodpeckers, waders,
doves). Reusing it means no separate "top 200" list to hand-curate and keep
in sync; it'll just take a few repeated runs (or a larger --birds-module)
to grow further; every species actually searched for in the app gets added
to the same cache organically anyway (see bird_photos.py), so this is a
head start, not the only way species end up cached.

Run directly — no server needs to be running, this calls bird_photos.py
in-process and writes straight to species_photo_cache.json:

    cd backend
    python scripts/seed_bird_photos.py

Safe to re-run: a species already in the cache is skipped for free (no
Commons call at all, see bird_photos.py's own cache check) — so re-running
after adding more species to app/data/birds.py only fetches what's new.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # -> backend/, so `app` imports regardless of cwd

from app.dao import bird_photos
from app.data.birds import all_birds

# Commons' search API rate-limits readily under a burst (the same lesson
# already learned the hard way with Nominatim elsewhere in this codebase,
# see docs/features/explore-map.md) — confirmed live: running this
# concurrently (even capped at 3 in flight) got most requests rate-limited
# (CommonsUnavailable, correctly left uncached rather than poisoning the
# cache with false "nothing found" results — see bird_photos.py — but still
# meant most species came back as a placeholder for that run instead of a
# real photo). Strictly sequential, one request at a time with a pause
# between each, actually gets real photos for a decent majority instead.
_DELAY_BETWEEN_REQUESTS_SECONDS = 1.0


async def main_async() -> int:
    birds = all_birds()

    skipped = newly_fetched = real_photos = placeholders = 0
    for i, bird in enumerate(birds):
        already_cached = bird["scientific_name"] in bird_photos._cache
        photo = await bird_photos.get_stock_photo(bird["scientific_name"], bird["common_name"])
        is_real = not photo["photo_url"].startswith("https://placehold.co/")

        if already_cached:
            skipped += 1
            status = "already cached"
        else:
            newly_fetched += 1
            status = "fetched (real photo)" if is_real else "fetched (no Commons match — placeholder)"
        if is_real:
            real_photos += 1
        else:
            placeholders += 1
        print(f"  {bird['common_name']:30s} {status}")

        # No point pausing after a cache hit (no Commons request happened)
        # or after the very last species.
        if not already_cached and i < len(birds) - 1:
            await asyncio.sleep(_DELAY_BETWEEN_REQUESTS_SECONDS)

    print(
        f"\n{len(birds)} species: {skipped} already cached, {newly_fetched} newly fetched "
        f"({real_photos} real Commons photos, {placeholders} placeholders)."
    )
    print(f"Cache file: {bird_photos._CACHE_FILE}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
