"""
shop_db.py — Dukaan ke records: Customer Manager + Repair Jobs.

SURVIVAL RULE (SERVER-EDITION-BRIEF.md): customer / repair records
ki ASAL jagah LOCAL hai. Koi server nahi, koi network call nahi —
is module me network ka koi istemal hai hi nahi.

DB file ki jagah (tay shuda faisla):
    tools/shop.db
    (TOOLS_DIR — frozen onefile EXE ke barabar wala tools/ folder;
    dev/source mode me project ka tools/ folder.)
Wajah: EXE update hone par sirf EXE badalta hai, tools/ ke andar
ka data (loaders, models, aur ab shop.db) mehfooz rehta hai.
Yehi pattern tools/mdm-models.json aur tools/imei-audit.log ka
hai jo pehle se chal raha hai.

Test hook: environment variable MEER_SHOP_DB kisi aur path par
DB rakh sakta hai (headless tests ke liye) — aam istemal me ye
kabhi set nahi hota.

Schema:
    customers(id, name, phone, address, notes, created_at)
    jobs(id, ticket_no UNIQUE, customer_id -> customers.id,
         brand, model, imei, problem, status,
         est_charges, final_charges, received_date, delivered_date,
         created_at, updated_at)
    settings(key PRIMARY KEY, value)   -- shop_name, ticket_seq

Ticket number: settings.ticket_seq counter se "T-0001" format.
Status ki pakki fehrist: STATUSES. Status "Delivered" hone par
delivered_date khali ho to aaj ki date khud lag jati hai.

IMEI yahan SIRF record ke liye hai (job card par device ki
pehchan) — is module se koi device write kabhi nahi hota.
"""

from __future__ import annotations

import csv
import html
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from core.runner import APP_ROOT, TOOLS_DIR

STATUSES = ("Received", "In Progress", "Done", "Delivered")
DEFAULT_SHOP_NAME = "MEER Tool Pro"


# ------------------------------------------------------------ path / db --
def db_path() -> Path:
    """shop.db ka asal rasta (env override sirf tests ke liye)."""
    override = os.environ.get("MEER_SHOP_DB", "").strip()
    if override:
        return Path(override)
    return TOOLS_DIR / "shop.db"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> Path:
    """Tables + default settings banao (idempotent). DB path wapas."""
    p = path or db_path()
    conn = _connect(p)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_no TEXT NOT NULL UNIQUE,
                customer_id INTEGER NOT NULL
                    REFERENCES customers(id),
                brand TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                imei TEXT NOT NULL DEFAULT '',
                problem TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Received',
                est_charges REAL NOT NULL DEFAULT 0,
                final_charges REAL NOT NULL DEFAULT 0,
                received_date TEXT NOT NULL DEFAULT '',
                delivered_date TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            INSERT OR IGNORE INTO settings(key, value)
                VALUES ('shop_name', '%s');
            INSERT OR IGNORE INTO settings(key, value)
                VALUES ('ticket_seq', '0');
            """ % DEFAULT_SHOP_NAME)
        conn.commit()
    finally:
        conn.close()
    return p


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_dict(row) -> dict | None:
    return dict(row) if row is not None else None


# -------------------------------------------------------------- settings --
def get_setting(key: str, default: str = "") -> str:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?",
                           (key,)).fetchone()
        return row["value"] if row is not None else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def shop_name() -> str:
    return get_setting("shop_name", DEFAULT_SHOP_NAME) or DEFAULT_SHOP_NAME


# ------------------------------------------------------------- customers --
def add_customer(name: str, phone: str = "", address: str = "",
                 notes: str = "") -> int:
    """Naya customer. Naam lazmi hai — khali ho to ValueError."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Customer ka naam lazmi hai.")
    init_db()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO customers(name, phone, address, notes, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (name, (phone or "").strip(), (address or "").strip(),
             (notes or "").strip(), _now()))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_customer(customer_id: int, name: str, phone: str = "",
                    address: str = "", notes: str = "") -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Customer ka naam lazmi hai.")
    init_db()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE customers SET name=?, phone=?, address=?, notes=? "
            "WHERE id=?",
            (name, (phone or "").strip(), (address or "").strip(),
             (notes or "").strip(), int(customer_id)))
        conn.commit()
    finally:
        conn.close()


def get_customer(customer_id: int) -> dict | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM customers WHERE id=?",
                           (int(customer_id),)).fetchone()
        return _row_dict(row)
    finally:
        conn.close()


_CUSTOMER_SELECT = (
    "SELECT c.*, (SELECT COUNT(*) FROM jobs j "
    "WHERE j.customer_id = c.id) AS jobs_count FROM customers c")


