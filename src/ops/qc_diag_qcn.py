"""
qc_diag_qcn.py — QCN / NV Backup & Restore via Diag (NATIVE, Qualcomm).

RESEARCH-2 §8.8 / §9.6: "QCN / NV backup & restore via Diag
(Qualcomm) — Fully public + official free tool: QPST v2.7.497
QCN backup/restore + EFS karta hai; Diag-enable dialer codes se
(*#*#13491#*#* Xiaomi, *#801# OnePlus, *#*#73694364#*#*
HyperOS 2.0) ya `adb shell setprop sys.usb.config diag,adb`
(root). MEER Diag-enable + QCN backup/restore NATIVELY DIAG
protocol (open) se implement kar sakta hai."

Ye op wahi native implementation hai — core/qc_diag.py par:
DIAG_VERNO_F (0) probe → DIAG_NV_READ_F (38) / DIAG_NV_WRITE_F
(39) se NV items → MEER QCN v1 file (item u16 LE, len u16 LE,
data). **Koi vendor tool (QFIL/QPST) MEER ke andar nahi khulta**
— purane qc_qcn_backup/qc_qcn_restore guide-only (manual_open_
guide) the; ye op asal transfer khud karta hai. QPST guide
un ke andar ab bhi maujood hai (interchange bench-pending).

Modes (GUI param `qcn_mode`):
  - "backup" (default): curated NV items (ESN 0, IMEI 550
    read-only, factory-data 2497) + `nv_items` param se extra
    items → tools/qcn/<model>-diag-<date>.qcn → re-read verify.
  - "restore": tools/qcn/ ki latest (ya `qcn_file` param wali)
    MEER QCN file → pehle ESN match (same-device check) →
    pre-restore snapshot → har item write + read-back verify.

IMEI KI HAD (sakht): NV item 550 (IMEI) SIRF backup me PARHA
jata hai — restore me hamesha SKIP hota hai (log me likha
jata hai). IMEI restore sirf existing META restore op ka kaam
hai (original box/sticker only, warning gate, backup-first,
read-back). Is op me IMEI-write ka rasta hai hi nahi.
"""

from datetime import datetime
from pathlib import Path

from core import qc_diag
from core.danger_gate import danger_gate
from ops.qc_qcn_backup import QCN_DIR, diag_enable

OP = {
    "id": "qc_diag_qcn",
    "category": "Qualcomm",
    "name": "QCN / NV Backup & Restore via Diag (Native)",
    "engine": "qc_diag",
    "modes": ("ADB", "DIAG"),
    "server_required": False,
}

DIAG_CODES_GUIDE = (
    "Diag port kholne ke dialer-code raste (phone par khud dial "
    "karen): Xiaomi *#*#13491#*#* · OnePlus *#801# · HyperOS 2.0 "
    "*#*#73694364#*#*. Ya ADB (root): adb shell setprop "
    "sys.usb.config diag,adb. Port Device Manager me 'Qualcomm "
    "HS-USB Diagnostics' (05c6:900e) ana chahiye — port na aye "
    "to stock firmware par diag band hai (ye is raste ki "
    "imaandar hadd hai).")


def _qcn_mode(ctx) -> str:
    mode = str(ctx.params.get("qcn_mode", "backup") or "backup").strip().lower()
    return mode if mode in ("backup", "restore") else "backup"


def _extra_items(ctx):
    """`nv_items` param (comma list) -> sorted unique valid items."""
    raw = str(ctx.params.get("nv_items", "") or "")
    out = []
    bad = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            bad.append(part)
            continue
        if 0 <= n <= qc_diag.MAX_NV_ITEM:
            out.append(n)
        else:
            bad.append(part)
    if bad:
        ctx.log(f"nv_items me ghalat entries ignore ki gayin: "
                f"{', '.join(bad)}", "WARN")
    return sorted(set(out) - set(qc_diag.BACKUP_NV_ITEMS))


def _find_port(ctx):
    """Device panel (DIAG mode) pehle, phir scan — ya None."""
    dev = ctx.device
    if dev is not None and getattr(dev, "mode", "") == "DIAG" \
            and getattr(dev, "port", ""):
        return dev.port
    try:
        ports = qc_diag.find_diag_ports()
    except qc_diag.QcDiagError as e:
        ctx.log(str(e), "ERROR")
        return None
    return ports[0][0] if ports else None


def _ensure_diag_port(ctx):
    """Diag port lao — scan, phir ADB setprop koshish, phir rescan.

    Port na mile to dialer-code guide + False (imaandar FAIL).
    """
    port = _find_port(ctx)
    if port:
        return port
    dev = ctx.device
    if dev is not None and getattr(dev, "mode", "") == "ADB":
        ctx.log("Diag port nahi mila — ADB se diag enable ki "
                "koshish ho rahi hai...", "INFO")
        try:
            diag_enable(ctx)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Diag-enable koshish me error: {e}", "WARN")
        port = _find_port(ctx)
        if port:
            return port
    ctx.log("Qualcomm Diag port nahi mila (05c6:900e).", "ERROR")
    ctx.log(DIAG_CODES_GUIDE, "INFO")
    return None


