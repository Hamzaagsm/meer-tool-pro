"""fastboot_info.py — Fastboot mode me getvar se asal info parhna."""

import shutil
import subprocess
import sys

OP = {
    "id": "fastboot_info",
    "category": "ADB / Fastboot",
    "name": "Read Device Info (Fastboot)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}

WANTED = ("product", "variant", "serialno", "unlocked", "secure",
          "slot-count", "current-slot", "version-bootloader", "max-download-size")


def _getvar_all(fastboot, serial):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            [fastboot, "-s", serial, "getvar", "all"],
            capture_output=True, text=True, timeout=20, **kwargs)
        text = (out.stderr or "") + "\n" + (out.stdout or "")
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    data = {}
    for line in text.splitlines():
        line = line.replace("(bootloader)", "").strip()
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip()] = val.strip()
    return data, ""


def run(ctx) -> bool:
    fb = shutil.which("fastboot")
    if not fb:
        ctx.log("fastboot nahi mila — engine setup required "
                "(tools/platform-tools).", "ERROR")
        return False
    dev = ctx.device
    if not dev or dev.mode != "FASTBOOT":
        ctx.log("Device Fastboot mode me nahi hai. (Volume Down + Power se "
                "bootloader mode me lao.)", "ERROR")
        return False
    ctx.progress(25, "getvar all chal raha hai...")
    data, err = _getvar_all(fb, dev.serial)
    if data is None:
        ctx.log(f"fastboot se jawab nahi aya: {err}", "ERROR")
        return False
    if not data:
        ctx.log("getvar khali aya — cable/driver check karo.", "ERROR")
        return False
    dev.model = data.get("product", dev.model)
    unlocked = data.get("unlocked", "")
    if unlocked:
        dev.detail = f"Bootloader unlocked: {unlocked}"
    for key in WANTED:
        if key in data:
            ctx.log(f"{key}: {data[key]}", "DATA")
    if ctx.update_device:
        ctx.update_device(dev)
    ctx.progress(95, "Mukammal")
    return True
