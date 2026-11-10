from dataclasses import dataclass


@dataclass(frozen=True)
class Scheme:
    scheme_id: str
    name: str
    url: str
    aliases: tuple[str, ...]


SCHEMES: tuple[Scheme, ...] = (
    Scheme(
        scheme_id="hdfc-mid-cap",
        name="HDFC Mid Cap Fund Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        aliases=("hdfc mid cap", "mid cap", "midcap"),
    ),
    Scheme(
        scheme_id="hdfc-small-cap",
        name="HDFC Small Cap Fund Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
        aliases=("hdfc small cap", "small cap", "smallcap"),
    ),
    Scheme(
        scheme_id="hdfc-large-cap",
        name="HDFC Large Cap Fund Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        aliases=("hdfc large cap", "large cap", "largecap"),
    ),
    Scheme(
        scheme_id="hdfc-silver-etf-fof",
        name="HDFC Silver ETF FoF Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        aliases=("silver etf", "silver fof", "silver"),
    ),
    Scheme(
        scheme_id="hdfc-multi-cap",
        name="HDFC Multi Cap Fund Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth",
        aliases=("hdfc multi cap", "multi cap", "multicap"),
    ),
)

SCHEME_BY_ID: dict[str, Scheme] = {scheme.scheme_id: scheme for scheme in SCHEMES}
REQUIRED_GROWW_URLS: tuple[str, ...] = tuple(scheme.url for scheme in SCHEMES)
