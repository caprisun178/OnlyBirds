from app.models.observation import Source
from app.services import adapters

EBIRD_RECORD = {
    "speciesCode": "compoo",
    "comName": "Common Poorwill",
    "sciName": "Phalaenoptilus nuttallii",
    "locName": "Desert NWR",
    "obsDt": "2026-05-01 06:30",
    "subId": "S12345678",
    "lat": 36.4,
    "lng": -115.35,
}

INAT_RECORD = {
    "id": 987654,
    "description": "singing male",
    "place_guess": "Red Rock Canyon, NV",
    "time_observed_at": "2026-05-02T07:15:00+00:00",
    "geojson": {"type": "Point", "coordinates": [-115.35, 36.4]},
    "photos": [{"url": "https://static.inaturalist.org/photos/1/square.jpg"}],
    "taxon": {
        "id": 4444,
        "name": "Phalaenoptilus nuttallii",
        "preferred_common_name": "Common Poorwill",
        "iconic_taxon_name": "Aves",
    },
}


def test_from_ebird():
    obs = adapters.from_ebird(EBIRD_RECORD)
    assert obs.source is Source.ebird
    assert obs.source_observation_id == "S12345678"
    assert obs.species.source_ids == {"ebird": "compoo"}
    assert (obs.lat, obs.lng) == (36.4, -115.35)
    assert obs.observed_at.year == 2026 and obs.observed_at.hour == 6
    # Regression: this used to land in `notes` instead, which read
    # misleadingly on the Explore Map popup (a place name shown as if it
    # were a free-text note) once that screen started showing both fields.
    assert obs.location_name == "Desert NWR"
    assert obs.notes is None


def test_from_inaturalist():
    obs = adapters.from_inaturalist(INAT_RECORD)
    assert obs.source is Source.inat
    assert obs.source_observation_id == "987654"
    assert obs.species.source_ids == {"inat": "4444"}
    # Regression: iNaturalist's API only ever returns the 75x75 "square"
    # thumbnail — extremely blurry once shown full-size in the detail panel.
    # Confirmed live that "medium" (much larger) exists at the same path.
    assert obs.photo_url == "https://static.inaturalist.org/photos/1/medium.jpg"
    assert round(obs.lat, 2) == 36.4 and round(obs.lng, 2) == -115.35
    # iNaturalist's own human-readable place name — needed so "top spots"
    # groupings on Explore Map have something to group by (eBird always has
    # `locName`; iNaturalist's nearest equivalent is `place_guess`).
    assert obs.location_name == "Red Rock Canyon, NV"


def test_upgrade_inat_photo_size_swaps_square_for_medium():
    assert (
        adapters._upgrade_inat_photo_size("https://static.inaturalist.org/photos/1/square.jpg")
        == "https://static.inaturalist.org/photos/1/medium.jpg"
    )


def test_upgrade_inat_photo_size_leaves_non_square_urls_alone():
    # Defensive: only replace the exact pattern we've confirmed — an
    # unexpected URL shape should pass through unchanged rather than risk
    # mangling it.
    url = "https://static.inaturalist.org/photos/1/original.jpg"
    assert adapters._upgrade_inat_photo_size(url) == url


def test_upgrade_inat_photo_size_handles_none():
    assert adapters._upgrade_inat_photo_size(None) is None


SPECIES_COUNT_RECORD = {
    "count": 42,
    "taxon": {
        "id": 4444,
        "name": "Phalaenoptilus nuttallii",
        "preferred_common_name": "Common Poorwill",
        "iconic_taxon_name": "Aves",
        "default_photo": {"medium_url": "https://static.inaturalist.org/photos/1/medium.jpg"},
    },
}


def test_from_inat_species_count():
    result = adapters.from_inat_species_count(SPECIES_COUNT_RECORD)
    assert result.species.scientific_name == "Phalaenoptilus nuttallii"
    assert result.species.common_name == "Common Poorwill"
    assert result.species.source_ids == {"inat": "4444"}
    assert result.observation_count == 42
    # default_photo.medium_url is already the right size — must NOT go
    # through _upgrade_inat_photo_size() (that only applies to the
    # observation-level photos[].url field, stuck at a 75x75 thumbnail).
    assert result.photo_url == "https://static.inaturalist.org/photos/1/medium.jpg"


def test_from_inat_species_count_handles_missing_photo():
    record = {"count": 3, "taxon": {"id": 1, "name": "Corvus corax", "iconic_taxon_name": "Aves"}}
    result = adapters.from_inat_species_count(record)
    assert result.photo_url is None


EBIRD_HOTSPOT_RECORD = {
    "locId": "L1021141",
    "locName": "Bethania--Black Walnut Bottom",
    "lat": 36.1780162,
    "lng": -80.3390694,
    "numSpeciesAllTime": 160,
}


def test_from_ebird_hotspot():
    result = adapters.from_ebird_hotspot(EBIRD_HOTSPOT_RECORD)
    assert result.loc_id == "L1021141"
    assert result.name == "Bethania--Black Walnut Bottom"
    assert result.lat == 36.1780162
    assert result.lng == -80.3390694
    assert result.species_all_time == 160


def test_from_ebird_hotspot_handles_missing_name_and_count():
    record = {"locId": "L2", "lat": 36.1, "lng": -80.3}
    result = adapters.from_ebird_hotspot(record)
    assert result.name == "Unnamed location"
    assert result.species_all_time == 0