def _open_session(ctx, port):
    session = qc_diag.QcDiagSession(port)
    try:
        session.open()
    except qc_diag.QcDiagError as e:
        ctx.log(str(e), "ERROR")
        return None
    try:
        version = session.read_version()
    except qc_diag.QcDiagError as e:
        session.close()
        ctx.log(f"Diag VERNO probe fail: {e}", "ERROR")
        return None
    ctx.log(f"Diag session khula: {port} — modem version: {version}",
            "OK")
    return session


def _latest_qcn():
    if not QCN_DIR.is_dir():
        return None
    files = sorted(QCN_DIR.glob("*.qcn"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


# ---------------------------------------------------------------------------
# BACKUP
# ---------------------------------------------------------------------------
def _run_backup(ctx, session) -> bool:
    items_wanted = list(qc_diag.BACKUP_NV_ITEMS) + _extra_items(ctx)
    ctx.log(f"NV backup: {len(items_wanted)} items parhe jayenge "
            f"(curated: ESN 0, IMEI 550 read-only, factory-data "
            f"2497 + extra {len(items_wanted) - 3}). Poori-QCN "
            "(QPST jaisi hazaron items) is build me nahi — ye "
            "core-NV backup hai; QPST method guide ke liye purana "
            "'QCN Backup — Guide' op dekho.", "INFO")
    read, skipped = {}, []
    for item in items_wanted:
        try:
            data = session.nv_read(item)
        except qc_diag.QcDiagError as e:
            skipped.append(item)
            ctx.log(f"NV item {item} nahi parha gaya (skip): {e}",
                    "WARN")
            continue
        read[item] = data
        if item == qc_diag.NV_IMEI_I:
            ctx.log(f"NV 550 (IMEI, read-only backup): "
                    f"{data.decode('ascii', errors='ignore').strip() or data.hex()}",
                    "DATA")
    if not read:
        ctx.log("Koi NV item nahi parha gaya — backup FAIL. Diag "
                "port jawab de raha hai lekin NV read band hai "
                "(kuch firmwares par NV access restricted hota "
                "hai).", "ERROR")
        return False
    if qc_diag.NV_ESN_I not in read and qc_diag.NV_IMEI_I not in read:
        ctx.log("Identity anchor (ESN 0 / IMEI 550) me se koi bhi "
                "nahi parha gaya — backup bekar hota, is liye "
                "FAIL.", "ERROR")
        return False
    try:
        QCN_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"QCN folder nahi ban saka: {e}", "ERROR")
        return False
    dev = ctx.device
    model = (getattr(dev, "model", "") or "qc").replace(" ", "-")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = QCN_DIR / f"{model}-diag-{stamp}.qcn"
    try:
        path.write_bytes(qc_diag.build_qcn_bytes(read))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"QCN file likhna fail hua: {e}", "ERROR")
        return False
    ctx.log(f"QCN backup likhi gayi: {path} ({len(read)} items, "
            f"{path.stat().st_size} bytes; skipped: "
            f"{skipped or 'koi nahi'})", "DATA")
    # Verify: pehle 3 items dobara parh kar file se milao.
    for item in list(read)[:3]:
        try:
            back = session.nv_read(item)
        except qc_diag.QcDiagError as e:
            ctx.log(f"Verify fail — NV item {item} dobara nahi "
                    f"parha gaya: {e}", "ERROR")
            return False
        if back != read[item]:
            ctx.log(f"Verify fail — NV item {item} ka dobara parha "
                    "data file se nahi mila.", "ERROR")
            return False
    ctx.progress(95, "QCN backup mukammal + verify hua")
    ctx.log("QCN/NV backup mukammal — file mehfooz hai aur re-read "
            "verify hua. Note: ye MEER QCN v1 file hai (QPST .qcn "
            "ke saath interchange bench par verify karna baqi "
            "hai).", "OK")
    return True


