from pydantic import BaseModel, ConfigDict, Field


class Holding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    sector: str | None = None
    weight: str | None = None


class SchemeFact(BaseModel):
    """One captured scheme record. Labeled values stay null when the page omitted them."""

    model_config = ConfigDict(extra="ignore")

    scheme_id: str
    name: str
    category: str | None = None
    riskometer: str | None = None
    expense_ratio: str | None = None
    exit_load: str | None = None
    minimum_sip: str | None = None
    minimum_lumpsum: str | None = None
    minimum_additional: str | None = None
    nav_value: str | None = None
    nav_date: str | None = None
    aum: str | None = None
    benchmark: str | None = None
    fund_manager: str | None = None
    stamp_duty: str | None = None
    tax_note: str | None = None
    holdings: list[Holding] = Field(default_factory=list)
    source_url: str
    authority: str
    accessed_at: str
    sid_url: str | None = None
