"""
fw_loader_harvest.py — Firmware → Loader Auto-Harvest.

Factory firmware file (`tools/firmware-inbox/` me rakhi hui
.zip / .tgz / .tar.gz / .ofp / .ozip / .pac) ke andar se
loader-class files — preloader, lk, MTK DA, Qualcomm firehose,
aur PAC ke FDL1/FDL2 — nikaal kar Loaders Library me darj
karta hai (core/fw_harvest; tasdeeq loader_library ke magic
rules se, FDL PAC table se, preloader/lk naam se — har cheez
log me saaf).

Is se har nayi firmware ke saath loaders khud library me
jama hote rehte hain — Hovatek/AndroidMTK se alag-alag DA
dhoondhne ki zaroorat kam ho jati hai. Imaandari: loader
milna aur signed-auth pass hona do alag chezen hain — ye op
sirf library bharta hai.

Device ki zaroorat nahi (modes ()).
"""

from __future__ import annotations

from core import fw_harvest
from core.runner import TOOLS_DIR

OP = {
    "id": "fw_loader_harvest",
    "category": "Utility",
    "name": "Firmware → Loader Harvest (Firmware se Loaders → Library)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "firmware-inbox"


def run(ctx) -> bool:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    src = fw_harvest.find_input(INBOX_DIR)
    if src is None:
        ctx.log("firmware-inbox me koi supported firmware file "
                "nahi mili (.zip / .tgz / .tar.gz / .ofp / .ozip / "
                ".pac).", "ERROR")
        ctx.log(f"Guide: factory firmware file is folder me "
                f"rakho: {INBOX_DIR} — phir ye op dobara chalao. "
                "File ke andar ke preloader / lk / DA / firehose "
                "/ FDL khud nikaal kar Loaders Library me darj "
                "ho jayenge.", "WARN")
        return False
    ctx.log(f"Firmware file: {src}", "INFO")
    ctx.progress(15, "Firmware khul raha hai — loaders dhoondhe "
                     "ja rahe hain...")
    result = fw_harvest.harvest(ctx, src)
    if ctx.is_cancelled():
        return False
    fw_harvest.log_summary(ctx, result)
    ctx.progress(95, "Harvest mukammal")
    if result["registered"]:
        return True
    if result["already"]:
        ctx.log("Is firmware ke tamam loaders pehle se library "
                "me hain — naya kuch darj nahi hua, lekin harvest "
                "saaf mukammal hua.", "INFO")
        return True
    ctx.log("Is firmware se koi loader register NAHI hua — "
            "upar ki fehrist me wajahen saaf hain (candidate na "
            "milna, ya tasdeeq na hona). Nakli darj kabhi nahi "
            "hota.", "ERROR")
    return False
