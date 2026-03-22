# config.py
# ─────────────────────────────────────────────────────────────────────────────
# All tunable values live here.
# When deploying to a real pharmacy, this is the file the pharmacist
# (or IT person) edits. Nothing else needs to change.
# ─────────────────────────────────────────────────────────────────────────────

import os
from dotenv import load_dotenv
load_dotenv()

# ── Pharmacy identity ─────────────────────────────────────────────────────────
PHARMACY_NAME = "KU Health Sciences Pharmacy"
LOCATION      = "Kenyatta University, Nairobi"

# ── Expiry warning windows (days before expiry to flag) ───────────────────────
# WARN     : yellow flag — start planning disposal or return to supplier
# CRITICAL : red flag — urgent action needed
# EXPIRED  : drug is past expiry date — must not be dispensed
EXPIRY_WARN_DAYS     = 90
EXPIRY_CRITICAL_DAYS = 30

# ── Demand forecasting ────────────────────────────────────────────────────────
# How many days ahead to forecast demand
FORECAST_DAYS = 90

# Minimum days of dispensing history needed before Prophet will forecast
# Less than this and the forecast is unreliable
MIN_HISTORY_DAYS = 30

# If current stock covers less than this many days of predicted demand → reorder
REORDER_COVER_DAYS = 14

# ── Reorder filter ────────────────────────────────────────────────────────────
# Only flag a drug for reorder if it has moved at least this many units
# in the last 30 days. Prevents alerts on drugs nobody actually uses.
MIN_MOVEMENT_30_DAYS = 5

# ── Email ─────────────────────────────────────────────────────────────────────
# Set these in your .env file
EMAIL_SENDER    = os.getenv("EMAIL_SENDER",   "floodwatch.alerts@gmail.com")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD", "your_app_password_here")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT","pharmacist@example.com")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST","smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = "pharmwatch.db"
