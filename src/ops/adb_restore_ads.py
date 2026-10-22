"""
adb_restore_ads.py — Restore Ads (Remove Ads ka ulta).

Remove Ads op ne jo packages disable kiye thay (Xiaomi ads
set + generic ads set, dono profiles ke packages), un me se
jo is waqt disabled halat me hain unhe `pm enable` karke
wapas chaloo karta hai.

IMAANDARI:
  - Root: NAHI chahiye.
  - Sirf wohi packages chue jate hain jo asal me disabled
    hain — baqi sab SKIP (ye nakami nahi).
  - SUCCESS sirf device-side saboot par: enable ke baad
    package `pm list packages -d` se asal me ghayab ho.
  - Kuch disabled hi na mile to "karne ko kuch tha hi
    nahi" ke saath FAIL (nakli success nahi).
"""

from core import app_profiles
from ops.adb_remove_ads import apply_and_verify, guard

OP = {
    "id": "adb_restore_ads",
    "category": "ADB / Fastboot",
    "name": "Restore Ads (Servicing)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

PROFILE_KEYS = ("xiaomi_ads_set", "generic_bloat_admin")


def ads_packages():
    """Dono ads profiles ke packages ka majmua (pure-ish —
    sirf builtin store parhta hai)."""
    profiles = app_profiles.all_profiles()
    pkgs = []
    for key in PROFILE_KEYS:
        prof = profiles.get(key)
        if prof:
            for pkg in prof["packages"]:
                if pkg not in pkgs:
                    pkgs.append(pkg)
    return pkgs


def run(ctx) -> bool:
    adb, serial = guard(ctx)
    if adb is None:
        return False
    packages = ads_packages()
    if not packages:
        ctx.log("Ads profiles nahi mile — app files check karo.",
                "ERROR")
        return False
    ctx.log("Root: NAHI chahiye — ye aam ADB shell ka kaam hai.",
            "INFO")
    ctx.log("Remove Ads wale dono profiles ke packages check "
            "ho rahe hain — jo disabled hain sirf wohi enable "
            "honge.", "INFO")
    ctx.progress(35, "Ads packages wapas enable ho rahe hain...")
    done, failed, skipped = apply_and_verify(
        ctx, adb, serial, packages, "enable")
    for pkg in done:
        ctx.log(f"✓ {pkg} wapas enable (disabled list se ghayab "
                "— device se verify).", "DATA")
    for pkg in failed:
        ctx.log(f"✗ {pkg} enable NAHI hua.", "WARN")
    if failed:
        ctx.log(f"Natija: {len(done)} enable hue, "
                f"{len(failed)} nakam — poora kaam nahi hua, is "
                "liye FAIL.", "ERROR")
        return False
    if not done:
        ctx.log("Koi bhi ads package disabled halat me nahi "
                "mila — restore karne ko kuch tha hi nahi (sab "
                "pehle se enable hain).", "ERROR")
        return False
    ctx.log(f"Restore Ads mukammal — {len(done)} packages "
            "wapas enable + device se verify shuda.", "OK")
    ctx.progress(95, "Restore Ads mukammal")
    return True
