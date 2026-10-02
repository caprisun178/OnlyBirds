"""Hand-maintained supplement to `region_repo._drop_escapees`.

That function drops species eBird *currently* flags `exoticCategory: "X"`
(escapee) in a region's last-30-days observations — see
`docs/ebird-api.md#exoticcategory--not-in-the-api-reference-but-documented-by-cornell`.
It can only catch a species whose escapee report falls inside that rolling
window; eBird's public API has no endpoint for "this species' exotic status
in this region, regardless of when it was last reported", so a species whose
*only* escapee sighting was more than 30 days ago has no live signal to
catch it. This list exists to hand-fix exactly that gap.

Keyed by eBird species code (the same `speciesCode` used throughout
`region_repo`/`dao/ebird.py`) rather than name, since codes are the stable
identifier — look one up at https://ebird.org/species/<code> or via
`GET /ref/taxonomy/ebird?species=<code>`. Every entry needs a comment: which
region prompted it and why (so a future maintainer can tell a real fix from
one that's become stale, e.g. if a population later gets Naturalized).

Before adding one, cross-check the species has no real US range with a
second source, not just eBird/Cornell (eBird *is* the data feeding this
whole feature, so a second, independent source is worth having):
[National Audubon Society's Guide to North American Birds](https://www.audubon.org/bird-guide)
(`https://www.audubon.org/field-guide/bird/<slug>`) only covers species that
occur in North America — no entry there for a species is a good corroborating
signal it doesn't belong on a US checklist (verified for every entry below:
none of them have an Audubon field-guide page, while the look-alike US
natives noted at the bottom, e.g. Black-bellied and Fulvous Whistling-Duck,
do).

This is deliberately not "exclude every exotic species everywhere" — most
exotics (House Sparrow, European Starling, Rock Pigeon, ...) are Naturalized
("N") and belong on a life list same as any native bird; eBird's own
Naturalized/Provisional/Escapee distinction already draws that line
correctly for anything within its 30-day lookback. This list only covers the
narrow gap outside that window.
"""

from __future__ import annotations

