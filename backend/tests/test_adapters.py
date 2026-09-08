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


def test_from_inaturalist():
    obs = adapters.from_inaturalist(INAT_RECORD)
    assert obs.source is Source.inat
    assert obs.source_observation_id == "987654"
    assert obs.species.source_ids == {"inat": "4444"}
    assert obs.photo_url.endswith("square.jpg")
    assert round(obs.lat, 2) == 36.4 and round(obs.lng, 2) == -115.35
