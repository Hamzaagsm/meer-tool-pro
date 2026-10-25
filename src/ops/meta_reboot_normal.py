"""
meta_reboot_normal.py — META session se phone ko normal
(Android) boot par reboot (Round 7, B5 session completion set).

FT_REBOOT + target REBOOT_NORMAL. SUCCESS sirf verified
status 0x00 jawab par (ft_checked) — hukum "bhej diya" kabhi
success nahi. META session ke aakhir me phone ko safai se
bahir nikalne ka asal rasta yahi hai.
"""

from core import meta_session

OP = {
    "id": "meta_reboot_normal",
    "category": "MDM / Transsion",
    "name": "Reboot to Normal (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    ctx.log("Phone ko META mode se normal boot par bheja ja raha "
            "hai...", "INFO")
    ctx.progress(30, "FT reboot (normal) request bheji ja rahi hai...")
    # Standalone op: phone META me hai hi nahi to FAIL (helper ka
    # already_gone_ok=False) — "phone shayad khud reboot ho raha
    # hai" wali narmi sirf doosre ops ke completion step ke liye hai.
    ok = meta_session.reboot_to_normal(ctx, already_gone_ok=False)
    if ok:
        ctx.progress(95, "Reboot to Normal mukammal")
    return ok
