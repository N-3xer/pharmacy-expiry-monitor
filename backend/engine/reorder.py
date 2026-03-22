# engine/reorder.py
# ─────────────────────────────────────────────────────────────────────────────
# This is the knowledge filter equivalent for PharmWatch.
#
# The problem it solves:
#   Prophet might forecast high demand for a drug.
#   But if there's already plenty of stock, no reorder alert is needed.
#   Conversely, if stock is almost gone and demand is rising, that's urgent.
#
# The logic:
#   days_of_stock = current_quantity / avg_daily_demand
#   if days_of_stock < REORDER_COVER_DAYS → flag for reorder
#
# The movement filter:
#   Only flag drugs that have actually moved recently.
#   A drug with 5 units that nobody has dispensed in 3 months
#   doesn't need a reorder alert — it needs a review.
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
from datetime import date, timedelta
from typing import List, Dict
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import REORDER_COVER_DAYS, MIN_MOVEMENT_30_DAYS, FORECAST_DAYS


def check_reorder(
    inventory_df:  pd.DataFrame,
    demand_forecast: Dict[str, Dict],
    dispensing_df: pd.DataFrame
) -> List[Dict]:
    """
    Compare current stock against forecasted demand.
    Flag drugs that will run out before the reorder window.

    Args:
        inventory_df     : Validated inventory DataFrame
        demand_forecast  : Output from demand.forecast_demand()
        dispensing_df    : Validated dispensing DataFrame (for movement check)

    Returns:
        List of reorder flag dicts.
    """
    flags = []
    today = date.today()
    cutoff_30 = pd.Timestamp(today - timedelta(days=30))

    # Aggregate current stock per drug (sum across all batches)
    stock = (
        inventory_df.groupby("drug_name")["quantity"]
        .sum()
        .to_dict()
    )

    for drug, forecast in demand_forecast.items():
        current_stock = stock.get(drug, 0)
        avg_daily     = forecast["avg_daily"]

        # ── Movement filter ───────────────────────────────────────────────────
        # How many units moved in the last 30 days?
        recent = dispensing_df[
            (dispensing_df["drug_name"] == drug) &
            (dispensing_df["date"] >= cutoff_30)
        ]
        recent_units = int(recent["units"].sum())

        if recent_units < MIN_MOVEMENT_30_DAYS:
            print(f"  [reorder] {drug}: only {recent_units} units moved in 30d — skipping")
            continue

        # ── Days of stock remaining ───────────────────────────────────────────
        if avg_daily <= 0:
            continue   # Drug isn't being used — skip

        days_of_stock = current_stock / avg_daily

        if days_of_stock < REORDER_COVER_DAYS:
            # How many units to order to cover the full forecast window?
            units_needed = max(0, forecast["forecast_units"] - current_stock)

            message = (
                f"{drug}: only {days_of_stock:.0f} days of stock remaining "
                f"(current: {current_stock} units, avg demand: {avg_daily:.1f}/day). "
                f"Reorder ~{units_needed} units to cover next {FORECAST_DAYS} days."
            )

            flags.append({
                "drug_name":      drug,
                "batch_number":   None,
                "flag_type":      "REORDER",
                "days_to_expiry": None,
                "quantity":       current_stock,
                "value_ksh":      None,
                "days_of_stock":  round(days_of_stock, 1),
                "units_needed":   units_needed,
                "forecast_units": forecast["forecast_units"],
                "avg_daily":      avg_daily,
                "reliable":       forecast["reliable"],
                "message":        message
            })

            print(f"  [reorder] ⚠ {drug}: {days_of_stock:.0f}d stock < {REORDER_COVER_DAYS}d threshold")

    print(f"  [reorder] {len(flags)} reorder flags")
    return flags
