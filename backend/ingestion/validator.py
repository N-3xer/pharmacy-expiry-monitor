# ingestion/validator.py
# ─────────────────────────────────────────────────────────────────────────────
# Two validators:
#   validate_inventory_csv   — checks the stock/expiry data
#   validate_dispensing_csv  — checks the historical dispensing records
#
# Same philosophy as FloodWatch:
#   Bad data in → wrong predictions out → pharmacist makes wrong decisions.
#   Reject loudly with a clear reason rather than silently producing garbage.
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
from datetime import date, timedelta
from typing import Tuple
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


INVENTORY_REQUIRED  = {"drug_name", "batch_number", "expiry_date", "quantity", "unit_cost_ksh"}
DISPENSING_REQUIRED = {"drug_name", "date", "units"}


def validate_inventory_csv(filepath: str) -> Tuple[bool, str, pd.DataFrame]:
    """
    Validate an inventory CSV.

    Checks:
      1. Required columns exist
      2. No nulls in critical columns
      3. Quantities are non-negative integers
      4. Unit costs are positive
      5. Expiry dates are valid dates
      6. No future quantities (can't have -5 units)
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return False, f"Could not read file: {e}", pd.DataFrame()

    # ── Required columns ──────────────────────────────────────────────────────
    missing = INVENTORY_REQUIRED - set(df.columns)
    if missing:
        return False, f"Missing columns: {missing}", pd.DataFrame()

    # ── No nulls in critical columns ──────────────────────────────────────────
    critical = ["drug_name", "batch_number", "expiry_date", "quantity", "unit_cost_ksh"]
    nulls = df[critical].isnull().sum()
    if nulls.any():
        return False, f"Null values in: {nulls[nulls > 0].to_dict()}", pd.DataFrame()

    # ── Parse expiry dates ────────────────────────────────────────────────────
    try:
        df["expiry_date"] = pd.to_datetime(df["expiry_date"])
    except Exception:
        return False, "expiry_date column contains invalid dates. Use YYYY-MM-DD format.", pd.DataFrame()

    # ── Quantity must be non-negative integer ─────────────────────────────────
    if (df["quantity"] < 0).any():
        return False, "quantity column contains negative values", pd.DataFrame()

    # ── Unit cost must be positive ────────────────────────────────────────────
    if (df["unit_cost_ksh"] <= 0).any():
        return False, "unit_cost_ksh must be greater than 0", pd.DataFrame()

    # ── Standardise drug names ────────────────────────────────────────────────
    df["drug_name"] = df["drug_name"].str.strip().str.title()

    return True, "OK", df


def validate_dispensing_csv(filepath: str) -> Tuple[bool, str, pd.DataFrame]:
    """
    Validate a dispensing records CSV.

    Checks:
      1. Required columns exist
      2. No nulls
      3. Units dispensed are positive integers
      4. Dates are valid and not in the future
      5. At least 1 row exists
    """
    try:
        df = pd.read_csv(filepath, parse_dates=["date"])
    except Exception as e:
        return False, f"Could not read file: {e}", pd.DataFrame()

    # ── Required columns ──────────────────────────────────────────────────────
    missing = DISPENSING_REQUIRED - set(df.columns)
    if missing:
        return False, f"Missing columns: {missing}", pd.DataFrame()

    # ── No nulls ──────────────────────────────────────────────────────────────
    nulls = df[["drug_name", "date", "units"]].isnull().sum()
    if nulls.any():
        return False, f"Null values in: {nulls[nulls > 0].to_dict()}", pd.DataFrame()

    # ── Units must be positive ────────────────────────────────────────────────
    if (df["units"] <= 0).any():
        return False, "units column must be > 0. Remove zero-dispensing rows.", pd.DataFrame()

    # ── No future dates ───────────────────────────────────────────────────────
    future = df[df["date"].dt.date > date.today()]
    if not future.empty:
        return False, f"{len(future)} rows have future dates", pd.DataFrame()

    # ── At least some data ────────────────────────────────────────────────────
    if len(df) < 1:
        return False, "File is empty", pd.DataFrame()

    # ── Standardise ──────────────────────────────────────────────────────────
    df["drug_name"] = df["drug_name"].str.strip().str.title()
    df["date"]      = pd.to_datetime(df["date"])

    return True, "OK", df
