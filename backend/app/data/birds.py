"""Canned reference set for the describe & guess identification flow.

Computer vision is descoped for MVP (`docs/features/add-observation.md`), so
there is no real photo-classification model behind this yet. Instead
`app/dao/identify.py` matches free text against this small, hand-picked set of
species grouped by how easily they're confused for one another by sight —
enough to drive the "6 similar photos, pick the one you saw" flow end to end.

Covers songbirds (by colour: blue, red/orange, brown/streaky, black, yellow,
gray/small) plus owls, raptors, waterfowl, woodpeckers, herons/waders, and
doves/pigeons — the shapes/categories a casual description is most likely to
name. Add a new group by giving 5-6 species that same `group` string; a
species whose common name doesn't already contain the word its family goes
by (e.g. "Mallard" vs. "duck") should get an entry in `_KEYWORD_OVERRIDES`
below so a generic description still finds it.

`photo_url` here is a generated placeholder (name + group colour), used only
as a **fallback**. `app/dao/bird_photos.py` looks up a real photo from
Wikimedia Commons by scientific name and only falls back to this value if
that lookup fails — see that module and `docs/features/add-observation.md`
for why Commons rather than Macaulay Library. Swap the fallback out (or drop
it) once real Macaulay media (`species_content.media`, see `bird-info.md`)
lands — nothing else in the identify flow needs to change, since callers
only ever see the `Candidate` shape.
"""

from __future__ import annotations

from urllib.parse import quote

# One hex colour per "looks like this" group, just so the placeholder photos
# are visually grouped in dev/demo screenshots.
_GROUP_COLORS = {
    "blue": "3aa0ff",
    "red_orange": "e2543f",
    "brown_streaky": "8a6a4b",
    "black": "2b2b2b",
    "yellow": "e8c229",
    "gray_small": "7a8a99",
    "owls": "6b5335",
    "raptors": "8a5a2e",
    "waterfowl": "2e7d5b",
    "woodpeckers": "c0392b",
    "herons_waders": "4a7a8c",
    "doves_pigeons": "9a9a9a",
}


def _placeholder_photo(common_name: str, group: str) -> str:
    color = _GROUP_COLORS[group]
    label = quote(common_name)
    return f"https://placehold.co/320x220/{color}/ffffff?text={label}"


