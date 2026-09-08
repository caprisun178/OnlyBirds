"""The adapter layer: external JSON -> internal `Observation`.

This is reason #2 in the README for having a backend at all — iNaturalist and
eBird describe the same real-world event with different field names and shapes.
Everything downstream (life list, endpoints, frontends) only sees `Observation`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.observation import Observation, Source
from app.models.species import SpeciesRef


def _parse_dt(value: str | None) -> datetime:
    """Best-effort parse of the assorted date/time formats both APIs emit."""
    if not value:
        return datetime.now(tz=timezone.utc)
    text = value.strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=timezone.utc)


def from_ebird(record: dict) -> Observation:
    """One element of eBird's `/data/obs/geo/recent` response."""
    species = SpeciesRef(
        scientific_name=record.get("sciName"),
        common_name=record.get("comName"),
        taxon_group="birds",
        source_ids={"ebird": record["speciesCode"]} if record.get("speciesCode") else {},
    )
    return Observation(
        species=species,
        lat=record.get("lat", 0.0),
        lng=record.get("lng", 0.0),
        observed_at=_parse_dt(record.get("obsDt")),
        source=Source.ebird,
        source_observation_id=record.get("subId"),
        notes=record.get("locName"),
    )


def from_inaturalist(record: dict) -> Observation:
    """One element of iNaturalist's `/observations` response."""
    taxon = record.get("taxon") or {}
    source_ids: dict[str, str] = {}
    if taxon.get("id") is not None:
        source_ids["inat"] = str(taxon["id"])
    species = SpeciesRef(
        scientific_name=taxon.get("name"),
        common_name=taxon.get("preferred_common_name"),
        taxon_group=taxon.get("iconic_taxon_name"),
        source_ids=source_ids,
    )

    lat, lng = _inat_coords(record)
    photos = record.get("photos") or []
    photo_url = photos[0].get("url") if photos else None

    return Observation(
        species=species,
        lat=lat,
        lng=lng,
        observed_at=_parse_dt(
            record.get("time_observed_at") or record.get("observed_on")
        ),
        source=Source.inat,
        source_observation_id=str(record["id"]) if record.get("id") is not None else None,
        photo_url=photo_url,
        notes=record.get("description"),
    )


def _inat_coords(record: dict) -> tuple[float, float]:
    geo = record.get("geojson") or {}
    coords = geo.get("coordinates")
    if isinstance(coords, list) and len(coords) == 2:
        return float(coords[1]), float(coords[0])  # geojson is [lng, lat]
    location = record.get("location")
    if isinstance(location, str) and "," in location:
        lat_str, lng_str = location.split(",", 1)
        try:
            return float(lat_str), float(lng_str)
        except ValueError:
            pass
    return 0.0, 0.0
