"""
shop_sync.py — Dukaan records ka JSON export/import (Phase 3 sync).

SURVIVAL RULE barqarar: asal records LOCAL shop.db me hi hain.
Ye module sirf un ka poora JSON snapshot banata / wapas lagata
hai taake core/server.py use shop_backup table me rakh sake.

export_json() -> dict:
    {format, exported_at, shop_name,
     customers: [...raw rows...], jobs: [...raw rows...],
     settings: {key: value}}

import_json(payload) -> {"customers": n, "jobs": m}
    Restore = poora replace: pehle jobs, phir customers, phir
    settings saaf karke snapshot wali rows UNHI ids ke saath
    wapas. Aik hi transaction — darmiyan me fail ho to rollback,
    aadha restore kabhi nahi. GUI is se PEHLE hamesha local
    backup (shop_db.backup_db) banati hai + user se confirm
    leti hai.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from core import shop_db

FORMAT = "meer-shop-backup-v1"

_CUSTOMER_COLS = ("id", "name", "phone", "address", "notes",
                  "created_at")
_JOB_COLS = ("id", "ticket_no", "customer_id", "brand", "model",
             "imei", "problem", "status", "est_charges",
             "final_charges", "received_date", "delivered_date",
             "created_at", "updated_at")


def export_json() -> dict:
    """shop.db ka poora snapshot (raw rows, ids ke saath)."""
    shop_db.init_db()
    conn = sqlite3.connect(str(shop_db.db_path()))
    conn.row_factory = sqlite3.Row
    try:
        customers = [dict(r) for r in conn.execute(
            "SELECT * FROM customers ORDER BY id")]
        jobs = [dict(r) for r in conn.execute(
            "SELECT * FROM jobs ORDER BY id")]
        settings = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM settings")}
    finally:
        conn.close()
    return {
        "format": FORMAT,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "shop_name": settings.get("shop_name", ""),
        "customers": customers,
        "jobs": jobs,
        "settings": settings,
    }


def payload_counts(payload) -> tuple[int, int]:
    """(customers, jobs) ki ginti — confirm dialog ke liye."""
    if not isinstance(payload, dict):
        return (0, 0)
    return (len(payload.get("customers") or []),
            len(payload.get("jobs") or []))


def validate_payload(payload) -> None:
    """Ghalat/ajnabi payload par ValueError (restore se pehle)."""
    if not isinstance(payload, dict):
        raise ValueError("Backup payload dict nahi hai.")
    if payload.get("format") != FORMAT:
        raise ValueError(
            f"Backup format pehchana nahi gaya: "
            f"{payload.get('format')!r} (chahiye {FORMAT!r})")
    for key in ("customers", "jobs"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"Backup me '{key}' ki fehrist nahi hai.")
    for c in payload["customers"]:
        if not isinstance(c, dict) or "id" not in c \
                or not str(c.get("name") or "").strip():
            raise ValueError("Backup me aik customer record kharab hai.")
    cust_ids = {c["id"] for c in payload["customers"]}
    for j in payload["jobs"]:
        if not isinstance(j, dict) or "id" not in j \
                or "ticket_no" not in j:
            raise ValueError("Backup me aik job record kharab hai.")
        if j.get("customer_id") not in cust_ids:
            raise ValueError(
                f"Job {j.get('ticket_no')} ka customer backup me "
                "nahi hai — restore rok diya gaya.")


def import_json(payload) -> dict:
    """Snapshot ko shop.db me poora replace karke lagao.

    Return: {"customers": n, "jobs": m}. Validate pehle hota
    hai; likhne ka kaam aik transaction me — fail = rollback.
    """
    validate_payload(payload)
    shop_db.init_db()
    conn = sqlite3.connect(str(shop_db.db_path()))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:  # transaction — commit/rollback khud
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM customers")
            conn.execute("DELETE FROM settings")
            for c in payload["customers"]:
                conn.execute(
                    "INSERT INTO customers(id, name, phone, address,"
                    " notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    tuple(c.get(k, "") if k != "id" else int(c["id"])
                          for k in _CUSTOMER_COLS))
            for j in payload["jobs"]:
                vals = []
                for k in _JOB_COLS:
                    v = j.get(k, "")
                    if k in ("id", "customer_id"):
                        v = int(v)
                    elif k in ("est_charges", "final_charges"):
                        v = float(v or 0)
                    vals.append(v)
                conn.execute(
                    "INSERT INTO jobs(id, ticket_no, customer_id,"
                    " brand, model, imei, problem, status,"
                    " est_charges, final_charges, received_date,"
                    " delivered_date, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                    " ?, ?)", tuple(vals))
            settings = payload.get("settings") or {}
            if not isinstance(settings, dict):
                settings = {}
            if "shop_name" not in settings and payload.get("shop_name"):
                settings["shop_name"] = payload["shop_name"]
            if "ticket_seq" not in settings:
                # Ticket number aage hi barhe — pichla number
                # dobara na aye (jobs ke ticket_no se andaza)
                seq = 0
                for j in payload["jobs"]:
                    t = str(j.get("ticket_no") or "")
                    if t.startswith("T-") and t[2:].isdigit():
                        seq = max(seq, int(t[2:]))
                settings["ticket_seq"] = str(seq)
            for k, v in settings.items():
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?)",
                    (str(k), str(v)))
    finally:
        conn.close()
    return {"customers": len(payload["customers"]),
            "jobs": len(payload["jobs"])}


__all__ = ["FORMAT", "export_json", "import_json",
           "validate_payload", "payload_counts"]
