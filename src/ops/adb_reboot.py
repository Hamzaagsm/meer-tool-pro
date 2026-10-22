"""adb_reboot.py — ADB reboot operations (normal / bootloader / recovery)."""

import shutil
from pathlib import Path

from core import engines

OP = {
    "id": "adb_reboot",
    "category": "ADB / Fastboot",
    "name": "Reboot (ADB → Normal)",
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
    ctx.progress(30, f"Reboot ({target or 'normal'}) ka hukum bheja ja raha hai...")
    cmd = [adb, "-s", dev.serial, "reboot"]
    if target:
        cmd.append(target)
    code = ctx.stream(cmd, timeout=30)
    if code == 0:
        ctx.log("Reboot ka hukum bhej diya — device restart ho raha hai.", "OK")
        return True
    ctx.log(f"adb reboot fail hua (exit code {code}).", "ERROR")
    return False


def run(ctx) -> bool:
    return _reboot(ctx, "")
