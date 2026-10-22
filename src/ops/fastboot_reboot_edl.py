"""
fastboot_reboot_edl.py — Fastboot se device ko EDL (9008) me reboot karna.

Pehle `oem edl` ki koshish hoti hai; wo fail ho to `reboot-edl`
try hota hai. SUCCESS sirf tab jab dono me se koi aik hukum
exit 0 par qabool ho jaye. Reboot ke hukum ke liye bootloader
unlock check ki zaroorat nahi — is liye check_unlocked yahan
nahi chalaya jata.
"""

from ops.fastboot_frp import resolve_fastboot

OP = {
    "id": "fastboot_reboot_edl",
    "category": "ADB / Fastboot",
    "name": "Reboot (Fastboot → EDL 9008)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial

    ctx.progress(30, "oem edl ka hukum bheja ja raha hai...")
    code = ctx.stream([fb, "-s", serial, "oem", "edl"],
                      timeout=60)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.log("oem edl qabool ho gaya — device EDL mode me "
                "restart ho raha hai.", "OK")
        ctx.log("Ab Device panel me EDL (QDLoader 9008) nazar "
                "ana chahiye.", "INFO")
        ctx.progress(95, "EDL reboot mukammal")
        return True

    ctx.log(f"oem edl fail hua (exit code {code}) — ab "
            "reboot-edl wala hukum try ho raha hai...", "WARN")
    ctx.progress(60, "reboot-edl ka hukum bheja ja raha hai...")
    code = ctx.stream([fb, "-s", serial, "reboot-edl"],
                      timeout=60)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.log("reboot-edl qabool ho gaya — device EDL mode "
                "me restart ho raha hai.", "OK")
        ctx.log("Ab Device panel me EDL (QDLoader 9008) nazar "
                "ana chahiye.", "INFO")
        ctx.progress(95, "EDL reboot mukammal")
        return True

    ctx.log(f"reboot-edl bhi fail hua (exit code {code}) — "
            "dono hukum nakam hue.", "ERROR")
    ctx.log("Har bootloader EDL reboot support nahi karta — "
            "khaas tor par locked aur naye devices par ye "
            "hukum aksar band hota hai. Wahan test-point ya "
            "EDL cable wala rasta istemaal hota hai.", "WARN")
    return False