def list_customers() -> list[dict]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            _CUSTOMER_SELECT + " ORDER BY c.name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_customers(query: str = "") -> list[dict]:
    """Naam / phone / address me talash (khali query = tamam)."""
    q = (query or "").strip()
    if not q:
        return list_customers()
    init_db()
    conn = _connect()
    try:
        like = f"%{q}%"
        rows = conn.execute(
            _CUSTOMER_SELECT +
            " WHERE c.name LIKE ? OR c.phone LIKE ? OR c.address LIKE ?"
            " ORDER BY c.name COLLATE NOCASE",
            (like, like, like)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ------------------------------------------------------------------ jobs --
def _next_ticket(conn) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key='ticket_seq'"
                       ).fetchone()
    seq = int(row["value"]) + 1 if row is not None else 1
    conn.execute(
        "INSERT INTO settings(key, value) VALUES ('ticket_seq', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(seq),))
    return f"T-{seq:04d}"


def add_job(customer_id: int, brand: str = "", model: str = "",
            imei: str = "", problem: str = "", status: str = "Received",
            est_charges: float = 0, final_charges: float = 0,
            received_date: str = "",
            delivered_date: str = "") -> tuple[int, str]:
    """Naya repair job. (job_id, ticket_no) wapas karta hai.

    Customer ka hona lazmi hai, masla (problem) lazmi hai;
    received_date khali ho to aaj ki date; status Delivered ho
    aur delivered_date khali ho to wo bhi aaj ki date.
    """
    if status not in STATUSES:
        raise ValueError(f"Status ghalat hai: {status}")
    problem = (problem or "").strip()
    if not problem:
        raise ValueError("Masla (problem) likhna lazmi hai.")
    init_db()
    conn = _connect()
    try:
        cust = conn.execute("SELECT id FROM customers WHERE id=?",
                            (int(customer_id),)).fetchone()
        if cust is None:
            raise ValueError("Customer pehle banao ya list se select "
                             "karo — job baghair customer ke nahi banta.")
        received_date = (received_date or "").strip() or _today()
        delivered_date = (delivered_date or "").strip()
        if status == "Delivered" and not delivered_date:
            delivered_date = _today()
        ticket = _next_ticket(conn)
        now = _now()
        cur = conn.execute(
            "INSERT INTO jobs(ticket_no, customer_id, brand, model, "
            "imei, problem, status, est_charges, final_charges, "
            "received_date, delivered_date, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket, int(customer_id), (brand or "").strip(),
             (model or "").strip(), (imei or "").strip(), problem,
             status, float(est_charges or 0), float(final_charges or 0),
             received_date, delivered_date, now, now))
        conn.commit()
        return int(cur.lastrowid), ticket
    finally:
        conn.close()


_JOB_FIELDS = ("customer_id", "brand", "model", "imei", "problem",
               "status", "est_charges", "final_charges",
               "received_date", "delivered_date")


def update_job(job_id: int, **fields) -> None:
    """Job ke fields badlo. Status 'Delivered' ho jaye aur
    delivered_date khali ho to aaj ki date khud lag jati hai."""
    unknown = set(fields) - set(_JOB_FIELDS)
    if unknown:
        raise ValueError(f"Job ke ajnabi fields: {sorted(unknown)}")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"Status ghalat hai: {fields['status']}")
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=?",
                           (int(job_id),)).fetchone()
        if row is None:
            raise ValueError("Job nahi mila.")
        merged = dict(row)
        merged.update(fields)
        # Wahid auto-rule: status Delivered ho jaye aur date khali
        # ho to aaj ki date lag jati hai. Date kabhi khud saaf
        # nahi hoti (record mehfooz rehta hai).
        if merged["status"] == "Delivered" and \
                not str(merged.get("delivered_date") or "").strip():
            merged["delivered_date"] = _today()
        sets = ", ".join(f"{k}=?" for k in _JOB_FIELDS)
        vals = [merged[k] for k in _JOB_FIELDS]
        for k in ("est_charges", "final_charges"):
            vals[_JOB_FIELDS.index(k)] = float(merged[k] or 0)
        vals[_JOB_FIELDS.index("customer_id")] = int(merged["customer_id"])
        conn.execute(
            f"UPDATE jobs SET {sets}, updated_at=? WHERE id=?",
            (*vals, _now(), int(job_id)))
        conn.commit()
    finally:
        conn.close()


def set_job_status(job_id: int, status: str) -> None:
    """Sirf status badlo (quick buttons ke liye)."""
    update_job(job_id, status=status)


