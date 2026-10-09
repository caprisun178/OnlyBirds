import asyncio

import httpx
import pytest

from app.dao import commons
from app.dao.commons import CommonsUnavailable, _strip_html, format_attribution

# Captured before any test monkeypatches `commons.httpx.AsyncClient` (see the
# two tests below) — those tests replace that name with a fake, so the fake
# itself must build its (real, mock-transport-backed) client from this
# original reference rather than `httpx.AsyncClient`, or it recurses into
# itself.
_RealAsyncClient = httpx.AsyncClient


def test_strip_html_drops_hidden_screen_reader_duplicate():
    # Regression: Commons' "Unknown author" template appends a hidden
    # duplicate for screen readers, e.g. found live on a real recording:
    # 'Unknown author<span style="display: none;">Unknown author</span>'
    # — without stripping it, the credit line reads "Unknown authorUnknown author".
    raw = 'Unknown author<span style="display: none;">Unknown author</span>'
    assert _strip_html(raw) == "Unknown author"


def test_strip_html_handles_plain_text():
    assert _strip_html("Jane Doe") == "Jane Doe"


def test_strip_html_handles_none_and_empty():
    assert _strip_html(None) is None
    assert _strip_html("") is None


def test_strip_html_strips_ordinary_link_markup():
    raw = '<a href="//commons.wikimedia.org/wiki/User:Mdf" title="User:Mdf">Mdf</a>'
    assert _strip_html(raw) == "Mdf"


def test_format_attribution_includes_artist_and_license():
    result = {"artist": "Jane Doe", "license": "CC BY-SA 3.0"}
    assert format_attribution(result) == "Jane Doe / Wikimedia Commons (CC BY-SA 3.0)"


def test_format_attribution_without_artist():
    result = {"license": "CC BY 2.0"}
    assert format_attribution(result) == "Wikimedia Commons (CC BY 2.0)"


def test_format_attribution_without_license():
    result = {"artist": "Jane Doe"}
    assert format_attribution(result) == "Jane Doe / Wikimedia Commons"


def _mock_client(handler):
    """A fake `httpx.AsyncClient` (same shape `commons._search` uses it: as
    an async context manager) backed by a real client wired to a mock
    transport — no real network call, per the "offline tests" rule. Built
    from `_RealAsyncClient` (captured above, before any patching) rather
    than `httpx.AsyncClient`, since tests using this replace that very name.
    """
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._client = _RealAsyncClient(transport=httpx.MockTransport(handler))

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            await self._client.aclose()

    return FakeAsyncClient


def _page(index, title, *, categories=(), object_name=None, description=None, has_image=True):
    """One `query.pages` entry, shaped like a real Commons generator-search
    response — `index` is Commons' own relevance rank (the dict itself is
    keyed by page id, not rank order, see `_search`)."""
    page = {"title": title, "index": index}
    if categories:
        page["categories"] = [{"title": c} for c in categories]
    if has_image:
        extmetadata = {}
        if object_name:
            extmetadata["ObjectName"] = {"value": object_name}
        if description:
            extmetadata["ImageDescription"] = {"value": description}
        page["imageinfo"] = [{
            "thumburl": f"https://upload.wikimedia.org/{index}.jpg",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
            "extmetadata": extmetadata,
        }]
    return page


def test_search_raises_commons_unavailable_on_http_error(monkeypatch):
    # Regression: a rate limit (429) or any other HTTP-level failure used to
    # be swallowed into a plain `None`, indistinguishable from Commons
    # genuinely having nothing — which meant `bird_photos.py` cached a
    # transient rate-limit as a permanent "no photo" for that species. Now
    # it's a distinct exception the caller has to consciously not cache.
    #
    # Exercises the real `_search()` (bypassing the autouse
    # `no_live_media_lookups` fixture, which stubs the public
    # `search_photo`/`search_audio` wrappers, not `_search` itself).
    def raise_429(request):
        return httpx.Response(429, request=request, text="Too Many Requests")

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(raise_429))

    with pytest.raises(CommonsUnavailable):
        asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))


def test_search_returns_none_on_genuine_empty_result(monkeypatch):
    def empty_result(request):
        return httpx.Response(200, request=request, json={"query": {"pages": {}}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(empty_result))

    assert asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True)) is None


