"""fastboot_reboot.py — Fastboot mode se device ko normal reboot karna."""

import shutil
from pathlib import Path

from core import engines

OP = {
    "id": "fastboot_reboot",
    "category": "ADB / Fastboot",
    "name": "Reboot (Fastboot → Normal)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}


def run(ctx) -> bool:
    fb = engines.find_platform_tool("fastboot")
    if not Path(fb).is_file() and shutil.which(fb) is None:
        ctx.log("fastboot nahi mila — engine setup required "
                "(tools/platform-tools).", "ERROR")
        return False
    dev = ctx.device
    if not dev or dev.mode != "FASTBOOT":
        ctx.log("Device Fastboot mode me nahi hai. (Volume Down + Power se "
                "bootloader mode me lao.)", "ERROR")
        return False
    ctx.progress(30, "Reboot ka hukum bheja ja raha hai...")
    code = ctx.stream([fb, "-s", dev.serial, "reboot"], timeout=30)
    if code == 0:
        ctx.log("Reboot ka hukum bhej diya — device normal restart ho raha hai.", "OK")
        return True
    ctx.log(f"fastboot reboot fail hua (exit code {code}).", "ERROR")
    return False
