"""
meta_poweroff.py — META session se phone power off (Round 7,
B5 session completion set).

FT_REBOOT + target REBOOT_POWEROFF. SUCCESS sirf verified
status 0x00 jawab par (ft_checked).
"""

from core import meta_session

OP = {
    "id": "meta_poweroff",
    "category": "MDM / Transsion",
    "name": "Power Off (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    ctx.log("Phone ko META mode se power off kiya ja raha hai...",
            "INFO")
    ctx.progress(30, "FT power-off request bheji ja rahi hai...")
    if not meta_session.ft_checked(
            ctx, meta_session.FT_REBOOT,
            payload=bytes([meta_session.REBOOT_POWEROFF]),
            timeout=15, what="Power Off"):
        return False
    ctx.log("Power off ka verified jawab (status OK) mil gaya — "
            "phone band ho jana chahiye. Screen phir bhi on rahe "
            "to is firmware ne ye target qabool nahi kiya (battery "
            "nikalna ya power button hi rasta hai).", "OK")
    ctx.progress(95, "Power Off mukammal")
    return True
