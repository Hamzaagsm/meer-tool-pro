"""adb_reboot_download.py — ADB se Samsung device ko Download mode me reboot karna."""

import shutil
from pathlib import Path

from core import engines

OP = {
    "id": "adb_reboot_download",
    "category": "ADB / Fastboot",
    "name": "Reboot (ADB → Samsung Download)",
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
    ctx.log("Note: ye hukum sirf Samsung par kaam karta hai — "
            "Samsung devices par adb reboot download seedha "
            "Odin / Download mode me le jata hai. Doosre "
            "brands par is se aam reboot ho sakta hai, Download "
            "mode nahi ayega.", "WARN")
    ctx.progress(30, f"Reboot ({target or 'normal'}) ka hukum bheja ja raha hai...")
    cmd = [adb, "-s", dev.serial, "reboot"]
    if target:
        cmd.append(target)
    code = ctx.stream(cmd, timeout=30)
    if code == 0:
        ctx.log("Reboot ka hukum bhej diya — device restart ho raha hai.", "OK")
        ctx.log("Samsung device par ab Download / Odin mode "
                "ki screen ani chahiye. Agar aam reboot hua "
                "hai to device Samsung nahi hai ya us model "
                "par ye hukum support nahi karta.", "INFO")
        return True
    ctx.log(f"adb reboot fail hua (exit code {code}).", "ERROR")
    return False


def run(ctx) -> bool:
    return _reboot(ctx, "download")