# code, common_name, scientific_name, group, size, colors, habitat
_RAW = [
    # -- blue --------------------------------------------------------------
    ("blujay", "Blue Jay", "Cyanocitta cristata", "blue", "medium", {"blue", "white", "black"}, {"woodland", "backyard"}),
    ("stejay1", "Steller's Jay", "Cyanocitta stelleri", "blue", "medium", {"blue", "black"}, {"woodland"}),
    ("indbun", "Indigo Bunting", "Passerina cyanea", "blue", "small", {"blue"}, {"grassland", "woodland"}),
    ("moublu", "Mountain Bluebird", "Sialia currucoides", "blue", "small", {"blue"}, {"grassland"}),
    ("belkin1", "Belted Kingfisher", "Megaceryle alcyon", "blue", "medium", {"blue", "white"}, {"wetland"}),
    ("treswa", "Tree Swallow", "Tachycineta bicolor", "blue", "small", {"blue", "white"}, {"wetland", "grassland"}),
    # -- red / orange --------------------------------------------------------
    ("norcar", "Northern Cardinal", "Cardinalis cardinalis", "red_orange", "medium", {"red"}, {"backyard", "woodland"}),
    ("scatan", "Scarlet Tanager", "Piranga olivacea", "red_orange", "small", {"red", "black"}, {"woodland"}),
    ("houfin", "House Finch", "Haemorhous mexicanus", "red_orange", "small", {"red", "brown"}, {"backyard", "urban"}),
    ("verfly", "Vermilion Flycatcher", "Pyrocephalus rubinus", "red_orange", "small", {"red"}, {"grassland"}),
    ("balori", "Baltimore Oriole", "Icterus galbula", "red_orange", "small", {"orange", "black"}, {"woodland", "backyard"}),
    ("amerob", "American Robin", "Turdus migratorius", "red_orange", "medium", {"orange", "brown"}, {"backyard", "grassland"}),
    # -- brown / streaky sparrows ---------------------------------------------
    ("sonspa", "Song Sparrow", "Melospiza melodia", "brown_streaky", "small", {"brown"}, {"wetland", "backyard"}),
    ("savspa", "Savannah Sparrow", "Passerculus sandwichensis", "brown_streaky", "small", {"brown"}, {"grassland"}),
    ("houspa", "House Sparrow", "Passer domesticus", "brown_streaky", "small", {"brown", "gray"}, {"urban", "backyard"}),
    ("chispa", "Chipping Sparrow", "Spizella passerina", "brown_streaky", "small", {"brown"}, {"backyard", "woodland"}),
    ("whcspa", "White-crowned Sparrow", "Zonotrichia leucophrys", "brown_streaky", "small", {"brown", "white"}, {"grassland", "backyard"}),
    ("carwre", "Carolina Wren", "Thryothorus ludovicianus", "brown_streaky", "small", {"brown"}, {"woodland", "backyard"}),
    # -- black -----------------------------------------------------------
    ("amecro", "American Crow", "Corvus brachyrhynchos", "black", "large", {"black"}, {"urban", "grassland"}),
    ("comrav", "Common Raven", "Corvus corax", "black", "large", {"black"}, {"woodland", "grassland"}),
    ("eursta", "European Starling", "Sturnus vulgaris", "black", "medium", {"black"}, {"urban", "backyard"}),
    ("rewbla", "Red-winged Blackbird", "Agelaius phoeniceus", "black", "medium", {"black", "red"}, {"wetland"}),
    ("bnhcow", "Brown-headed Cowbird", "Molothrus ater", "black", "medium", {"black", "brown"}, {"grassland", "backyard"}),
    ("comgra", "Common Grackle", "Quiscalus quiscula", "black", "medium", {"black"}, {"urban", "grassland"}),
    # -- yellow ------------------------------------------------------------
    ("amegfi", "American Goldfinch", "Spinus tristis", "yellow", "small", {"yellow", "black"}, {"backyard", "grassland"}),
    ("yelwar", "Yellow Warbler", "Setophaga petechia", "yellow", "small", {"yellow"}, {"wetland", "woodland"}),
    ("wlswar", "Wilson's Warbler", "Cardellina pusilla", "yellow", "small", {"yellow", "black"}, {"woodland", "wetland"}),
    ("westan", "Western Tanager", "Piranga ludoviciana", "yellow", "small", {"yellow", "red"}, {"woodland"}),
    ("comyel", "Common Yellowthroat", "Geothlypis trichas", "yellow", "small", {"yellow", "black"}, {"wetland"}),
    ("evegro", "Evening Grosbeak", "Coccothraustes vespertinus", "yellow", "medium", {"yellow", "black"}, {"woodland", "backyard"}),
    # -- gray / small (chickadee-shaped) --------------------------------------
    ("bkcchi", "Black-capped Chickadee", "Poecile atricapillus", "gray_small", "small", {"gray", "black", "white"}, {"woodland", "backyard"}),
    ("tuftit", "Tufted Titmouse", "Baeolophus bicolor", "gray_small", "small", {"gray"}, {"woodland", "backyard"}),
    ("whbnut", "White-breasted Nuthatch", "Sitta carolinensis", "gray_small", "small", {"gray", "white"}, {"woodland", "backyard"}),
    ("carchi", "Carolina Chickadee", "Poecile carolinensis", "gray_small", "small", {"gray", "black", "white"}, {"woodland"}),
    ("mouchi", "Mountain Chickadee", "Poecile gambeli", "gray_small", "small", {"gray", "black", "white"}, {"woodland"}),
    ("bushti", "Bushtit", "Psaltriparus minimus", "gray_small", "small", {"gray"}, {"woodland", "backyard"}),
    # -- owls ----------------------------------------------------------------
    ("greathorn", "Great Horned Owl", "Bubo virginianus", "owls", "large", {"brown", "gray"}, {"woodland", "grassland"}),
    ("barredowl", "Barred Owl", "Strix varia", "owls", "large", {"brown", "gray", "white"}, {"woodland", "wetland"}),
    ("easscreec", "Eastern Screech-Owl", "Megascops asio", "owls", "small", {"brown", "gray"}, {"woodland", "backyard"}),
    ("barnowl1", "Barn Owl", "Tyto alba", "owls", "medium", {"white", "brown", "gray"}, {"grassland", "urban"}),
    ("shoeaowl", "Short-eared Owl", "Asio flammeus", "owls", "medium", {"brown"}, {"grassland", "wetland"}),
    ("snowyowl", "Snowy Owl", "Bubo scandiacus", "owls", "large", {"white"}, {"grassland"}),
    # -- raptors (hawks / eagles) ---------------------------------------------
    ("redtail1", "Red-tailed Hawk", "Buteo jamaicensis", "raptors", "large", {"brown", "white"}, {"grassland", "woodland"}),
    ("coophawk", "Cooper's Hawk", "Accipiter cooperii", "raptors", "medium", {"gray", "brown"}, {"woodland", "backyard"}),
    ("sharpshin", "Sharp-shinned Hawk", "Accipiter striatus", "raptors", "small", {"gray", "brown"}, {"woodland"}),
    ("baldeagl", "Bald Eagle", "Haliaeetus leucocephalus", "raptors", "large", {"brown", "white"}, {"wetland", "woodland"}),
    ("osprey1", "Osprey", "Pandion haliaetus", "raptors", "large", {"brown", "white"}, {"wetland"}),
    ("amekest", "American Kestrel", "Falco sparverius", "raptors", "small", {"orange", "gray", "blue"}, {"grassland", "urban"}),
    # -- waterfowl -------------------------------------------------------------
    ("mallard1", "Mallard", "Anas platyrhynchos", "waterfowl", "medium", {"green", "brown", "white"}, {"wetland", "urban"}),
    ("wooduck1", "Wood Duck", "Aix sponsa", "waterfowl", "medium", {"green", "white", "brown"}, {"wetland", "woodland"}),
    ("ribduck1", "Ring-necked Duck", "Aythya collaris", "waterfowl", "medium", {"black", "white", "gray"}, {"wetland"}),
    ("norshov", "Northern Shoveler", "Spatula clypeata", "waterfowl", "medium", {"green", "brown", "white"}, {"wetland"}),
    ("canada1", "Canada Goose", "Branta canadensis", "waterfowl", "large", {"brown", "black", "white"}, {"wetland", "grassland", "urban"}),
    ("trumswan", "Trumpeter Swan", "Cygnus buccinator", "waterfowl", "large", {"white"}, {"wetland"}),
    # -- woodpeckers ---------------------------------------------------------
    ("dowwoo", "Downy Woodpecker", "Dryobates pubescens", "woodpeckers", "small", {"black", "white", "red"}, {"woodland", "backyard"}),
    ("haiwoo", "Hairy Woodpecker", "Dryobates villosus", "woodpeckers", "medium", {"black", "white", "red"}, {"woodland"}),
    ("rebwoo", "Red-bellied Woodpecker", "Melanerpes carolinus", "woodpeckers", "medium", {"red", "gray", "white"}, {"woodland", "backyard"}),
    ("norfli", "Northern Flicker", "Colaptes auratus", "woodpeckers", "medium", {"brown", "black", "red"}, {"woodland", "backyard", "grassland"}),
    ("pilwoo", "Pileated Woodpecker", "Dryocopus pileatus", "woodpeckers", "large", {"black", "white", "red"}, {"woodland"}),
    ("rehwoo", "Red-headed Woodpecker", "Melanerpes erythrocephalus", "woodpeckers", "medium", {"red", "black", "white"}, {"woodland"}),
    # -- herons / waders -------------------------------------------------------
    ("gbheron", "Great Blue Heron", "Ardea herodias", "herons_waders", "large", {"blue", "gray", "white"}, {"wetland"}),
    ("greategr", "Great Egret", "Ardea alba", "herons_waders", "large", {"white"}, {"wetland"}),
    ("snoegret", "Snowy Egret", "Egretta thula", "herons_waders", "medium", {"white"}, {"wetland"}),
    ("greeheron", "Green Heron", "Butorides virescens", "herons_waders", "small", {"green", "brown"}, {"wetland"}),
    ("bcnheron", "Black-crowned Night-Heron", "Nycticorax nycticorax", "herons_waders", "medium", {"black", "white", "gray"}, {"wetland"}),
    ("sandcran", "Sandhill Crane", "Antigone canadensis", "herons_waders", "large", {"gray", "brown"}, {"grassland", "wetland"}),
    # -- doves / pigeons -------------------------------------------------------
    ("moudov1", "Mourning Dove", "Zenaida macroura", "doves_pigeons", "medium", {"brown", "gray"}, {"backyard", "grassland", "urban"}),
    ("rocpige", "Rock Pigeon", "Columba livia", "doves_pigeons", "medium", {"gray", "black", "white"}, {"urban"}),
    ("eucdove", "Eurasian Collared-Dove", "Streptopelia decaocto", "doves_pigeons", "medium", {"gray", "brown"}, {"urban", "backyard"}),
    ("whwdove", "White-winged Dove", "Zenaida asiatica", "doves_pigeons", "medium", {"brown", "gray", "white"}, {"backyard", "urban"}),
    ("bandtail", "Band-tailed Pigeon", "Patagioenas fasciata", "doves_pigeons", "medium", {"gray"}, {"woodland"}),
    ("incadove", "Inca Dove", "Columbina inca", "doves_pigeons", "small", {"gray", "brown"}, {"urban", "backyard"}),
]

