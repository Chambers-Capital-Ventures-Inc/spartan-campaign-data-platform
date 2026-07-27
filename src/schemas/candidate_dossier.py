from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator

YesNo = Literal["Yes", "No"]
IncumbentStatus = Literal["Incumbent", "Challenger", "Open seat", "Unknown", "Needs verification"]
Confidence = Literal["High", "Medium", "Low", "Needs review"]
DisciplineFlag = Literal["Yes", "No", "Unknown", "Not checked", "Needs verification"]
ScjcChecked = Literal["Yes", "Partial", "No", "Not checked"]

class CandidateDossier(BaseModel):
    candidate_name: str
    party: str
    court_name: str
    court_type: str
    incumbent_status: IncumbentStatus

    state_bar_profile_url: Optional[str] = None
    bar_number: Optional[str] = None
    bar_status: Optional[str] = None
    licensed_since: Optional[str] = None
    public_discipline_flag: DisciplineFlag

    campaign_finance_source: Optional[str] = None
    campaign_finance_url: Optional[str] = None
    filer_id: Optional[str] = None
    total_contributions: Optional[float] = None
    total_expenditures: Optional[float] = None

    oca_case_category: Optional[str] = None
    active_pending_total: Optional[float] = None
    long_pending_count: Optional[float] = None
    long_pending_threshold: Optional[str] = None
    long_pending_pct: Optional[float] = None

    scjc_checked: ScjcChecked
    scjc_result: Optional[str] = None
    overall_confidence: Confidence
    missing_fields: Optional[str] = None
    notes: Optional[str] = None

    source_id: Optional[str] = None
    ingested_at: Optional[str] = None
    verification_status: Optional[str] = None
    source_caveat: Optional[str] = None

    @field_validator("filer_id")
    @classmethod
    def filer_id_must_preserve_leading_zeros(cls, value):
        if value is None:
            return value
        value = str(value)
        if value.isdigit() and len(value) < 8:
            raise ValueError("filer_id should preserve leading zeros, e.g. 00090319")
        return value

    @field_validator("long_pending_pct")
    @classmethod
    def long_pending_pct_between_zero_and_one(cls, value):
        if value is None:
            return value
        if value < 0 or value > 1:
            raise ValueError("long_pending_pct must be between 0 and 1")
        return value