EXCLUDED_SPECIES_CODES: frozenset[str] = frozenset({
    # --- US region checklist ---
    # All confirmed present on the live `GET /product/spplist/US` response as
    # of 2026-09-26, none with any naturalized/established population
    # anywhere in the US (mainland or Hawaii) — aviary/collection escapees
    # with a one-off historic report, outside eBird's 30-day live-flag window.
    "ostric2",  # Common Ostrich — native to Africa
    "emu1",     # Emu — native to Australia
    "grerhe1",  # Greater Rhea — native to South America
    "lesrhe2",  # Lesser Rhea — native to South America
    "chitin1",  # Chilean Tinamou — native to Chile
    "maggoo1",  # Magpie Goose — native to Australia / New Guinea
    "plwduc1",  # Plumed Whistling-Duck — native to Australia
    "wfwduc1",  # White-faced Whistling-Duck — native to Africa / South America

    # Product call, not a clear-cut fact like the ones above: eBird itself
    # classifies this one "Provisional" rather than "Escapee" when reported
    # (natural vagrancy from the Caribbean vs. captive origin both considered
    # plausible — Cornell's own Provisional records do count toward official
    # eBird totals, which is why `_drop_escapees` doesn't catch it). Excluded
    # here anyway per explicit request — a life list meant to represent
    # genuine wild regional species reasonably leaves out a record eBird
    # itself can't confirm isn't captive-origin. Revisit if FOSRC (Florida's
    # records committee) or eBird ever resolves this to Naturalized.
    "wiwduc1",  # West Indian Whistling-Duck — Caribbean; "Provisional"/uncertain-provenance FL vagrant

    # --- 2026-09-26 full-list pass ---
    # Every species below was found on the live US checklist with zero
    # activity anywhere in the US in eBird's last 30 days (the same profile
    # as the Ostrich case: a one-off historic aviculture-escapee report, not
    # an ongoing population) *and* individually checked — not assumed by
    # family — since several families below have real native/vagrant/
    # naturalized members mixed in with the exotics (see "left OFF" list at
    # the bottom). Two were nearly added by the "zero recent activity" signal
    # alone before an individual check caught them: Gunnison Sage-Grouse and
    # Lesser Prairie-Chicken are genuine, imperiled *native* US species that
    # are simply hard to detect, not exotics — the 30-day heuristic finds
    # candidates, it doesn't decide on its own.

    # Waterfowl — ornamental/collection species with no wild vagrancy
    # potential to the US (distinct from several genuine Siberian/Eurasian
    # vagrants in this same family that are deliberately NOT here — see
    # "left OFF" below).
    "baepoc1",  # Baer's Pochard — Asia
    "blnswa2",  # Black-necked Swan — South America
    "hottea1",  # Blue-billed (Hottentot) Teal — Africa
    "buwgoo1",  # Blue-winged Goose — Ethiopian highlands
    "chetea1",  # Chestnut Teal — Australia
    "chiwig1",  # Chiloe Wigeon — South America
    "cosswa1",  # Coscoroba Swan — South America
    "creduc1",  # Crested Duck — South America
    "ferduc",   # Ferruginous Duck — eBird's own default classification is "Escapee"
    "lwfgoo",   # Lesser White-fronted Goose — Eurasia
    "manduc1",  # Maned (Australian Wood) Duck — Australia
    "martea1",  # Marbled Duck — Mediterranean / Middle East
    "origoo1",  # Orinoco Goose — South America
    "parshe1",  # Paradise Shelduck — New Zealand
    "radshe1",  # Radjah Shelduck — Australia / New Guinea
    "recpoc",   # Red-crested Pochard — eBird's own default classification is "Escapee"
    "rintea1",  # Ringed Teal — South America
    "robpoc1",  # Rosy-billed Pochard — South America
    "siltea1",  # Silver Teal — South America
    "soashe1",  # South African Shelduck — southern Africa
    "soupoc1",  # Southern Pochard — Africa / South America
    "uplgoo1",  # Upland Goose — South America
    "whcpin",   # White-cheeked Pintail — eBird's default is "Escapee"; Florida records specifically
                # have decent odds of being wild Caribbean vagrants (Audubon), but not the norm
    "yebpin1",  # Yellow-billed Pintail — South America
    "yebtea1",  # Yellow-billed (Speckled) Teal — South America

    # Parrots, macaws, parakeets, lovebirds, lorikeets, cockatoos — virtually
    # never shows credible wild vagrancy to the US; any US record is
    # aviculture-trade in origin. "carpar" (Carolina Parakeet) and "thbpar"
    # (Thick-billed Parrot) are deliberately excluded from this exclusion —
    # both are genuine native US species (see "left OFF" below).
    "galah",    # Galah — Australia
    "litcor2",  # Little Corella — Australia
    "succoc",   # Sulphur-crested Cockatoo — Australia / New Guinea
    "barpar1",  # Barred Parakeet — South America
    "blcpar1",  # Black-capped Parakeet — South America
    "blhpar4",  # Black-headed Parrot — South America
    "blhpar1",  # Blue-headed Parrot — South America
    "crfpar",   # Crimson-fronted Parakeet — Central America
    "duhpar",   # Dusky-headed Parakeet — South America
    "golpar3",  # Golden Parakeet — South America
    "grepar",   # Gray Parrot — Africa
    "grgmac",   # Great Green Macaw — Central/South America
    "grrpar1",  # Green-rumped Parrotlet — South America
    "hispar1",  # Hispaniolan Amazon — Hispaniola
    "hispar",   # Hispaniolan Parakeet — Hispaniola
    "hyamac1",  # Hyacinth Macaw — South America
    "janpar1",  # Jandaya Parakeet — South America
    "mabpar",   # Maroon-bellied Parakeet — South America
    "meapar",   # Mealy Amazon — Central/South America
    "meypar1",  # Meyer's Parrot — Africa
    "milmac",   # Military Macaw — Central/South America
    "oltpar1",  # Olive-throated Parakeet — Central America
    "orfpar",   # Orange-fronted Parakeet — Central America
    "pacpar2",  # Pacific Parrotlet — South America
    "pefpar1",  # Peach-fronted Parakeet — South America
    "ragmac1",  # Red-and-green Macaw — South America
    "refmac1",  # Red-fronted Macaw — South America
    "resmac2",  # Red-shouldered Macaw — South America
    "respar2",  # Red-spectacled Amazon — South America
    "scamac1",  # Scarlet Macaw — Central/South America
    "scfpar2",  # Scarlet-fronted Parakeet — South America
    "senpar",   # Senegal Parrot — Africa
    "sunpar1",  # Sun Parakeet — South America
    "bufpar",   # Turquoise-fronted Amazon — South America
    "whcpar",   # White-crowned Parrot — Central America
    "ywcpar",   # Yellow-crowned Amazon — South/Central America
    "yefpar4",  # Yellow-fronted Parrot — Africa
    "yelpar1",  # Yellow-lored Amazon — Central America
    "yenpar1",  # Yellow-naped Amazon — Central America
    "yespar1",  # Yellow-shouldered Amazon — Caribbean
    "alepar2",  # Alexandrine Parakeet — Asia
    "blclov1",  # Black-cheeked Lovebird — Africa
    "boupar2",  # Bourke's Parrot — Australia
    "chalor1",  # Chattering Lory — Indonesia
    "criros2",  # Crimson Rosella — Australia
    "duslor1",  # Dusky Lory — Indonesia
    "easros1",  # Eastern Rosella — Australia
    "maupar1",  # Echo Parakeet — Mauritius
    "lillov1",  # Lilian's Lovebird — Africa
    "litlor1",  # Little Lorikeet — Australia
    "malpar1",  # Malabar Parakeet — India
    "eclpar4",  # Papuan Eclectus — New Guinea
    "plhpar1",  # Plum-headed Parakeet — Asia
    "railor5",  # Rainbow Lorikeet — Australia
    "redlor1",  # Red Lory — Indonesia
    "rebpar4",  # Red-breasted Parakeet — Asia
    "rehlov1",  # Red-headed Lovebird — Africa
    "rerpar1",  # Red-rumped Parrot — Australia
    "regpar1",  # Regent Parrot — Australia

    # Hornbills, turacos, toucans, rollers, leafbirds, bulbuls,
    # laughingthrushes, white-eyes — Old World/Neotropical forest birds with
    # no wild vagrancy potential to the US.
    "bawhor2", "blchor1", "rebhor1", "orphor1", "piphor1", "truhor1", "wrbhor2", "whthor1",  # hornbills — Africa/Asia
    "grygab1", "whctur1",  # turacos — Africa
    "kebtou1",  # Keel-billed Toucan — Central America
    "blbrol1", "librol2",  # rollers — Africa
    "goflea1",  # Golden-fronted Leafbird — Asia
    "whebul1",  # White-eared Bulbul — Asia (Red-whiskered Bulbul, naturalized in FL, is NOT on this list)
    "whclau2",  # White-crested Laughingthrush — Asia; a feral CA population existed historically but
                # isn't currently reflected as Naturalized/reported
    "indwhe1",  # Indian White-eye — Asia (Japanese White-eye, naturalized in HI, is NOT on this list)

    # Estrildid finches (waxbills, munias, firefinches, cordonbleus, ...),
    # weavers/bishops/widowbirds, whydahs/indigobirds — African/Asian/
    # Australian aviary finches, no wild vagrancy potential to the US.
    # (Scaly-breasted Munia/Nutmeg Mannikin and Bronze Mannikin, naturalized
    # in parts of CA/LA/HI, are NOT on this list.)
    "afffin", "bawman1", "bkrwax", "blccor1", "crrwax1", "cutthr1", "diafir1", "dobfin1",
    "grwpyt1", "indsil", "magman1", "rebfir2", "rebfir1", "reccor", "pettwi1", "bubcor1",
    "stafin1", "trimun", "whhmun1", "whrmun", "zebwax2",
    "blhwea1", "blwbis1", "gopwea1", "redfod1", "recwid3", "afmwea", "redbis", "tagwea1",
    "vilwea1", "vimwea1", "whwwid1", "zanbis1",
    "btpwhy1", "eapwhy1", "topwhy1", "vilind",

    # Starlings/mynas, Old World sparrows, gamebirds — exotic species with no
    # established US population (European Starling, House Sparrow, Chukar,
    # and the several Hawaii-naturalized gamebirds are all genuinely
    # Naturalized and deliberately NOT on this list — see "left OFF" below).
    "balmyn1", "brasta1", "cremyn", "ltgsta1", "pugsta1", "supsta1",  # starlings/mynas
    "sugspa1",  # Sudan Golden Sparrow
    "elequa",   # Elegant Quail — Mexican endemic, no US population
    "comqua1",  # Common Quail — distinct from the Hawaii-naturalized Japanese/Brown/Blue-breasted Quail
    "golphe", "grypep2", "grepea1", "rinphe2", "laaphe1", "relpar1", "reephe1", "silphe", "swiphe1",
    # Golden/Lady Amherst's/Reeves's/Swinhoe's/Silver Pheasant, Green Pheasant,
    # Gray Peacock-Pheasant, Green Peafowl, Red-legged Partridge — Asian/European
    # gamebirds, aviary escapees, none with an established self-sustaining US population

    # Species intentionally left OFF this list despite looking similar:
    # - "bbwduc" (Black-bellied Whistling-Duck) and "fuwduc" (Fulvous
    #   Whistling-Duck) are genuinely native/breeding in the southern US
    #   (Texas, Louisiana, Florida) — not exotics at all.
    # - "masduc" (Masked Duck) is a genuine, if rare, native breeder in
    #   southern TX/FL. "labduc" (Labrador Duck) is an extinct *native*
    #   species, not an exotic. Several Siberian/Eurasian waterfowl in this
    #   same family — Baikal Teal, Common Pochard, Common Scoter, Eastern
    #   Spot-billed Duck, Falcated Duck, Pink-footed Goose, Red-breasted
    #   Goose, Smew, Stejneger's Scoter, Taiga/Tundra Bean-Goose — are
    #   genuine accepted rare vagrants, not escapees. "comshe" (Common
    #   Shelduck) is left off too: genuinely ambiguous, with both accepted
    #   vagrant and escapee records, and not enough signal either way to
    #   call it.
    # - "carpar" (Carolina Parakeet, extinct) and "thbpar" (Thick-billed
    #   Parrot) are native/historically-native US species, not exotics —
    #   both look like they belong in the parrot exclusions above, but don't.
    # - "gusgro" (Gunnison Sage-Grouse) and "lepchi" (Lesser Prairie-Chicken)
    #   are genuine native US species, both endangered/threatened and hard
    #   to detect — not exotics. Caught by the same "zero recent activity"
    #   signal as everything above, but ruled out on an individual check.
    #   "blbqua1" (Blue-breasted Quail) and "broqua1" (Brown Quail) are
    #   genuinely Naturalized in Hawaii.
    # - Several other Asian/African gamebirds in the "Pheasants, Grouse, and
    #   Allies" family (Chukar, Kalij Pheasant, Erckel's Spurfowl, Gray/Black
    #   Francolin, Himalayan Snowcock, Japanese Quail, ...) look exotic but
    #   ARE eBird-Naturalized somewhere in the US, mostly Hawaii or the
    #   western mainland — genuinely countable, so not excluded here.
})
