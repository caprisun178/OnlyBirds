from app.dao.commons import _strip_html, format_attribution


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
