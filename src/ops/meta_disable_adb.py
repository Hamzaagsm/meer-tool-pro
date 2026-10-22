"""
meta_disable_adb.py — META mode me FT protocol se ADB disable
(Round 7, B5 — Fenix TMETA tab se parity: hamare paas Enable
ADB tha, Disable nahi tha).

FT_SET_ADB par set-value 0x00 (ADB off). Pehle LADDER guard
(Enable ADB wala hi usool — new-Auth class par META entry
gated hai). SUCCESS sirf verified status 0x00 par (ft_checked).
"""

from core import meta_guard, meta_session

OP = {
    "id": "meta_disable_adb",
    "category": "MDM / Transsion",
    "name": "Disable ADB (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}

_ADB_OFF_PAYLOAD = bytes([0x00])


def run(ctx, model=None) -> bool:
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    ctx.log("ADB disable ka hukum META session se bheja ja raha "
            "hai — is ke baad phone normal reboot par USB "
            "debugging BAND milegi (yehi is amal ka maqsad hai).",
            "INFO")
    ctx.progress(30, "FT ADB-disable request bheji ja rahi hai...")
    if not meta_session.ft_checked(ctx, meta_session.FT_SET_ADB,
                                   payload=_ADB_OFF_PAYLOAD,
                                   timeout=15, what="ADB Disable"):
        return False
    if ctx.is_cancelled():
        return False
    ctx.progress(85, "ADB disable ka verified jawab mil gaya")
    ctx.log("ADB disable ka verified jawab (status OK) mil gaya. "
            "Phone ko normal reboot karke tasdeeq kar lo — ADB "
            "ab nahi milna chahiye.", "OK")
    ctx.progress(95, "Disable ADB mukammal")
    return True
