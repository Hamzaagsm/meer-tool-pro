"""
spd_cert_restore.py — Unisoc Cert (prodnv) RESTORE, FDL level par.

spd_cert_backup ka dusra rukh (SPD-EXPANSION.md §3.3): backup
wala prodnv (IMEI 1/2, BT/WiFi MAC, calibration) device par
wapas likhna. Ye asal cert kharab hone (prodnv corrupt, IMEI
null, calibration gayab) par wohi file hai jo device ko us ki
asal pehchan wapas deti hai.

Discipline — koi shortcut nahi:
  1. **Danger gate SAB SE PEHLE** (core/danger_gate): bhaari
     warning + GUI tasdeeq; baghair tasdeeq device par aik bhi
     koshish nahi hoti, aur tasdeeq audit log me jati hai.
     Wajah saaf hai: galat model ka prodnv likhna device ki
     cert hamesha ke liye kharab kar sakta hai.
  2. **Source lazmi:** backups/spd-cert-*/prodnv.bin (Cert
     Backup op ki banayi hui) — na mile to guided FAIL.
     prerestore wale snapshot folders source NAHI bante.
  3. **Size ka dohra check:** pehle session me device ki
     prodnv ka asal size (partition_list) nikalta hai; source
     file ka size us se byte-to-byte match na kare to restore
     RUK jati hai — galat size ka NV likhna mehfooz nahi.
  4. **BACKUP-FIRST (survival rule):** write se pehle device
     ki MAUJOODA prodnv parh kar backups/spd-cert-prerestore-*/
     me mehfooz hoti hai; snapshot na bane to write NAHI
     hoti — wapsi ka rasta band karke write kabhi nahi.
  5. Teen sessions lagte hain (spd_dump ki sakhtayi: har
     session ke baad phone dobara download mode me lagana
     hota hai) — har marhale par log me wazeh hidayat ati hai.
"""

from datetime import datetime

from core import spd_fdl
from core.danger_gate import danger_gate
from core.runner import BACKUPS_DIR

OP = {
    "id": "spd_cert_restore",
    "category": "SPD / Unisoc",
    "name": "⚠ Unisoc Cert Restore (prodnv, FDL) — KHATARNAAK",
    "engine": "spd_dump",
    "modes": ("SPD",),
    "server_required": False,
    "danger_write": True,
}

_MIN_PRODNV = 16 * 1024
_MAX_PRODNV = 128 * 1024 * 1024


