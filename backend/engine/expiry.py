# engine/expiry.py
# ─────────────────────────────────────────────────────────────────────────────
# The simplest engine in the system — pure date arithmetic.
# No ML, no forecasting. Just:
#   today - expiry_date = days_remaining
#   days_remaining < threshold → flag it
#
# Three flag types:
#   EXPIRED          — past expiry date. Must not be dispensed.
#   EXPIRY_CRITICAL  — within 30 days. Urgent.
#   EXPIRY_WARN      — within 90 days. Plan ahead.
#
# Each flag includes value_ksh = quantity × unit_cost
# so the pharmacist knows the financial exposure at a glance.
# A drug expiring with 500 units × Ksh 200 = Ksh 100,000 at risk.
# That number drives urgency more than anything else.
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
from datetime import date
from typing import List, Dict
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import EXPIRY_WARN_DAYS, EXPIRY_CRITICAL_DAYS


def check_expiry(inventory_df: pd.DataFrame) -> List[Dict]:
    """
    Scan inventory for drugs approaching or past expiry.

    Args:
        inventory_df : Validated inventory DataFrame

    Returns:
        List of flag dicts, one per flagged batch.
        Sorted by days_to_expiry ascending (most urgent first).
    """
    flags  = []
    today  = date.today()

    for _, row in inventory_df.iterrows():
        expiry         = row["expiry_date"].date()
        days_remaining = (expiry - today).days
        quantity       = int(row["quantity"])
        unit_cost      = float(row["unit_cost_ksh"])
        value_ksh      = round(quantity * unit_cost, 2)
        drug           = row["drug_name"]
        batch          = row["batch_number"]

        # Skip drugs already out of stock — nothing to flag
        if quantity == 0:
            continue

        if days_remaining < 0:
            flag_type = "EXPIRED"
            message   = (
                f"{drug} (batch {batch}) EXPIRED {abs(days_remaining)} days ago. "
                f"{quantity} units worth Ksh {value_ksh:,.0f} must be removed immediately."
            )

        elif days_remaining <= EXPIRY_CRITICAL_DAYS:
            flag_type = "EXPIRY_CRITICAL"
            message   = (
                f"{drug} (batch {batch}) expires in {days_remaining} days ({expiry}). "
                f"{quantity} units at risk — Ksh {value_ksh:,.0f}. Urgent action required."
            )

        elif days_remaining <= EXPIRY_WARN_DAYS:
            flag_type = "EXPIRY_WARN"
            message   = (
                f"{drug} (batch {batch}) expires in {days_remaining} days ({expiry}). "
                f"{quantity} units — Ksh {value_ksh:,.0f}. Plan disposal or return to supplier."
            )

        else:
            continue   # Drug is fine — no flag

        flags.append({
            "drug_name":      drug,
            "batch_number":   batch,
            "flag_type":      flag_type,
            "days_to_expiry": days_remaining,
            "quantity":       quantity,
            "value_ksh":      value_ksh,
            "message":        message
        })

        print(f"  [expiry] {flag_type}: {drug} — {days_remaining}d — Ksh {value_ksh:,.0f}")

    # Sort most urgent first
    flags.sort(key=lambda x: x["days_to_expiry"])

    print(f"  [expiry] {len(flags)} flags raised")
    return flags
