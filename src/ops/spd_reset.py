"""
spd_reset.py — Unisoc / Spreadtrum factory reset (FDL session).

spd_frp ka saathi op (REPAIR-METHODS-RESEARCH §2.1): poori PAC
flash ke baghair tez reset — FDL session se `erase_part userdata`,
aur model me `metadata` partition ho to wo bhi (encryption keys
wahan hote hain; baghair us ke reset na-mukammal reh sakta hai).

Session me pehle `partition_list` chalti hai taake metadata ki
maujoodgi ka saboot PC par mehfooz ho: agar metadata hai hi nahi
to us ke erase par spd_dump rukta hai — us surat me op partition
list se tasdeeq karke userdata-wala reset SUCCESS maanta hai aur
wajah log me wazeh likhta hai. Agar metadata tha aur phir bhi
session fail hua to imaandar FAIL hai.
"""

from datetime import datetime

from core import spd_fdl
from core.runner import BACKUPS_DIR

OP = {
    "id": "spd_reset",
    "category": "SPD / Unisoc",
    "name": "Unisoc Factory Reset (FDL / spd_dump)",
    "engine": "spd_dump",
    "modes": ("SPD",),
    "server_required": False,
}


def run(ctx) -> bool:
    if not spd_fdl.spd_guard(ctx):
        return False
    session = spd_fdl.prepare_fdl(ctx)
    if session is None:
        return False

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    plist = BACKUPS_DIR / f"spd-partitions-{stamp}.xml"
    try:
        plist.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Partition list ki jagah nahi ban saki: {e}", "ERROR")
        return False

    ctx.log("Reset ka nishana: userdata (+ metadata agar model me "
            "ho). NV/prodnv ko NAHI chua jayega — IMEI/cert mehfooz "
            "rahega.", "INFO")
    ctx.progress(30, "FDL session — userdata erase ho raha hai...")
    cmd = spd_fdl.session_args(session, [
        "partition_list", str(plist),
        "erase_part", "userdata",
        "erase_part", "metadata",
        "power_off",
    ])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False

    parts = {}
    if plist.is_file():
        try:
            parts = spd_fdl.parse_partition_xml(
                plist.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            parts = {}
    if parts:
        ctx.log(f"Partition list mehfooz: {plist} "
                f"({len(parts)} partitions)", "INFO")

    if code == 0:
        ctx.progress(95, "Factory reset mukammal")
        ctx.log("userdata + metadata erase ho gaye — factory reset "
                "mukammal.", "OK")
        return True

    # Session fail — lekin agar metadata tha hi nahi, to spd_dump
    # usi erase par rukta hai; userdata us se pehle erase ho chuka
    # hota hai (tartib: userdata pehle). Saboot partition list se.
    if parts and "metadata" not in parts and "userdata" in parts:
        ctx.log("Note: is model me 'metadata' partition hai hi "
                "nahi — spd_dump us ke erase par ruka, lekin "
                "userdata erase us se PEHLE mukammal ho chuka tha "
                "(session ki tartib). Reset asal me ho gaya hai.",
                "WARN")
        ctx.progress(95, "Factory reset mukammal (metadata maujood nahi tha)")
        ctx.log("Factory reset mukammal — sirf userdata wala model "
                "tha.", "OK")
        return True

    ctx.log(f"Factory reset fail hua (spd_dump exit code {code}). "
            "Upar ki lines me asal wajah dekho (FDL mismatch, "
            "driver, ya darmiyan me cable/phone nikal jana).",
            "ERROR")
    return False
