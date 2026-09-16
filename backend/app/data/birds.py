"""Canned reference set for the describe & guess identification flow.

Computer vision is descoped for MVP (`docs/features/add-observation.md`), so
there is no real photo-classification model behind this yet. Instead
`app/dao/identify.py` matches free text against this small, hand-picked set of
species grouped by how easily they're confused for one another by sight —
enough to drive the "6 similar photos, pick the one you saw" flow end to end.

`photo_url` points at a generated placeholder (name + group colour) rather
than a real photo. Swap this out for cached Macaulay Library media
(`species_content.media`, see `bird-info.md`) once that lands — nothing else
in the identify flow needs to change, since callers only ever see the
`Candidate` shape.
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
]

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