# ---------------------------------------------------------------------------
# RESTORE
# ---------------------------------------------------------------------------
def _run_restore(ctx, session) -> bool:
    wanted = str(ctx.params.get("qcn_file", "") or "").strip()
    qcn_path = Path(wanted) if wanted else _latest_qcn()
    if qcn_path is None or not qcn_path.is_file():
        ctx.log("tools/qcn/ me koi .qcn backup file nahi mili — "
                "pehle isi device ki 'QCN backup' (is op ka backup "
                "mode) se file banao. Baghair apni file ke restore "
                "mumkin nahi.", "ERROR")
        return False
    try:
        raw = qcn_path.read_bytes()
    except Exception as e:  # noqa: BLE001
        ctx.log(f"QCN file parhna fail hua: {e}", "ERROR")
        return False
    items, why = qc_diag.parse_qcn_bytes(raw)
    if items is None:
        ctx.log(f"QCN file qabool nahi: {why}", "ERROR")
        return False
    ctx.log(f"Restore ki file: {qcn_path.name} ({len(items)} items)",
            "DATA")
    if qc_diag.NV_ESN_I not in items:
        ctx.log("File me ESN (NV item 0) nahi hai — same-device "
                "check mumkin nahi, is liye restore RUK gaya hai. "
                "Sirf MEER ki apni backup file (ESN samet) se "
                "restore hota hai.", "ERROR")
        return False
    # Same-device check: file ka ESN vs device ka maujooda ESN.
    try:
        current_esn = session.nv_read(qc_diag.NV_ESN_I)
    except qc_diag.QcDiagError as e:
        ctx.log(f"Device ka maujooda ESN nahi parha gaya: {e} — "
                "same-device check ke baghair restore nahi hoga.",
                "ERROR")
        return False
    if current_esn != items[qc_diag.NV_ESN_I]:
        ctx.log("⚠️ ESN MISMATCH: file ka ESN device ke maujooda "
                "ESN se nahi milta — ye file kisi DOOSRE device "
                "ki hai. Doosre device ki QCN restore karna phone "
                "brick kar sakta hai. Restore RUK gaya hai.",
                "ERROR")
        return False
    ctx.log("Same-device check pass — file isi device ki hai (ESN "
            "match).", "OK")
    # IMEI skip — hamesha, wazeh tor par.
    if qc_diag.NV_IMEI_I in items:
        ctx.log("NV item 550 (IMEI) file me hai lekin is op me "
                "KABHI nahi likha jayega — skip ho raha hai. IMEI "
                "restore sirf META restore op se (original "
                "box/sticker only).", "WARN")
    to_write = {k: v for k, v in items.items()
                if k != qc_diag.NV_IMEI_I}
    if not to_write:
        ctx.log("File me IMEI ke ilawa koi item nahi — likhne ko "
                "kuch nahi, restore ka koi matlab nahi.", "ERROR")
        return False
    # Pre-restore snapshot (wapsi ka rasta) — pehle, lazmi.
    try:
        QCN_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"QCN folder nahi ban saka: {e}", "ERROR")
        return False
    snapshot = {}
    for item in to_write:
        try:
            snapshot[item] = session.nv_read(item)
        except qc_diag.QcDiagError as e:
            ctx.log(f"Pre-restore snapshot fail (NV item {item} "
                    f"nahi parha gaya: {e}) — baghair wapsi ke "
                    "raste ke write nahi hoga. Restore RUK gaya "
                    "hai.", "ERROR")
            return False
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap_path = QCN_DIR / f"prerestore-{stamp}.qcn"
    try:
        snap_path.write_bytes(qc_diag.build_qcn_bytes(snapshot))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Snapshot file likhna fail hua: {e} — restore RUK "
                "gaya hai.", "ERROR")
        return False
    ctx.log(f"Pre-restore snapshot mehfooz: {snap_path} "
            f"({len(snapshot)} items) — kuch ghalat ho to is file "
            "se wapas restore ho sakta hai.", "INFO")
    # Write + read-back, har item.
    done = []
    for item, data in sorted(to_write.items()):
        ok, evidence = session.nv_write_verified(item, data)
        if not ok:
            ctx.log(f"Restore FAIL — {evidence} (pehle {done} "
                    f"items likhe ja chuke hain; snapshot file "
                    f"{snap_path.name} se wapas restore karo).",
                    "ERROR")
            return False
        done.append(item)
        ctx.log(evidence, "DATA")
    ctx.progress(95, "QCN restore mukammal + verify hua")
    ctx.log(f"QCN/NV restore mukammal — {len(done)} items write + "
            "read-back verify hue (IMEI 550 skip hua). Phone "
            "restart karke *#06# se dabbe wala asal IMEI milao.",
            "OK")
    return True


# ---------------------------------------------------------------------------
def run(ctx) -> bool:
    mode = _qcn_mode(ctx)
    ctx.log(f"QCN / NV via Diag (Native) — mode: {mode.upper()}. "
            "Qualcomm DIAG protocol (VERNO/NV_READ/NV_WRITE, "
            "HDLC) se asal transfer hota hai — koi QFIL/QPST "
            "MEER ke andar nahi khulta.", "INFO")
    if mode == "restore":
        # Destructive NV write — tasdeeq sab se pehle.
        if not danger_gate(ctx, "QCN/NV RESTORE (Diag)"):
            return False
    port = _ensure_diag_port(ctx)
    if port is None:
        return False
    if ctx.is_cancelled():
        ctx.log("User ne rok diya.", "WARN")
        return False
    ctx.log(f"Diag port: {port}", "OK")
    ctx.progress(30, f"Diag session khul raha hai: {port}...")
    session = _open_session(ctx, port)
    if session is None:
        return False
    try:
        if mode == "restore":
            return _run_restore(ctx, session)
        return _run_backup(ctx, session)
    finally:
        session.close()
