# test_pharmwatch.py
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

PASS = "✓"; FAIL = "✗"; results = []

def test(name, fn):
    try:
        fn(); print(f"  {PASS}  {name}"); results.append((name, True, None))
    except Exception as e:
        print(f"  {FAIL}  {name}\n       → {e}"); results.append((name, False, str(e)))

print("\n── PharmWatch tests ───────────────────────────────────────────────────\n")

def t_config():
    from config import EXPIRY_WARN_DAYS, EXPIRY_CRITICAL_DAYS, FORECAST_DAYS
    assert EXPIRY_WARN_DAYS > EXPIRY_CRITICAL_DAYS, "WARN window must be larger than CRITICAL"
    assert FORECAST_DAYS > 0

def t_db():
    from database import init_db, get_connection
    init_db()
    conn = get_connection()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert {"inventory","dispensing","flags","email_log"} <= tables

def t_inv_valid():
    from ingestion.validator import validate_inventory_csv
    ok, reason, df = validate_inventory_csv("data/sample_inventory.csv")
    assert ok, reason
    assert "drug_name" in df.columns

def t_inv_rejects_neg_cost():
    import tempfile, pandas as pd
    from ingestion.validator import validate_inventory_csv
    bad = pd.DataFrame([{"drug_name":"X","batch_number":"B1","expiry_date":"2026-01-01","quantity":10,"unit_cost_ksh":-5}])
    with tempfile.NamedTemporaryFile(suffix=".csv",mode="w",delete=False) as f:
        bad.to_csv(f,index=False); path=f.name
    ok,_,_ = validate_inventory_csv(path); os.unlink(path)
    assert not ok

def t_disp_valid():
    from ingestion.validator import validate_dispensing_csv
    ok, reason, df = validate_dispensing_csv("data/sample_dispensing.csv")
    assert ok, reason
    assert len(df) > 0

def t_expiry_flags():
    import pandas as pd
    from datetime import date, timedelta
    from engine.expiry import check_expiry
    df = pd.DataFrame([
        {"drug_name":"TestDrug","batch_number":"B1",
         "expiry_date": pd.Timestamp(date.today() - timedelta(days=5)),
         "quantity":50,"unit_cost_ksh":10.0}
    ])
    flags = check_expiry(df)
    assert len(flags) == 1
    assert flags[0]["flag_type"] == "EXPIRED"

def t_expiry_skips_zero_stock():
    import pandas as pd
    from datetime import date, timedelta
    from engine.expiry import check_expiry
    df = pd.DataFrame([
        {"drug_name":"EmptyDrug","batch_number":"B1",
         "expiry_date": pd.Timestamp(date.today() + timedelta(days=10)),
         "quantity":0,"unit_cost_ksh":10.0}
    ])
    flags = check_expiry(df)
    assert len(flags) == 0, "Should skip zero-stock drugs"

def t_expiry_value():
    import pandas as pd
    from datetime import date, timedelta
    from engine.expiry import check_expiry
    df = pd.DataFrame([
        {"drug_name":"CostlyDrug","batch_number":"B1",
         "expiry_date": pd.Timestamp(date.today() + timedelta(days=15)),
         "quantity":100,"unit_cost_ksh":50.0}
    ])
    flags = check_expiry(df)
    assert flags[0]["value_ksh"] == 5000.0, "value_ksh should be qty × unit_cost"

test("Config values are sane", t_config)
test("Database initialises all tables", t_db)
test("Inventory CSV validates", t_inv_valid)
test("Validator rejects negative unit cost", t_inv_rejects_neg_cost)
test("Dispensing CSV validates", t_disp_valid)
test("Expiry engine flags expired drug", t_expiry_flags)
test("Expiry engine skips zero-stock drugs", t_expiry_skips_zero_stock)
test("Expiry engine calculates value correctly", t_expiry_value)

passed = sum(1 for _,ok,_ in results if ok)
failed = sum(1 for _,ok,_ in results if not ok)
print(f"\n── Results: {passed}/{len(results)} passed ──────────────────────────────────────")
if failed:
    for name,ok,err in results:
        if not ok: print(f"  {FAIL}  {name}\n       {err}")
    sys.exit(1)
else:
    print("\n  All tests passed.\n"); sys.exit(0)
