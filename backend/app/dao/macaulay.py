"""
==============================
Macaulay script library
Description:
Raw access to the Macaulay Library asset API — no business logic. Species
photos and audio (Cornell Lab of Ornithology), keyed by eBird species code.
No confirmed base URL, auth scheme, or response shape yet — a Cornell/
Macaulay developer account may be required. See docs/features/bird-info.md.

=============================
changeLog
=============================
09/11/2026 ... SP ... Created library
=============================
"""




async def get_media(species_code: str, media_type: str | None = None) -> list[dict]:
    """Photo/audio asset references for a species.

    `media_type` is `photo` | `audio` | `None` (both). Needed by Bird info to
    populate `species_content.media` — cache the result there rather than
    fetching on every page view.
    """
    raise NotImplementedError