def test_search_skips_top_ranked_specimen_photo_by_title(monkeypatch):
    # Regression: real live-data case. American Robin's top Commons hit was
    # a museum specimen photo of an egg (accession-number filename), ranked
    # ahead of several ordinary live-bird photos.
    def handler(request):
        pages = {
            "1": _page(1, "File:Robin egg in nest.jpg"),
            "2": _page(2, "File:Turdus migratorius in Central Park.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))
    assert result["media_url"] == "https://upload.wikimedia.org/2.jpg"


def test_search_skips_top_ranked_specimen_photo_by_category(monkeypatch):
    # Same real case, but the specimen file's name is just an accession
    # number (as it actually was) — no keyword in the title at all, only in
    # its Commons categories, which the filter also has to check.
    def handler(request):
        pages = {
            "1": _page(1, "File:MHNT.ZOO.2010.11.189.14.jpg", categories=["Category:Bird eggs in MHNT"]),
            "2": _page(2, "File:Turdus migratorius in Central Park.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))
    assert result["media_url"] == "https://upload.wikimedia.org/2.jpg"


def test_search_skips_top_ranked_specimen_photo_by_description_metadata(monkeypatch):
    # Same real case again, but this time neither the filename nor any
    # category names it — a GLAM batch upload can leave the descriptive
    # text only in ObjectName/ImageDescription metadata (which `_search`
    # already fetches via `iiprop=extmetadata` for the attribution credit,
    # so checking it here costs no extra request).
    def handler(request):
        pages = {
            "1": _page(1, "File:MHNT.ZOO.2010.11.189.14.jpg", object_name="Œuf, Turdus migratorius, MHNT"),
            "2": _page(2, "File:Turdus migratorius in Central Park.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))
    assert result["media_url"] == "https://upload.wikimedia.org/2.jpg"


def test_search_falls_back_to_top_result_when_every_candidate_is_unwanted(monkeypatch):
    # Better an imperfect real photo than nothing — the filter narrows, it
    # doesn't ever turn a real result into None. `flagged=True` is how a
    # caller that actually needs a real bird photo (not just "some image")
    # can tell this was a forced pick, not a clean match — see
    # app/services/quiz.py's use of this.
    def handler(request):
        pages = {
            "1": _page(1, "File:Robin egg.jpg"),
            "2": _page(2, "File:Robin nest with eggs.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))
    assert result["media_url"] == "https://upload.wikimedia.org/1.jpg"  # top-ranked, despite being unwanted
    assert result["flagged"] is True


def test_search_clean_match_is_not_flagged(monkeypatch):
    def handler(request):
        pages = {
            "1": _page(1, "File:Robin egg in nest.jpg"),
            "2": _page(2, "File:Turdus migratorius in Central Park.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))
    assert result["flagged"] is False


def test_search_skips_a_range_map(monkeypatch):
    # Real, reported case: a Seaside Sparrow quiz question showed a range
    # map instead of a photo. Its actual title didn't contain either
    # "distribution map" or "range map" as an exact phrase — just "map" —
    # which the old keyword list missed entirely.
    def handler(request):
        pages = {
            "1": _page(1, "File:Ammodramus maritimus map.svg"),
            "2": _page(2, "File:Seaside Sparrow in marsh grass.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Ammodramus maritimus", "bitmap", thumbnail=True))
    assert result["media_url"] == "https://upload.wikimedia.org/2.jpg"
    assert result["flagged"] is False


def test_search_excludes_given_media_urls(monkeypatch):
    # Backs Test Your Skill's "try another photo" — a different file than
    # one already shown, not a quality judgment on the excluded one.
    def handler(request):
        pages = {
            "1": _page(1, "File:Turdus migratorius A.jpg"),
            "2": _page(2, "File:Turdus migratorius B.jpg"),
        }
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(
        commons._search(
            "Turdus migratorius", "bitmap", thumbnail=True,
            exclude_media_urls=frozenset({"https://upload.wikimedia.org/1.jpg"}),
        )
    )
    assert result["media_url"] == "https://upload.wikimedia.org/2.jpg"


def test_search_returns_none_when_everything_is_excluded(monkeypatch):
    def handler(request):
        pages = {"1": _page(1, "File:Turdus migratorius A.jpg")}
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(
        commons._search(
            "Turdus migratorius", "bitmap", thumbnail=True,
            exclude_media_urls=frozenset({"https://upload.wikimedia.org/1.jpg"}),
        )
    )
    assert result is None


def test_search_requests_full_unhidden_categories_for_a_photo_search(monkeypatch):
    # Regression: real live-data case. A generator search for 10 candidate
    # photos shares ONE `categories` budget across all 10 pages combined
    # (MediaWiki's un-raised default: 10 total, not 10 each) — a 1894
    # hybrid-swallow engraving's categories (including the literal
    # "Petrochelidon pyrrhonota (illustrations)" this filter already looks
    # for) got silently dropped from the response purely because other
    # candidates in the same batch used up the shared budget first, letting
    # the engraving through as an un-flagged "real photo." `cllimit=max`
    # raises that shared budget; `clshow=!hidden` keeps Commons' own
    # license/maintenance bookkeeping categories from eating into it.
    def handler(request):
        url = str(request.url)
        assert "cllimit=max" in url
        assert "clshow=%21hidden" in url or "clshow=!hidden" in url
        pages = {"1": _page(1, "File:Turdus migratorius in Central Park.jpg")}
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    asyncio.run(commons._search("Turdus migratorius", "bitmap", thumbnail=True))


def test_search_does_not_request_categories_params_for_audio(monkeypatch):
    def handler(request):
        url = str(request.url)
        assert "cllimit" not in url
        assert "clshow" not in url
        pages = {"1": _page(1, "File:American Robin nestling begging calls.ogg")}
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    asyncio.run(commons._search("Turdus migratorius", "audio", thumbnail=False))


def test_search_does_not_filter_audio_results(monkeypatch):
    # The specimen-photo problem is photo-specific — an "egg" match in an
    # audio search's title isn't a defect the same way, so audio search
    # keeps taking the single top-ranked hit unfiltered.
    def handler(request):
        assert "gsrlimit=1" in str(request.url)
        assert "categories" not in str(request.url)
        pages = {"1": _page(1, "File:American Robin nestling begging calls.ogg")}
        return httpx.Response(200, request=request, json={"query": {"pages": pages}})

    monkeypatch.setattr(commons.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(commons._search("Turdus migratorius", "audio", thumbnail=False))
    assert result["media_url"] == "https://upload.wikimedia.org/1.jpg"
    assert result["flagged"] is False  # never a quality concern for audio — see _search()'s docstring
