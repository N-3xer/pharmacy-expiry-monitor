# alerts/email_alert.py
# ─────────────────────────────────────────────────────────────────────────────
# Sends a formatted email to the pharmacist with all active flags.
#
# The email is plain text — not HTML — because it needs to be readable
# on any device including old phones and webmail with images blocked.
#
# Uses Python's built-in smtplib — no extra library needed.
# Works with Gmail (use an App Password, not your real password),
# Outlook, or any SMTP server.
#
# Gmail App Password setup:
#   Google Account → Security → 2-Step Verification → App passwords
#   Generate one for "Mail" and put it in your .env as EMAIL_PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT,
    EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, PHARMACY_NAME
)
from database import get_connection


def _build_email_body(expiry_flags: List[Dict], reorder_flags: List[Dict]) -> str:
    """
    Build the plain text email body.
    Structured so the most urgent things appear first.
    """
    lines = []
    now   = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines.append(f"PharmWatch Daily Report — {PHARMACY_NAME}")
    lines.append(f"Generated: {now}")
    lines.append("=" * 60)

    # ── Expired drugs (most critical — top of email) ──────────────────────────
    expired = [f for f in expiry_flags if f["flag_type"] == "EXPIRED"]
    if expired:
        lines.append(f"\n⚠ EXPIRED DRUGS ({len(expired)}) — REMOVE FROM DISPENSING IMMEDIATELY")
        lines.append("-" * 60)
        for f in expired:
            lines.append(f"  • {f['message']}")

    # ── Critical expiry ────────────────────────────────────────────────────────
    critical = [f for f in expiry_flags if f["flag_type"] == "EXPIRY_CRITICAL"]
    if critical:
        lines.append(f"\n⚠ EXPIRING WITHIN 30 DAYS ({len(critical)})")
        lines.append("-" * 60)
        for f in critical:
            lines.append(f"  • {f['message']}")

    # ── Warning expiry ─────────────────────────────────────────────────────────
    warn = [f for f in expiry_flags if f["flag_type"] == "EXPIRY_WARN"]
    if warn:
        lines.append(f"\n⚡ EXPIRING WITHIN 90 DAYS ({len(warn)})")
        lines.append("-" * 60)
        for f in warn:
            lines.append(f"  • {f['message']}")

    # ── Reorder flags ──────────────────────────────────────────────────────────
    if reorder_flags:
        lines.append(f"\n📦 REORDER REQUIRED ({len(reorder_flags)})")
        lines.append("-" * 60)
        for f in reorder_flags:
            reliability = "" if f.get("reliable") else " [forecast based on limited history]"
            lines.append(f"  • {f['message']}{reliability}")

    # ── Summary ────────────────────────────────────────────────────────────────
    total = len(expiry_flags) + len(reorder_flags)
    lines.append("\n" + "=" * 60)
    lines.append(f"Total flags: {total}  |  Expiry: {len(expiry_flags)}  |  Reorder: {len(reorder_flags)}")
    lines.append("Log in to the PharmWatch dashboard to mark flags as resolved.")
    lines.append("=" * 60)

    return "\n".join(lines)


def send_alert_email(expiry_flags: List[Dict], reorder_flags: List[Dict]) -> bool:
    """
    Send the daily alert email to the pharmacist.

    Args:
        expiry_flags  : Flags from expiry.check_expiry()
        reorder_flags : Flags from reorder.check_reorder()

    Returns:
        True if sent successfully, False otherwise.
    """
    total_flags = len(expiry_flags) + len(reorder_flags)

    if total_flags == 0:
        print("  [email] No flags — skipping email")
        return True

    # Build message
    body    = _build_email_body(expiry_flags, reorder_flags)
    subject = f"[PharmWatch] {total_flags} flag(s) require attention — {PHARMACY_NAME}"

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    status = "failed"
    error  = None

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

        status = "sent"
        print(f"  [email] ✓ Sent to {EMAIL_RECIPIENT} — {total_flags} flags")

    except Exception as e:
        error = str(e)
        print(f"  [email] ✗ Failed: {e}")

    # Log the attempt
    conn = get_connection()
    conn.execute("""
        INSERT INTO email_log (recipient, subject, flag_count, status, error, sent_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (EMAIL_RECIPIENT, subject, total_flags, status, error,
          datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    return status == "sent"
