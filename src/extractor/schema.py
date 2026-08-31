"""The canonical output contract.

Seven canonical fields plus two review fields. The scorer compares the seven;
`needs_review` decides which side of the utility table a record lands on.

Do not change the field names or the JSON shape: `score.py` reads them and the
harness reads them. You may add fields; we ignore anything we do not know.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

YEAR_MIN = 1980
YEAR_MAX = 2027


class CanonicalVehicle(BaseModel):
    """One vehicle row in canonical form."""

    source_file: str = Field(..., description="File name the record came from. Part of the join key.")

    vin: Optional[str] = Field(
        None,
        description=(
            "17-character VIN, uppercase, no separators, and satisfying the ISO 3779 "
            "check digit at position 9. A value that fails validation is not a VIN: "
            "emit null rather than passing a corrupt identifier downstream."
        ),
    )
    plate: Optional[str] = Field(
        None, description="License plate, uppercase, alphanumerics only. Part of the join key."
    )
    brand: str = Field(..., description='Manufacturer, uppercase. e.g. "TOYOTA".')
    model: str = Field(..., description='Model line, uppercase, trimmed. e.g. "HILUX", "250".')
    year: int = Field(..., description=f"4-digit model year, {YEAR_MIN}-{YEAR_MAX}.")
    value_mxn: Optional[float] = Field(None, description="Insured value in Mexican pesos.")
    use: Optional[str] = Field(None, description='e.g. "PARTICULAR", "CARGA", "PASAJEROS".')

    needs_review: bool = Field(
        False, description="True if a human must look at this record before it is used."
    )
    review_reason: Optional[str] = Field(
        None,
        description="Short machine-readable reason, required when needs_review is True.",
    )

    @field_validator("year")
    @classmethod
    def _year_in_range(cls, value: int) -> int:
        if not YEAR_MIN <= value <= YEAR_MAX:
            raise ValueError(f"year out of range: {value}")
        return value

    @model_validator(mode="after")
    def _reason_required_when_flagged(self) -> "CanonicalVehicle":
        if self.needs_review and not self.review_reason:
            raise ValueError("review_reason is required when needs_review is True")
        return self


class HeaderDetection(BaseModel):
    row_index: int
    method: str = Field(..., description='"llm" or "fallback"')
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """What POST /extract returns and what the CLI writes, one record per line."""

    source_file: str
    header_detection: HeaderDetection
    records: list[CanonicalVehicle] = Field(default_factory=list)
    rejected_rows: int = 0
    warnings: list[str] = Field(default_factory=list)
    llm_calls: int = 0
