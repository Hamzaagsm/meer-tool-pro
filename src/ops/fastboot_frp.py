"""
fastboot_frp.py — Fastboot se FRP erase (sirf unlocked bootloader).

Gap jo ye band karta hai (REPAIR-METHODS-RESEARCH §1.2/§4 P2#6):
Fastboot suite me pehle sirf info/reboot thay. Unlocked devices
(Xiaomi waghera jahan bootloader pehle se khula ho) par
`fastboot erase frp` sab se tez FRP rasta hai.

Usool: pehle `getvar` se unlock halat ASAL me parhi jati hai.
Locked bootloader par erase chal hi nahi sakta — wahan op
koshish ka natak nahi karta, saaf wajah ke saath FAIL deta hai
(unlock karna khud data mitata hai, wo alag faisla hai).
`config` partition (kuch builds par FRP wahan bhi hota hai)
koshish hoti hai; na ho to WARN, nakami nahi.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from core import engines

OP = {
    "id": "fastboot_frp",
    "category": "ADB / Fastboot",
    "name": "FRP Erase (Fastboot, unlocked only)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}


def parse_getvar(text):
    """fastboot getvar all ki output -> {key: value} (pure)."""
    data = {}
    for line in (text or "").splitlines():
        line = line.replace("(bootloader)", "").strip()
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip().lower()] = val.strip()
    return data


def is_unlocked(data):
    """True / False / None (None = halat confirm nahi ho saki — pure)."""
    val = (data or {}).get("unlocked")
    if val is None:
        return None
    v = val.strip().lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    return None


def getvar_all(fastboot, serial):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            [fastboot, "-s", serial, "getvar", "all"],
            capture_output=True, text=True, timeout=25, **kwargs)
        return (out.stderr or "") + "\n" + (out.stdout or "")
    except Exception:  # noqa: BLE001
        return ""


def resolve_fastboot(ctx):
    fb = engines.find_platform_tool("fastboot")
    if not Path(fb).is_file() and shutil.which(fb) is None:
        ctx.log("fastboot nahi mila — platform-tools setup chahiye "
                "(engines/platform-tools/).", "ERROR")
        return None
    dev = ctx.device
    if not dev or dev.mode != "FASTBOOT":
        ctx.log("Device Fastboot mode me nahi hai. Phone band "
                "karke Volume Down + Power se bootloader mode me "
                "lao.", "ERROR")
        return None
    return fb


def check_unlocked(ctx, fb, serial):
    """True = unlocked confirm. False = FAIL log tayyar hai."""
    text = getvar_all(fb, serial)
    data = parse_getvar(text)
    if not data:
        ctx.log("getvar se jawab nahi aya — cable/driver check "
                "karo; unlock halat ke baghair erase nahi hoga.",
                "ERROR")
        return False
    state = is_unlocked(data)
    if state is True:
        ctx.log("Bootloader UNLOCKED confirm ho gaya — erase aage "
                "barhega.", "OK")
        return True
    if state is False:
        ctx.log("Bootloader LOCKED hai — fastboot erase is device "
                "par chal hi nahi sakta. Raste: (a) pehle official "
                "unlock karo (us se data wese hi mit jata hai — "
                "customer se pehle pooch lo), ya (b) is chipset ka "
                "BROM/EDL wala FRP rasta istemal karo. Yahan "
                "koshish ka natak nahi kiya gaya.", "ERROR")
        return False
    ctx.log("getvar me 'unlocked' value nahi mili — is device par "
            "unlock halat confirm nahi ho saki, is liye erase "
            "nahi hoga. Pehle 'Read Device Info (Fastboot)' se "
            "poori getvar list dekho.", "ERROR")
    return False


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial
    if not check_unlocked(ctx, fb, serial):
        return False
    ctx.progress(40, "frp erase ho raha hai...")
    code = ctx.stream([fb, "-s", serial, "erase", "frp"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"frp erase fail hua (exit code {code}) — is "
                "device par FRP shayad doosre naam/partition me "
                "hai; chipset ke BROM/EDL raste dekho.", "ERROR")
        return False
    ctx.log("frp erase ho gaya.", "OK")
    ctx.progress(70, "config partition ki koshish...")
    code = ctx.stream([fb, "-s", serial, "erase", "config"],
                      timeout=180)
    if code != 0:
        ctx.log("config erase nahi hua — har device me ye "
                "partition nahi hota; FRP ka asal kaam (frp) ho "
                "chuka hai.", "WARN")
    else:
        ctx.log("config bhi erase ho gaya.", "OK")
    ctx.log("FRP erase mukammal. Phone reboot karke setup check "
            "karo — purana Google account nahi mangna chahiye.",
            "OK")
    ctx.progress(95, "FRP erase mukammal")
    return True
