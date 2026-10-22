"""
adb_fix_install.py — Fix Install Apps (Servicing Task).

Jab phone ADB/sideload se app install karne me nakam hota
hai (package verifier ki rok, 'install blocked' waghera),
ye mashhoor servicing settings madad karti hain:
  global verifier_verify_adb_installs = 0
  global package_verifier_enable     = 0
  secure install_non_market_apps     = 1

IMAANDARI:
  - Root: NAHI chahiye — lekin kuch ROMs secure/global keys
    shell se badalne nahi deti. Is liye har setting ki
    readback hoti hai; jo lag gayi wahi log me ✓ ke saath
    ayegi, jo ROM ne ignore ki wo ✗ ke saath.
  - SUCCESS tab jab kam az kam AIK setting readback se
    confirm ho jaye; AIK bhi na lage to FAIL.
  - Note: ye verifier ki rokain naram karta hai — sirf
    bharose wale sources se app install karen; kaam ke baad
    Android ki apni hifazat wapas chaaho to Play Protect /
    Settings se verifier dobara on ho jata hai.
"""

from ops.adb_remove_ads import guard, sh

OP = {
    "id": "adb_fix_install",
    "category": "ADB / Fastboot",
    "name": "Fix Install Apps (Servicing)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

SETTINGS = (
    ("global", "verifier_verify_adb_installs", "0"),
    ("global", "package_verifier_enable", "0"),
    ("secure", "install_non_market_apps", "1"),
)


def setting_applied(readback, wanted):
    """Readback ki tasdeeq (pure)."""
    return (readback or "").strip() == wanted


def run(ctx) -> bool:
    adb, serial = guard(ctx)
    if adb is None:
        return False
    ctx.log("Root: NAHI chahiye — settings shell se likhi "
            "jati hain; har aik ki readback hi saboot hai.",
            "INFO")
    ctx.log("Note: ye settings app-install ki verifier "
            "rokain naram karti hain — sirf bharose wale "
            "sources se install karen.", "WARN")
    applied, ignored = [], []
    ctx.progress(35, "Install-fix settings lagayi ja rahi "
                     "hain...")
    for ns, key, value in SETTINGS:
        sh(adb, serial, ["settings", "put", ns, key, value])
        out, _ = sh(adb, serial, ["settings", "get", ns, key])
        back = (out or "").strip()
        if setting_applied(back, value):
            applied.append(f"{key}={value}")
            ctx.log(f"✓ {ns} {key} = {value} (readback confirm)",
                    "DATA")
        else:
            ignored.append(key)
            ctx.log(f"✗ {ns} {key} — readback '{back or 'khali'}' "
                    f"mili, {value} nahi; is ROM ne ignore kar "
                    "diya.", "WARN")
    if not applied:
        ctx.log("AIK bhi setting readback se confirm nahi hui "
                "— is ROM par ye rasta band hai. FAIL (nakli "
                "success nahi).", "ERROR")
        return False
    ctx.log(f"Fix Install mukammal — {len(applied)} settings "
            f"lag gayin ({', '.join(applied)})"
            + (f"; {len(ignored)} ROM ne ignore kin"
               if ignored else "")
            + ". Ab ADB se app install karke dekhen.", "OK")
    ctx.progress(95, "Fix Install mukammal")
    return True