def _latest_cert_backup():
    """Sab se naya spd-cert-* folder jis me prodnv.bin ho.

    prerestore wale folders source NAHI bante (wo write se
    pehle ke snapshot hain, asal backup nahi).
    """
    if not BACKUPS_DIR.is_dir():
        return None
    cands = []
    for d in BACKUPS_DIR.glob("spd-cert-2*"):
        if not d.is_dir() or "prerestore" in d.name:
            continue
        f = d / "prodnv.bin"
        if f.is_file() and f.stat().st_size > 0:
            cands.append(d)
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def run(ctx) -> bool:
    # DANGER GATE sab se pehle — warning + tasdeeq ke baghair
    # device par koi snapshot/write koshish bhi nahi.
    if not danger_gate(ctx, "SPD CERT (prodnv) RESTORE — WRITE"):
        return False
    if not spd_fdl.spd_guard(ctx):
        return False
    session = spd_fdl.prepare_fdl(ctx)
    if session is None:
        return False

    # --- Source: sab se naya mukammal cert backup
    src_dir = _latest_cert_backup()
    if src_dir is None:
        ctx.log("Restore ke liye koi cert backup nahi mila "
                "(backups/spd-cert-*/prodnv.bin) — pehle isi "
                "phone ka 'Unisoc Cert Backup (prodnv, FDL)' "
                "chalao. Baghair backup ke restore ka koi "
                "mehfooz matlab nahi.", "ERROR")
        return False
    src = src_dir / "prodnv.bin"
    src_size = src.stat().st_size
    ctx.log(f"Restore ka source: {src} ({src_size} bytes)",
            "INFO")
    if not (_MIN_PRODNV <= src_size <= _MAX_PRODNV):
        ctx.log(f"Source file ka size ghair-mamooli hai "
                f"({src_size} bytes) — ye saaf prodnv backup "
                "nahi lagta. Restore ROK di gayi.", "ERROR")
        return False

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapdir = BACKUPS_DIR / f"spd-cert-prerestore-{stamp}"
    try:
        snapdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Snapshot folder nahi ban saka: {e}", "ERROR")
        return False
    plist = snapdir / "partitions.xml"

    # --- Session 1: device ki prodnv ka asal size
    ctx.log("Session 1/3: partition list parhi ja rahi hai "
            "(device ki prodnv ka asal size maloom karne ke "
            "liye)...", "INFO")
    ctx.progress(15, "Session 1: partition list...")
    cmd = spd_fdl.session_args(session, ["partition_list",
                                         str(plist), "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0 or not plist.is_file():
        ctx.log(f"Partition list nahi ban saki (exit code {code}) "
                "— baghair asal size ke restore andaze se NAHI "
                "hoga. FDL/driver ki wajah upar ki lines me "
                "dekho.", "ERROR")
        return False
    try:
        parts = spd_fdl.parse_partition_xml(
            plist.read_text(encoding="utf-8", errors="ignore"))
    except OSError as e:
        ctx.log(f"Partition list parhi nahi ja saki: {e}", "ERROR")
        return False
    size = parts.get("prodnv")
    if not size or not (_MIN_PRODNV <= size <= _MAX_PRODNV):
        ctx.log("Partition list me 'prodnv' ka saaf size nahi "
                f"mila (mila: {size}) — is model par cert "
                "restore is raste se mehfooz nahi. Restore "
                "NAHI hua.", "ERROR")
        return False
    ctx.log(f"Device ki prodnv size: {size} bytes "
            f"({size / 1024:.0f} KiB)", "INFO")
    if src_size != size:
        ctx.log(f"Source backup ka size ({src_size}) device ki "
                f"prodnv ({size}) se match NAHI karta — ye kisi "
                "aur model/haalat ka backup lagta hai. Galat "
                "size ka prodnv likhna cert kharab kar dega, "
                "is liye restore ROK di gayi hai.", "ERROR")
        return False

    # --- Session 2: BACKUP-FIRST — maujooda prodnv mehfooz
    ctx.log("Session 1 mukammal. **Ab phone ko dobara download "
            "mode me lagao** — pehle device ki MAUJOODA prodnv "
            "ka snapshot liya jayega (baghair snapshot write "
            "NAHI hogi).", "WARN")
    ctx.progress(40, "Session 2: maujooda prodnv ka snapshot...")
    snap = snapdir / "prodnv.bin"
    cmd = spd_fdl.session_args(session, [
        "read_part", "prodnv", "0", str(size), str(snap),
        "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0 or not snap.is_file() \
            or snap.stat().st_size != size:
        got = snap.stat().st_size if snap.is_file() else 0
        ctx.log(f"Pre-restore snapshot NAHI ban saka (exit "
                f"code {code}, file {got} bytes) — is halat me "
                "write karna wapsi ka rasta band kar dega, is "
                "liye restore ROK di gayi hai. Pehle snapshot "
                "ki nakami ki wajah (upar ki lines) theek karo.",
                "ERROR")
        return False
    ctx.log(f"Snapshot mehfooz: {snap} ({size} bytes) — write "
            "ke baad bhi asal haal yahan se wapas mil sakta "
            "hai (is folder ko source bana kar yehi op dobara "
            "chalane se pehle isay kisi spd-cert-* naam wale "
            "folder me rakhna hoga).", "OK")

    # --- Session 3: asal write
    ctx.log("Snapshot mukammal. **Ab phone ko dobara download "
            "mode me lagao** — ab source backup ki prodnv "
            "device par likhi jayegi.", "WARN")
    ctx.progress(70, "Session 3: prodnv write ho raha hai...")
    cmd = spd_fdl.session_args(session, [
        "write_part", "prodnv", str(src), "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"prodnv write fail hua (spd_dump exit code "
                f"{code}). Device ki pichli haalat ka snapshot "
                f"yahan mehfooz hai: {snap} — asal lines upar "
                "dekho (FDL/driver/session ki wajah).", "ERROR")
        return False
    ctx.log(f"Cert (prodnv) restore mukammal: {src} device par "
            "likh diya gaya. Phone on karke *#06# se IMEI aur "
            "dabbe wale number se mila kar tasdeeq karo; WiFi/"
            "BT on karke MAC bhi check kar lo.", "OK")
    ctx.log(f"Note: write se pehle wali haalat ka snapshot: "
            f"{snap}", "INFO")
    ctx.progress(95, "Cert restore mukammal")
    return True