# Extra search terms for a species whose common name doesn't already contain
# the word a generic description would likely use for its family (e.g.
# "duck" for a Mallard, which is only ever called by its own name).
_KEYWORD_OVERRIDES: dict[str, set[str]] = {
    "mallard1": {"duck", "waterfowl"},
    "norshov": {"duck"},
    "ribduck1": {"duck"},
    "wooduck1": {"duck"},
    "canada1": {"goose", "waterfowl"},
    "sandcran": {"crane"},
    "rocpige": {"pigeon"},
}

BIRDS: dict[str, dict] = {}
for _code, _name, _sci, _group, _size, _colors, _habitat in _RAW:
    BIRDS[_code] = {
        "code": _code,
        "common_name": _name,
        "scientific_name": _sci,
        "group": _group,
        "size": _size,
        "colors": _colors,
        "habitat": _habitat,
        "keywords": _KEYWORD_OVERRIDES.get(_code, set()),
        "photo_url": _placeholder_photo(_name, _group),
    }

# Every other bird in the same visual-confusion group, in a fixed order.
for _bird in BIRDS.values():
    _bird["similar"] = [
        code
        for code, other in BIRDS.items()
        if other["group"] == _bird["group"] and code != _bird["code"]
    ]


def all_birds() -> list[dict]:
    return list(BIRDS.values())


def get_bird(code: str) -> dict | None:
    return BIRDS.get(code)
