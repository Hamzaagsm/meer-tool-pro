"""
fastboot_reset.py — Fastboot se factory reset (sirf unlocked).

`fastboot -w` wali class ka reset, lekin kadam-ba-kadam taake
har hisay ka natija log me wazeh ho (REPAIR-METHODS-RESEARCH
§2.1/§4 P2#6): userdata erase (lazmi), metadata erase (model
me ho to — encryption keys ke liye; na ho to WARN).

Bootloader locked ho to pehle hi saaf FAIL (fastboot_frp wala
hi unlock check) — erase ki nakli koshish nahi hoti. NV/IMEI
partitions ko ye op kabhi nahi chuta.
"""

from core import engines  # noqa: F401  (pattern consistency)
from ops.fastboot_frp import check_unlocked, resolve_fastboot

OP = {
    "id": "fastboot_reset",
    "category": "ADB / Fastboot",
    "name": "Factory Reset (Fastboot, unlocked only)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial
    if not check_unlocked(ctx, fb, serial):
        return False
    ctx.log("Reset ka nishana: userdata + metadata. NV/IMEI aur "
            "baqi partitions mehfooz rahenge.", "INFO")
    ctx.progress(35, "userdata erase ho raha hai...")
    code = ctx.stream([fb, "-s", serial, "erase", "userdata"],
                      timeout=300)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"userdata erase fail hua (exit code {code}) — "
                "reset aage nahi barhega.", "ERROR")
        return False
    ctx.log("userdata erase ho gaya.", "OK")
    ctx.progress(65, "metadata erase ho raha hai...")
    code = ctx.stream([fb, "-s", serial, "erase", "metadata"],
                      timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("metadata erase nahi hua — har model me ye "
                "partition nahi hota; userdata wala reset asal "
                "kaam hai, wo ho chuka hai.", "WARN")
    else:
        ctx.log("metadata bhi erase ho gaya (encryption keys "
                "saaf — reset mukammal surat me hua).", "OK")
    ctx.log("Factory reset mukammal. 'Reboot (Fastboot)' se ya "
            "phone ke Power button se on karo — pehli boot par "
            "setup wizard ayega.", "OK")
    ctx.progress(95, "Factory reset mukammal")
    return True
