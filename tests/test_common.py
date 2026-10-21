import pytest

from extract.common import normalize_path


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://news.example.com/economy/rates/", "/economy/rates"),
        ("/economy/rates/", "/economy/rates"),
        ("/Economy/Rates", "/economy/rates"),
        ("https://news.example.com/markets/gold/?utm_source=rss", "/markets/gold"),
        ("/haber/d%C3%B6viz-kuru/", "/haber/döviz-kuru"),
        ("https://news.example.com/", "/"),
        ("/", "/"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected

def test_ga4_and_rss_paths_match():
    """The join key must be identical from ga4 and rss it comes from."""
    assert normalize_path("/economy/central-bank-holds-rates/") == normalize_path(
        "https://news.example.com/economy/central-bank-holds-rates/"
    )