# main.py
# ─────────────────────────────────────────────────────────────────────────────
# Routes:
#   POST /ingest/inventory    — upload inventory CSV
#   POST /ingest/dispensing   — upload dispensing records CSV
#   POST /run-checks          — run expiry + demand + reorder + email
#   GET  /flags               — get all active flags for dashboard
#   POST /flags/resolve       — mark a flag as resolved
#   GET  /forecast            — get demand forecast per drug
#   GET  /inventory/summary   — total stock value + expiry overview
#   GET  /health              — ping
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import shutil, os, tempfile
import pandas as pd

from database  import init_db, get_connection
from models    import ResolveRequest
from config    import PHARMACY_NAME

from ingestion.validator  import validate_inventory_csv, validate_dispensing_csv
from engine.expiry        import check_expiry
from engine.demand        import forecast_demand
from engine.reorder       import check_reorder
from alerts.email_alert   import send_alert_email

app = FastAPI(
    title       = f"PharmWatch — {PHARMACY_NAME}",
    description = "Pharmacy expiry alert and demand forecasting system",
    version     = "1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"],
)

# In-memory store for latest uploaded DataFrames
latest_inventory:  pd.DataFrame = pd.DataFrame()
latest_dispensing: pd.DataFrame = pd.DataFrame()


@app.on_event("startup")
def startup():
    init_db()
    print(f"✓ PharmWatch running — {PHARMACY_NAME}")


@app.get("/health")
def health():
    return {"status": "ok", "pharmacy": PHARMACY_NAME, "time": datetime.utcnow().isoformat()}


# ── Ingest inventory ──────────────────────────────────────────────────────────
@app.post("/ingest/inventory")
async def ingest_inventory(file: UploadFile = File(...)):
    """
    Upload current inventory CSV.
    Columns: drug_name, batch_number, expiry_date, quantity, unit_cost_ksh
    Optional: category, supplier
    """
    global latest_inventory

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name

    ok, reason, df = validate_inventory_csv(path)
    os.unlink(path)

    if not ok:
        raise HTTPException(status_code=422, detail=f"Inventory rejected: {reason}")

    latest_inventory = df
    total_value = (df["quantity"] * df["unit_cost_ksh"]).sum()

    return {
        "status":      "accepted",
        "rows":        len(df),
        "drugs":       df["drug_name"].nunique(),
        "total_value_ksh": round(total_value, 2)
    }


# ── Ingest dispensing ─────────────────────────────────────────────────────────
@app.post("/ingest/dispensing")
async def ingest_dispensing(file: UploadFile = File(...)):
    """
    Upload dispensing history CSV.
    Columns: drug_name, date, units
    """
    global latest_dispensing

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name

    ok, reason, df = validate_dispensing_csv(path)
    os.unlink(path)

    if not ok:
        raise HTTPException(status_code=422, detail=f"Dispensing data rejected: {reason}")

    latest_dispensing = df

    return {
        "status": "accepted",
        "rows":   len(df),
        "drugs":  df["drug_name"].nunique(),
        "date_range": {
            "from": str(df["date"].min().date()),
            "to":   str(df["date"].max().date())
        }
    }


