# database.py
# ─────────────────────────────────────────────────────────────────────────────
# Four tables:
#
#   inventory   — current stock: drug, batch, expiry, quantity, cost
#   dispensing  — historical dispensing records: what moved and when
#   flags       — every expiry/reorder flag ever raised
#   email_log   — record of every alert email sent
#
# Why separate inventory and dispensing?
#   Inventory is a snapshot — what's on the shelf RIGHT NOW.
#   Dispensing is a history — what left the shelf OVER TIME.
#   Prophet trains on dispensing history, not inventory snapshots.
#   Expiry alerts come from inventory. Demand forecasts come from dispensing.
#   Keeping them separate means each can be updated independently.
# ─────────────────────────────────────────────────────────────────────────────

import sqlite3
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # ── inventory ─────────────────────────────────────────────────────────────
    # One row per batch of a drug.
    # A drug can have multiple batches with different expiry dates.
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name     TEXT    NOT NULL,
            batch_number  TEXT    NOT NULL,
            expiry_date   TEXT    NOT NULL,   -- YYYY-MM-DD
            quantity      INTEGER NOT NULL,   -- units in stock
            unit_cost_ksh REAL    NOT NULL,   -- cost per unit in KSH
            category      TEXT,              -- e.g. "antibiotic", "analgesic"
            supplier      TEXT,
            updated_at    TEXT    NOT NULL,
            UNIQUE(drug_name, batch_number)   -- no duplicate batches
        )
    """)

    # ── dispensing ────────────────────────────────────────────────────────────
    # One row per dispensing event.
    # If 5 units of Paracetamol were dispensed on 2024-03-01, that's one row.
    c.execute("""
        CREATE TABLE IF NOT EXISTS dispensing (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name   TEXT    NOT NULL,
            date        TEXT    NOT NULL,   -- YYYY-MM-DD
            units       INTEGER NOT NULL,   -- how many dispensed
            recorded_at TEXT    NOT NULL
        )
    """)

    # ── flags ─────────────────────────────────────────────────────────────────
    # Every flag raised by the expiry or demand engine.
    # flag_type: "EXPIRY_WARN", "EXPIRY_CRITICAL", "EXPIRED", "REORDER"
    c.execute("""
        CREATE TABLE IF NOT EXISTS flags (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name     TEXT    NOT NULL,
            batch_number  TEXT,
            flag_type     TEXT    NOT NULL,
            days_to_expiry INTEGER,         -- NULL for reorder flags
            quantity      INTEGER,
            value_ksh     REAL,             -- quantity × unit_cost at time of flag
            message       TEXT    NOT NULL,
            flagged_at    TEXT    NOT NULL,
            resolved      INTEGER DEFAULT 0  -- 1 = pharmacist marked resolved
        )
    """)

    # ── email_log ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS email_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient   TEXT    NOT NULL,
            subject     TEXT    NOT NULL,
            flag_count  INTEGER NOT NULL,
            status      TEXT    NOT NULL,   -- "sent" or "failed"
            error       TEXT,
            sent_at     TEXT    NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("✓ PharmWatch database ready")
