from app.data.exotic_exclusions import EXCLUDED_SPECIES_CODES


def test_excludes_species_with_no_us_population():
    assert {
        "ostric2", "emu1", "grerhe1", "lesrhe2", "chitin1", "maggoo1", "plwduc1", "wfwduc1",
        "wiwduc1",  # West Indian Whistling-Duck — "Provisional"/uncertain-provenance, excluded per product call
        # 2026-09-26 full-list pass — a representative sample, not the whole set:
        "recpoc",   # Red-crested Pochard — eBird's own default is "Escapee"
        "hyamac1",  # Hyacinth Macaw — no wild US range
        "railor5",  # Rainbow Lorikeet — no wild US range
        "trimun",   # Tricolored Munia — aviary escapee, no established US population
        "golphe",   # Golden Pheasant — aviary escapee, not established in the US
    } <= EXCLUDED_SPECIES_CODES
    assert len(EXCLUDED_SPECIES_CODES) >= 165


def test_does_not_exclude_genuinely_us_species():
    # Regression guard: these look similar to the exotics above (same family,
    # visually similar cards) but are genuinely native/naturalized in the US
    # — a future edit that widens the list by family or by eyeballing names
    # rather than verifying per species should not catch these.
    us_natives = {
        "bbwduc",   # Black-bellied Whistling-Duck — breeds in TX, LA, FL
        "fuwduc",   # Fulvous Whistling-Duck — breeds on the Gulf Coast
        "masduc",   # Masked Duck — rare native breeder, southern TX/FL
        "labduc",   # Labrador Duck — extinct, but a NATIVE species, not exotic
        "chukar",   # Chukar — eBird-Naturalized across the western US
        "kalphe",   # Kalij Pheasant — eBird-Naturalized in Hawaii
        "blbqua1",  # Blue-breasted Quail — eBird-Naturalized in Hawaii
        "broqua1",  # Brown Quail — eBird-Naturalized in Hawaii
        "carpar",   # Carolina Parakeet — extinct, but NATIVE to the eastern US
        "thbpar",   # Thick-billed Parrot — historically native to SE Arizona
        "gusgro",   # Gunnison Sage-Grouse — genuine native, just hard to detect
        "lepchi",   # Lesser Prairie-Chicken — genuine native, just hard to detect
        "baitea",   # Baikal Teal — genuine accepted Alaska vagrant
        "compoc",   # Common Pochard — genuine accepted vagrant
        "pifgoo",   # Pink-footed Goose — genuine accepted vagrant
        "smew",     # Smew — genuine accepted vagrant
        "comshe",   # Common Shelduck — genuinely ambiguous, deliberately left undecided
    }
    assert us_natives.isdisjoint(EXCLUDED_SPECIES_CODES)