# ── Run checks ────────────────────────────────────────────────────────────────
@app.post("/run-checks")
def run_checks(send_email: bool = True):
    """
    Run the full check pipeline:
      1. Expiry scan on inventory
      2. Demand forecast on dispensing history
      3. Reorder check (stock vs forecast)
      4. Save all flags to DB
      5. Send email summary (if send_email=True)
    """
    if latest_inventory.empty:
        raise HTTPException(status_code=400,
            detail="No inventory loaded. Upload via POST /ingest/inventory first.")

    print("\n── PharmWatch checks starting ────────────────────────")

    # Step 1: Expiry
    print("[1/4] Checking expiry...")
    expiry_flags = check_expiry(latest_inventory)

    # Step 2 + 3: Demand + Reorder
    reorder_flags = []
    if not latest_dispensing.empty:
        print("[2/4] Forecasting demand...")
        forecast = forecast_demand(latest_dispensing)

        print("[3/4] Checking reorder levels...")
        reorder_flags = check_reorder(latest_inventory, forecast, latest_dispensing)
    else:
        print("[2/4] No dispensing data — skipping demand forecast")
        print("[3/4] Skipping reorder check")

    # Step 4: Save flags to DB
    print("[4/4] Saving flags...")
    all_flags = expiry_flags + reorder_flags
    conn = get_connection()
    for f in all_flags:
        conn.execute("""
            INSERT INTO flags
            (drug_name, batch_number, flag_type, days_to_expiry, quantity,
             value_ksh, message, flagged_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            f["drug_name"], f.get("batch_number"), f["flag_type"],
            f.get("days_to_expiry"), f.get("quantity"), f.get("value_ksh"),
            f["message"], datetime.utcnow().isoformat()
        ))
    conn.commit()
    conn.close()

    # Step 5: Email
    email_sent = False
    if send_email:
        print("[5/5] Sending email...")
        email_sent = send_alert_email(expiry_flags, reorder_flags)

    print("── Checks complete ────────────────────────────────────\n")

    return {
        "expiry_flags":  len(expiry_flags),
        "reorder_flags": len(reorder_flags),
        "total_flags":   len(all_flags),
        "email_sent":    email_sent,
        "flags":         all_flags
    }


# ── Get flags ─────────────────────────────────────────────────────────────────
@app.get("/flags")
def get_flags(resolved: bool = False, limit: int = 100):
    """Get flags for the dashboard. Default: unresolved only."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM flags
        WHERE resolved = ?
        ORDER BY flagged_at DESC
        LIMIT ?
    """, (1 if resolved else 0, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Resolve a flag ────────────────────────────────────────────────────────────
@app.post("/flags/resolve")
def resolve_flag(req: ResolveRequest):
    """Mark a flag as resolved — pharmacist acknowledged it."""
    conn = get_connection()
    conn.execute("UPDATE flags SET resolved = 1 WHERE id = ?", (req.flag_id,))
    conn.commit()
    conn.close()
    return {"status": "resolved", "flag_id": req.flag_id}


# ── Demand forecast ───────────────────────────────────────────────────────────
@app.get("/forecast")
def get_forecast():
    """Return demand forecast for all drugs with dispensing history."""
    if latest_dispensing.empty:
        raise HTTPException(status_code=400,
            detail="No dispensing data loaded. Upload via POST /ingest/dispensing first.")
    forecast = forecast_demand(latest_dispensing)
    return list(forecast.values())


# ── Inventory summary ─────────────────────────────────────────────────────────
@app.get("/inventory/summary")
def inventory_summary():
    """High-level inventory overview — total value, expiry breakdown."""
    if latest_inventory.empty:
        raise HTTPException(status_code=400, detail="No inventory loaded.")

    from datetime import date
    today = date.today()
    df    = latest_inventory.copy()
    df["value_ksh"]      = df["quantity"] * df["unit_cost_ksh"]
    df["days_to_expiry"] = (pd.to_datetime(df["expiry_date"]).dt.date.apply(
        lambda x: (x - today).days
    ))

    return {
        "total_drugs":        int(df["drug_name"].nunique()),
        "total_batches":      int(len(df)),
        "total_stock_value":  round(df["value_ksh"].sum(), 2),
        "expired_count":      int((df["days_to_expiry"] < 0).sum()),
        "critical_count":     int(((df["days_to_expiry"] >= 0) & (df["days_to_expiry"] <= 30)).sum()),
        "warn_count":         int(((df["days_to_expiry"] > 30) & (df["days_to_expiry"] <= 90)).sum()),
        "healthy_count":      int((df["days_to_expiry"] > 90).sum()),
        "at_risk_value_ksh":  round(df[df["days_to_expiry"] <= 90]["value_ksh"].sum(), 2)
    }
