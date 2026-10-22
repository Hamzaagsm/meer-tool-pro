"""adb_reboot_edl.py — ADB se device ko EDL (9008) mode me reboot karna."""

import shutil
from pathlib import Path

from core import engines

OP = {
    "id": "adb_reboot_edl",
    "category": "ADB / Fastboot",
    "name": "Reboot (ADB → EDL 9008)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}


def _reboot(ctx, target):
    adb = engines.find_platform_tool("adb")
    if not Path(adb).is_file() and shutil.which(adb) is None:
        ctx.log("adb nahi mila — engine setup required (tools/platform-tools).", "ERROR")
        return False
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai.", "ERROR")
        return False
    ctx.log("Note: kuch brands — khaas tor par naye Xiaomi — "
            "ADB se EDL band karte hain. Agar phone EDL me na "
            "jaye to ye op ki nakami nahi, brand ki pabandi "
            "hai; wahan test-point ya EDL cable wala rasta "
            "istemaal hota hai.", "WARN")
    ctx.progress(30, f"Reboot ({target or 'normal'}) ka hukum bheja ja raha hai...")
    cmd = [adb, "-s", dev.serial, "reboot"]
    if target:
        cmd.append(target)
    code = ctx.stream(cmd, timeout=30)
    if code == 0:
        ctx.log("Reboot ka hukum bhej diya — device restart ho raha hai.", "OK")
        ctx.log("Ab Device panel me EDL (QDLoader 9008) nazar "
                "ana chahiye. Agar device aam tareeqe se on ho "
                "gaya ya panel me EDL nazar nahi aya to samjho "
                "is brand/model ne ADB se EDL band kiya hua "
                "hai — test-point / EDL cable wala rasta dekho.",
                "INFO")
        return True
    ctx.log(f"adb reboot fail hua (exit code {code}).", "ERROR")
    return False


def run(ctx) -> bool:
    return _reboot(ctx, "edl")
