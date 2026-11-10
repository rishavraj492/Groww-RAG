from app.services.registry import SCHEMES

EXPECTED = (
    (
        "hdfc-mid-cap",
        "HDFC Mid Cap Fund Direct Growth",
        "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        ("hdfc mid cap", "mid cap", "midcap"),
    ),
    (
        "hdfc-small-cap",
        "HDFC Small Cap Fund Direct Growth",
        "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
        ("hdfc small cap", "small cap", "smallcap"),
    ),
    (
        "hdfc-large-cap",
        "HDFC Large Cap Fund Direct Growth",
        "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        ("hdfc large cap", "large cap", "largecap"),
    ),
    (
        "hdfc-silver-etf-fof",
        "HDFC Silver ETF FoF Direct Growth",
        "https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        ("silver etf", "silver fof", "silver"),
    ),
    (
        "hdfc-multi-cap",
        "HDFC Multi Cap Fund Direct Growth",
        "https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth",
        ("hdfc multi cap", "multi cap", "multicap"),
    ),
)


def test_registry_lists_exactly_the_five_schemes():
    assert len(SCHEMES) == 5
    assert [(scheme.scheme_id, scheme.name, scheme.url, scheme.aliases) for scheme in SCHEMES] == list(EXPECTED)
    assert len({scheme.scheme_id for scheme in SCHEMES}) == 5
    assert len({scheme.url for scheme in SCHEMES}) == 5
