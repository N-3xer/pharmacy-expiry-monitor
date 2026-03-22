# models.py
# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models define the exact shape of data the API accepts.
# FastAPI uses these to validate incoming requests automatically.
# If the data doesn't match the shape, it's rejected before touching any logic.
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from datetime import date


class InventoryRecord(BaseModel):
    """
    One row of inventory data — one batch of one drug.

    Expected CSV columns:
        drug_name, batch_number, expiry_date, quantity, unit_cost_ksh, category, supplier
    """
    drug_name:     str
    batch_number:  str
    expiry_date:   date                          # YYYY-MM-DD
    quantity:      int   = Field(ge=0)           # can be 0 (out of stock)
    unit_cost_ksh: float = Field(gt=0)           # must be positive
    category:      Optional[str] = None
    supplier:      Optional[str] = None

    @field_validator("drug_name")
    @classmethod
    def clean_name(cls, v):
        # Standardise drug names — strip whitespace, title case
        return v.strip().title()


class DispensingRecord(BaseModel):
    """
    One dispensing event — how many units of a drug were dispensed on a date.

    Expected CSV columns:
        drug_name, date, units
    """
    drug_name: str
    date:      date
    units:     int = Field(gt=0)   # must have dispensed at least 1

    @field_validator("drug_name")
    @classmethod
    def clean_name(cls, v):
        return v.strip().title()


class FlagRecord(BaseModel):
    """Shape of a flag returned from the flags table."""
    id:             int
    drug_name:      str
    batch_number:   Optional[str]
    flag_type:      str
    days_to_expiry: Optional[int]
    quantity:       Optional[int]
    value_ksh:      Optional[float]
    message:        str
    flagged_at:     str
    resolved:       int


class ResolveRequest(BaseModel):
    """Mark a flag as resolved (pharmacist acknowledged it)."""
    flag_id: int
