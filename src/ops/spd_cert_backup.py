"""
spd_cert_backup.py — Unisoc Cert (prodnv) backup, FDL level par.

MDM List ke Network tab wala Backup Cert ADB se sirf cert ki
MALOOMAT mehfooz karta hai; asal NV partition (prodnv — IMEI 1/2,
BT/WiFi MAC, calibration) ka FDL-level backup ye op deta hai
(REPAIR-METHODS-RESEARCH §3.2/§4 P1#2): wahi file kal ko
prodnv kharab hone par asal cert wapas karne ka zariya hai.

Do sessions lagte hain (spd_dump ki sakhtayi: read_part ko size
pehle se chahiye hota hai):
  Session 1: partition_list — prodnv ka asal size maloom hota hai.
  Session 2: read_part prodnv — poori partition file me ati hai.
Dono ke darmiyan phone dobara download mode me lagana hota hai —
log me wazeh hidayat ati hai aur tool wait karta hai.
Size ka hisaab saaf na bane to op yahin ruk jata hai (andaze se
aadha/zyada read kabhi nahi).
"""

from datetime import datetime

from core import spd_fdl
from core.runner import BACKUPS_DIR

OP = {
    "id": "spd_cert_backup",
    "category": "SPD / Unisoc",
    "name": "Unisoc Cert Backup (prodnv, FDL)",
    "engine": "spd_dump",
    "modes": ("SPD",),
    "server_required": False,
}

_MIN_PRODNV = 16 * 1024
_MAX_PRODNV = 128 * 1024 * 1024


def run(ctx) -> bool:
    if not spd_fdl.spd_guard(ctx):
        return False
    session = spd_fdl.prepare_fdl(ctx)
    if session is None:
        return False

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BACKUPS_DIR / f"spd-cert-{stamp}"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False
    plist = outdir / "partitions.xml"

    # --- Session 1: partition list se prodnv ka size
    ctx.log("Session 1/2: partition list parhi ja rahi hai "
            "(prodnv ka asal size maloom karne ke liye)...", "INFO")
    ctx.progress(20, "Session 1: partition list...")
    cmd = spd_fdl.session_args(session, ["partition_list", str(plist),
                                         "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0 or not plist.is_file():
        ctx.log(f"Partition list nahi ban saki (exit code {code}) — "
                "baghair asal size ke prodnv read andaze se NAHI "
                "hoga. FDL/driver ki wajah upar ki lines me dekho.",
                "ERROR")
        return False
    try:
        parts = spd_fdl.parse_partition_xml(
            plist.read_text(encoding="utf-8", errors="ignore"))
    except OSError as e:
        ctx.log(f"Partition list parhi nahi ja saki: {e}", "ERROR")
        return False
    size = parts.get("prodnv")
    if not size or not (_MIN_PRODNV <= size <= _MAX_PRODNV):
        ctx.log("Partition list me 'prodnv' ka saaf size nahi mila "
                f"(mila: {size}) — is model par cert backup is "
                "raste se mehfooz nahi. Backup NAHI banaya gaya.",
                "ERROR")
        return False
    ctx.log(f"prodnv size: {size} bytes ({size / 1024:.0f} KiB)",
            "INFO")

    # --- Session 2: asal read
    ctx.log("Session 1 mukammal. **Ab phone ko dobara download "
            "mode me lagao** (band karke Volume dabaye hue cable) — "
            "tool 120 seconds wait karega, prodnv read hoga.", "WARN")
    ctx.progress(55, "Session 2: prodnv read (dobara download mode me lagao)...")
    out = outdir / "prodnv.bin"
    cmd = spd_fdl.session_args(session, [
        "read_part", "prodnv", "0", str(size), str(out), "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"prodnv read fail hua (exit code {code}). Session 1 "
                f"ki partition list mehfooz hai: {plist}", "ERROR")
        return False
    if not out.is_file() or out.stat().st_size != size:
        got = out.stat().st_size if out.is_file() else 0
        ctx.log(f"prodnv file ka size mile hue size se match nahi "
                f"({got} != {size}) — backup na-mukammal hai, use "
                "cert backup NAHI kaha jayega.", "ERROR")
        return False
    ctx.log(f"Cert (prodnv) backup mukammal: {out} "
            f"({size} bytes) — yehi file asal cert restore ka "
            "zariya hai; mehfooz jagah rakho.", "OK")
    ctx.progress(95, "Cert backup mukammal")
    return True
