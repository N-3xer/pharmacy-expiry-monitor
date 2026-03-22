# engine/demand.py
# ─────────────────────────────────────────────────────────────────────────────
# Prophet-based demand forecasting for each drug.
#
# The idea:
#   Historical dispensing records show how many units of each drug
#   leave the pharmacy per day. Prophet learns the pattern —
#   seasonal spikes, weekly cycles, trend direction — and projects
#   it forward FORECAST_DAYS days.
#
#   The total predicted demand over that window tells us:
#   "You will need approximately X units of Amoxicillin in the next 90 days."
#
#   We compare that against current stock.
#   If stock < predicted demand → flag for reorder.
#
# Why Prophet and not just average daily usage × 90?
#   Simple averages miss seasonality. Paracetamol consumption spikes
#   during cold/flu season. Oral Rehydration Salts spike in hot months.
#   A flat average would either overstock off-peak or understock at peak.
#   Prophet catches those patterns given enough history.
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
from typing import List, Dict
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import FORECAST_DAYS, MIN_HISTORY_DAYS

import logging
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


def forecast_demand(dispensing_df: pd.DataFrame) -> Dict[str, Dict]:
    """
    Forecast demand for each drug in the dispensing records.

    Args:
        dispensing_df : Validated dispensing DataFrame
                        columns: drug_name, date, units

    Returns:
        Dict mapping drug_name → forecast summary:
        {
            "drug_name":        "Paracetamol",
            "forecast_units":   450,          ← predicted units needed next 90 days
            "avg_daily":        5.0,          ← average daily demand
            "peak_day":         "2025-04-12", ← day with highest predicted demand
            "history_days":     180,          ← how many days of history was used
            "reliable":         True          ← False if not enough history
        }
    """
    try:
        from prophet import Prophet
    except ImportError:
        print("  [demand] Prophet not installed. Run: pip install prophet")
        return {}

    results = {}
    drugs   = dispensing_df["drug_name"].unique()

    for drug in drugs:
        drug_df = dispensing_df[dispensing_df["drug_name"] == drug].copy()

        # Aggregate to daily totals (in case multiple records per day)
        drug_df = (
            drug_df.groupby("date")["units"]
            .sum()
            .reset_index()
            .rename(columns={"date": "ds", "units": "y"})
        )
        drug_df["ds"] = pd.to_datetime(drug_df["ds"])
        drug_df = drug_df.sort_values("ds")

        history_days = (drug_df["ds"].max() - drug_df["ds"].min()).days

        # Not enough history — fall back to simple average
        if history_days < MIN_HISTORY_DAYS or len(drug_df) < MIN_HISTORY_DAYS:
            avg_daily      = drug_df["y"].mean()
            forecast_units = int(avg_daily * FORECAST_DAYS)
            results[drug]  = {
                "drug_name":     drug,
                "forecast_units": forecast_units,
                "avg_daily":     round(avg_daily, 2),
                "peak_day":      None,
                "history_days":  history_days,
                "reliable":      False   # Flag as unreliable — using simple average
            }
            print(f"  [demand] {drug}: insufficient history ({history_days}d) — using simple average")
            continue

        # ── Train Prophet ─────────────────────────────────────────────────────
        model = Prophet(
            yearly_seasonality  = True,
            weekly_seasonality  = True,   # Dispensing DOES have weekly patterns
            daily_seasonality   = False,
            interval_width      = 0.80
        )
        model.fit(drug_df)

        future   = model.make_future_dataframe(periods=FORECAST_DAYS)
        forecast = model.predict(future)

        # Only look at the future window
        future_only    = forecast.tail(FORECAST_DAYS)
        forecast_units = int(future_only["yhat"].clip(lower=0).sum())
        avg_daily      = round(future_only["yhat"].clip(lower=0).mean(), 2)
        peak_day       = future_only.loc[future_only["yhat"].idxmax(), "ds"].strftime("%Y-%m-%d")

        results[drug] = {
            "drug_name":      drug,
            "forecast_units": forecast_units,
            "avg_daily":      avg_daily,
            "peak_day":       peak_day,
            "history_days":   history_days,
            "reliable":       True
        }

        print(f"  [demand] {drug}: forecast {forecast_units} units over {FORECAST_DAYS}d "
              f"(avg {avg_daily}/day, peak {peak_day})")

    return results