def get_job(job_id: int) -> dict | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT j.*, c.name AS customer_name, "
            "c.phone AS customer_phone FROM jobs j "
            "JOIN customers c ON c.id = j.customer_id WHERE j.id=?",
            (int(job_id),)).fetchone()
        return _row_dict(row)
    finally:
        conn.close()


_JOB_SELECT = (
    "SELECT j.*, c.name AS customer_name, c.phone AS customer_phone "
    "FROM jobs j JOIN customers c ON c.id = j.customer_id")


def list_jobs(status: str | None = None) -> list[dict]:
    init_db()
    conn = _connect()
    try:
        if status and status != "All":
            rows = conn.execute(
                _JOB_SELECT + " WHERE j.status=? ORDER BY j.id DESC",
                (status,)).fetchall()
        else:
            rows = conn.execute(
                _JOB_SELECT + " ORDER BY j.id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_jobs(query: str = "", status: str | None = None) -> list[dict]:
    """Ticket / customer naam / phone / brand / model me talash."""
    q = (query or "").strip()
    jobs = list_jobs(status=status)
    if not q:
        return jobs
    ql = q.lower()

    def hit(j):
        hay = " ".join(str(j.get(k) or "") for k in
                       ("ticket_no", "customer_name", "customer_phone",
                        "brand", "model", "problem")).lower()
        return ql in hay

    return [j for j in jobs if hit(j)]


def customer_jobs(customer_id: int) -> list[dict]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            _JOB_SELECT + " WHERE j.customer_id=? ORDER BY j.id DESC",
            (int(customer_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------- stats --
def stats(today: str | None = None) -> dict:
    """Dashboard ke number: aaj ke jobs, pending, kul customers/jobs."""
    today = today or _today()
    init_db()
    conn = _connect()
    try:
        def one(sql, args=()):
            return int(conn.execute(sql, args).fetchone()[0])

        return {
            "today_jobs": one(
                "SELECT COUNT(*) FROM jobs WHERE received_date=?",
                (today,)),
            "pending_jobs": one(
                "SELECT COUNT(*) FROM jobs WHERE status != 'Delivered'"),
            "total_customers": one("SELECT COUNT(*) FROM customers"),
            "total_jobs": one("SELECT COUNT(*) FROM jobs"),
        }
    finally:
        conn.close()


# --------------------------------------------------------------- receipt --
def fmt_money(value) -> str:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"


def receipt_data(job: dict, customer: dict | None) -> dict:
    """Receipt ke tamam fields aik saaf dict me (HTML/text dono ke liye)."""
    cust = customer or {}
    device = " ".join(x for x in (str(job.get("brand") or "").strip(),
                                  str(job.get("model") or "").strip()) if x)
    return {
        "shop": shop_name(),
        "ticket": job.get("ticket_no", ""),
        "customer": cust.get("name") or job.get("customer_name", ""),
        "phone": cust.get("phone") or job.get("customer_phone", ""),
        "address": cust.get("address", ""),
        "device": device or "—",
        "imei": job.get("imei", ""),
        "problem": job.get("problem", ""),
        "status": job.get("status", ""),
        "est": fmt_money(job.get("est_charges")),
        "final": fmt_money(job.get("final_charges")),
        "received": job.get("received_date", ""),
        "delivered": job.get("delivered_date", ""),
        "printed": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def receipt_html(job: dict, customer: dict | None) -> str:
    """Printable HTML receipt — browser me khol kar print hoti hai."""
    d = receipt_data(job, customer)

    def e(x):
        return html.escape(str(x or ""))

    imei_row = (f"<tr><td>IMEI</td><td>{e(d['imei'])}</td></tr>"
                if d["imei"] else "")
    addr_row = (f"<tr><td>Address</td><td>{e(d['address'])}</td></tr>"
                if d["address"] else "")
    del_row = (f"<tr><td>Delivered</td><td>{e(d['delivered'])}</td></tr>"
               if d["delivered"] else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Receipt {e(d['ticket'])} — {e(d['shop'])}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
  .box {{ max-width: 640px; margin: 0 auto; border: 2px solid #111;
         padding: 20px 24px; }}
  h1 {{ margin: 0 0 2px; font-size: 24px; text-align: center; }}
  .sub {{ text-align: center; color: #555; margin-bottom: 14px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #ddd;
        vertical-align: top; }}
  td:first-child {{ width: 150px; color: #555; font-weight: bold; }}
  .final {{ font-size: 18px; font-weight: bold; }}
  .foot {{ margin-top: 16px; text-align: center; color: #555;
           font-size: 12px; }}
  @media print {{ body {{ margin: 0; }} .box {{ border: none; }} }}
</style>
</head>
<body>
<div class="box">
  <h1>{e(d['shop'])}</h1>
  <div class="sub">Mobile Repairing — Repair Receipt</div>
  <table>
    <tr><td>Ticket No</td><td><b>{e(d['ticket'])}</b></td></tr>
    <tr><td>Customer</td><td>{e(d['customer'])}</td></tr>
    <tr><td>Phone</td><td>{e(d['phone'])}</td></tr>
    {addr_row}
    <tr><td>Device</td><td>{e(d['device'])}</td></tr>
    {imei_row}
    <tr><td>Problem</td><td>{e(d['problem'])}</td></tr>
    <tr><td>Status</td><td>{e(d['status'])}</td></tr>
    <tr><td>Received</td><td>{e(d['received'])}</td></tr>
    {del_row}
    <tr><td>Estimated Charges</td><td>Rs {e(d['est'])}</td></tr>
    <tr><td>Final Charges</td><td class="final">Rs {e(d['final'])}</td></tr>
  </table>
  <div class="foot">Printed: {e(d['printed'])} · Shukriya! — {e(d['shop'])}</div>
</div>
</body>
</html>
"""


def receipt_text(job: dict, customer: dict | None) -> str:
    """Seedhi text receipt (notepad/print ke liye)."""
    d = receipt_data(job, customer)
    lines = [
        "=" * 46,
        str(d["shop"]).center(46),
        "Mobile Repairing — Repair Receipt".center(46),
        "=" * 46,
        f"Ticket No : {d['ticket']}",
        f"Customer  : {d['customer']}",
        f"Phone     : {d['phone']}",
    ]
    if d["address"]:
        lines.append(f"Address   : {d['address']}")
    lines.append(f"Device    : {d['device']}")
    if d["imei"]:
        lines.append(f"IMEI      : {d['imei']}")
    lines += [
        f"Problem   : {d['problem']}",
        f"Status    : {d['status']}",
        f"Received  : {d['received']}",
    ]
    if d["delivered"]:
        lines.append(f"Delivered : {d['delivered']}")
    lines += [
        "-" * 46,
        f"Estimated : Rs {d['est']}",
        f"FINAL     : Rs {d['final']}",
        "=" * 46,
        f"Printed: {d['printed']} · Shukriya!",
    ]
    return "\n".join(lines) + "\n"


def receipts_dir() -> Path:
    d = APP_ROOT / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    return d


# -------------------------------------------------------- backup/export --
def backup_db(dest_dir: Path | None = None) -> Path:
    """shop.db ki mehfooz copy (sqlite backup API se, live DB par
    bhi saaf). Default jagah: backups/ folder (APP_ROOT ke andar)."""
    init_db()
    dest_dir = Path(dest_dir) if dest_dir else (APP_ROOT / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"shop-backup-{stamp}.db"
    src = _connect()
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest


def export_csv(dest_dir: Path) -> tuple[Path, Path]:
    """customers.csv + jobs.csv (utf-8-sig — Excel me saaf khulta
    hai, Urdu naam bhi theek nazar ate hain)."""
    init_db()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    cust_path = dest_dir / "customers.csv"
    jobs_path = dest_dir / "jobs.csv"
    customers = list_customers()
    with open(cust_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "phone", "address", "notes",
                    "jobs_count", "created_at"])
        for c in customers:
            w.writerow([c["id"], c["name"], c["phone"], c["address"],
                        c["notes"], c["jobs_count"], c["created_at"]])
    jobs = list_jobs()
    with open(jobs_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ticket_no", "customer", "phone", "brand", "model",
                    "imei", "problem", "status", "est_charges",
                    "final_charges", "received_date", "delivered_date"])
        for j in jobs:
            w.writerow([j["ticket_no"], j["customer_name"],
                        j["customer_phone"], j["brand"], j["model"],
                        j["imei"], j["problem"], j["status"],
                        j["est_charges"], j["final_charges"],
                        j["received_date"], j["delivered_date"]])
    return cust_path, jobs_path


__all__ = [
    "STATUSES", "DEFAULT_SHOP_NAME", "db_path", "init_db",
    "get_setting", "set_setting", "shop_name",
    "add_customer", "update_customer", "get_customer",
    "list_customers", "search_customers",
    "add_job", "update_job", "set_job_status", "get_job",
    "list_jobs", "search_jobs", "customer_jobs",
    "stats", "fmt_money", "receipt_data", "receipt_html",
    "receipt_text", "receipts_dir", "backup_db", "export_csv",
]
