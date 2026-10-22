"""
meta_reboot_fastboot.py — META session se phone ko fastboot
mode me reboot (Round 7, B5 session completion set).

FT_REBOOT + target REBOOT_FASTBOOT. SUCCESS sirf verified
status 0x00 jawab par (ft_checked). Fastboot me jane ke baad
FASTBOOT tab ke ops (info, FRP, reset — unlocked BL par)
chalte hain.
"""

from core import meta_session

OP = {
    "id": "meta_reboot_fastboot",
    "category": "MDM / Transsion",
    "name": "Reboot to Fastboot (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    ctx.log("Phone ko META mode se fastboot mode me bheja ja "
            "raha hai...", "INFO")
    ctx.progress(30, "FT reboot (fastboot) request bheji ja rahi hai...")
    if not meta_session.ft_checked(
            ctx, meta_session.FT_REBOOT,
            payload=bytes([meta_session.REBOOT_FASTBOOT]),
            timeout=15, what="Reboot (Fastboot)"):
        return False
    ctx.log("Reboot ka verified jawab (status OK) mil gaya — "
            "phone fastboot screen par ana chahiye; phir device "
            "panel me FASTBOOT mode ayega aur fastboot ops chal "
            "sakenge.", "OK")
    ctx.progress(95, "Reboot to Fastboot mukammal")
    return True
