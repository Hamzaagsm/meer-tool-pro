"""
adb_service_menus.py — Servicing Settings Menus (ADB intents).

Technician ko aksar phone ke chhupe hue / gehray settings
menus chahiye hote hain: mobile network / operator selection,
APN settings, wireless settings. Ye op un ke PUBLIC Android
intents `am start` se kholta hai:
  - android.settings.NETWORK_OPERATOR_SETTINGS
  - android.settings.APN_SETTINGS
  - android.settings.WIRELESS_SETTINGS

IMAANDARI:
  - Root: NAHI chahiye.
  - `am start` nakami par bhi aksar exit code 0 de deta hai —
    is liye saboot output ka matan hai: jawab me "Error" aye
    to wo menu nakam mana jata hai. SUCCESS tab jab kam az
    kam AIK menu asal me khul jaye.
  - DIAG menu ka Android me koi public intent NAHI hota —
    ye op us ka jhoota daawa nahi karta; DIAG ke liye
    'Enable DIAG Port' op aur dialer codes hain (log me
    likhe jate hain).
"""

from ops.adb_remove_ads import guard, sh

OP = {
    "id": "adb_service_menus",
    "category": "ADB / Fastboot",
    "name": "Servicing Menus Kholain (Network/APN)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

INTENTS = (
    ("Mobile Network / Operator Settings",
     "android.settings.NETWORK_OPERATOR_SETTINGS"),
    ("APN Settings", "android.settings.APN_SETTINGS"),
    ("Wireless & Network Settings",
     "android.settings.WIRELESS_SETTINGS"),
)


def intent_started(output):
    """am start ke jawab ki tasdeeq (pure): 'Error' wala
    jawab nakami hai, warna menu khula mana jata hai."""
    return "error" not in (output or "").lower()


def run(ctx) -> bool:
    adb, serial = guard(ctx)
    if adb is None:
        return False
    ctx.log("Root: NAHI chahiye — public Android settings "
            "intents istemal ho rahe hain.", "INFO")
    ctx.log("Note: DIAG menu ka koi public intent nahi hota — "
            "DIAG ke liye alag 'Enable DIAG Port (ADB)' op hai, "
            "ya phone par dialer codes: Samsung *#0808#, "
            "OnePlus/Xiaomi *#*#717717#*#*.", "INFO")
    started = []
    ctx.progress(30, "Servicing menus kholne ki koshish...")
    for name, action in INTENTS:
        out, _code = sh(adb, serial, ["am", "start", "-a", action])
        first = (out.strip().splitlines() or [""])[0]
        if intent_started(out):
            started.append(name)
            ctx.log(f"✓ {name} khul gaya ({first})", "DATA")
        else:
            ctx.log(f"✗ {name} nahi khula — is ROM par ye "
                    f"intent maujood nahi ({first})", "WARN")
    if not started:
        ctx.log("Koi bhi servicing menu nahi khula — is device "
                "ke ROM me ye intents maujood nahi lagte. FAIL "
                "(nakli success nahi).", "ERROR")
        return False
    ctx.log(f"Servicing menus mukammal — {len(started)} menu "
            f"khule: {', '.join(started)}. Phone ki screen "
            "check karen.", "OK")
    ctx.progress(95, "Servicing menus khul gaye")
    return True
