"""
==============================
Status & Trends script library
Description:
Raw access to eBird Status & Trends — no business logic. Migration timing
and relative-abundance data (Cornell Lab of Ornithology) for a species'
"About" / migration block. Distributed as downloadable data products, not a
simple REST API — confirm the actual access method (a data request, a bulk
download processed offline, or a real endpoint) before implementing below.
See docs/features/bird-info.md. Docs: https://science.ebird.org/en/status-and-trends

=============================
changeLog
=============================
09/11/2026 ... SP ... Created library
=============================
"""


async def get_migration_summary(species_code: str) -> dict | None:
    """Migration/abundance summary for a species, or `None` if unavailable.

    Needed by Bird info to populate `species_content.migration` — cache the
    result there rather than fetching on every page view.
    """
    raise NotImplementedError
