"""
app_profiles.py — App-disable Profiles / Templates (CM2 AppTool
parity, COMPETITOR-RESEARCH-3 §2.2 / §4 P1).

CM2MT2 ke [AppTool] "Load list to Disable" ki design: checked
app-disable list ko file me save karke doosre devices par
template ke tor par reuse karna. Mechanism public hai (ADB
`pm disable-user`) — yahan sirf profile/template wali design
hai:

  - Built-in profiles: Transsion security-plugin set, Samsung
    IT-Admin/MDM set, generic bloat/admin set.
  - User ke apne custom profiles: tools/app-profiles.json me
    save/load hote hain; aik profile ko "active" mark kiya ja
    sakta hai — active custom profile ho to op wahi lagata hai.
  - Har amal ka natija label discipline ke tehet hamesha
    BYPASS hai (app-disable reversible hai; PERMANENT sirf
    state-layer patch path hai — mdm_security_plugin dekho).

Profile ke packages "template" hain: jo package device par
installed hi nahi, wo skip hota hai (nakami nahi). Har package
ka natija alag log hota hai — yehi CM2-style imaandari hai.
"""

import json
from pathlib import Path

PROFILES_FILENAME = "app-profiles.json"

# Built-in profiles — packages wahi jo project research/code me
# documented hain ya aam debloat/IT-admin references me mashhoor
# hain. Ye TEMPLATE hain: device par jo na ho wo skip hoga.
BUILTIN_PROFILES = {
    "transsion_security_plugin": {
        "name": "Transsion Security Plugin Set",
        "description": (
            "Infinix/Tecno/itel ke researched security-plugin "
            "family packages (FENIX research §1). Plugin ki asal "
            "pehchan mdm_security_plugin op ki heuristic + "
            "device-owner list se bhi hoti hai — ye set us ka "
            "tayyar template hai."),
        "packages": [
            "com.financial.service",
            "com.mixtel.manager",
        ],
    },
    "samsung_it_admin": {
        "name": "Samsung IT Admin / MDM Set",
        "description": (
            "Samsung ke Knox/MDM client packages — KG client, "
            "KLM agent, Knox cloud MDM. Disable = BYPASS; KG ki "
            "server state is se nahi badalti (KG Status op "
            "dekho)."),
        "packages": [
            "com.samsung.android.kgclient",
            "com.samsung.klmsagent",
            "com.sec.enterprise.knox.cloudmdm.smdms",
        ],
    },
    "generic_bloat_admin": {
        "name": "Generic Bloat / Preloaded Managers",
        "description": (
            "Aam preloaded bloat/manager apps jo aksar devices "
            "par pehle se aati hain. Disable reversible hai — "
            "Settings se dobara enable ho sakti hain."),
        "packages": [
            "com.facebook.system",
            "com.facebook.appmanager",
            "com.facebook.services",
            "com.microsoft.appmanager",
        ],
    },
    "samsung_account_knox_set": {
        "name": "Samsung Account / Knox Set",
        "description": (
            "Samsung account/Knox client set — KG client, KLM "
            "agent, Knox cloud MDM, Samsung account sign-in. "
            "Disable = BYPASS label hai, KG ki server state is "
            "se nahi badalti. Ye TEMPLATE hai — jo package "
            "device par installed nahi, wo op skip kar deta hai."),
        "packages": [
            "com.samsung.android.kgclient",
            "com.samsung.klmsagent",
            "com.sec.enterprise.knox.cloudmdm.smdms",
            "com.osp.app.signin",
        ],
    },
    "disable_ota_updates": {
        "name": "Disable OTA Updates Set",
        "description": (
            "MDM/finance wale phones par OTA update band karne "
            "ke liye — Samsung FOTA/software-update, Xiaomi/MIUI "
            "updater, Transsion OTA (Fenix/Infinix wale case me "
            "update se MDM wapas ane ka risk kam hota hai). Ye "
            "TEMPLATE hai — jo package device par installed "
            "nahi, wo op skip kar deta hai."),
        "packages": [
            "com.wssyncmldm",
            "com.sec.android.soagent",
            "com.android.updater",
            "com.transsion.ota",
        ],
    },
    "demo_retail_set": {
        "name": "Demo / Retail Mode Set",
        "description": (
            "Shop demo/retail mode packages — Samsung retail "
            "mode/demo aur Google retail demo. Ye TEMPLATE hai "
            "— jo package device par installed nahi, wo op "
            "skip kar deta hai."),
        "packages": [
            "com.sec.android.retailmode",
            "com.samsung.android.demo",
            "com.google.android.retaildemo",
        ],
    },
    "xiaomi_ads_set": {
        "name": "Xiaomi / MIUI Ads Set",
        "description": (
            "MIUI ke system ads/analytics packages — Remove Ads "
            "op ke liye (TSM-UAT round 6). Disable = ads "
            "components band; reversible hai (Restore Ads op / "
            "Settings se dobara enable). Ye TEMPLATE hai — jo "
            "package device par installed nahi, wo op skip kar "
            "deta hai."),
        "packages": [
            "com.miui.systemAdSolution",
            "com.miui.analytics",
            "com.miui.msa.global",
        ],
    },
}

_TRANSSION_BRANDS = ("transsion", "infinix", "tecno", "itel")


def profiles_path(tools_dir=None):
    if tools_dir is None:
        from core.runner import TOOLS_DIR
        tools_dir = TOOLS_DIR
    return Path(tools_dir) / PROFILES_FILENAME


def load_store(tools_dir=None):
    """Custom profiles ka store — {active, custom:{name:[pkgs]}}.
    File na ho ya kharab ho to khali store (kabhi raise nahi)."""
    path = profiles_path(tools_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        custom = data.get("custom") or {}
        clean = {}
        for name, pkgs in custom.items():
            if isinstance(pkgs, list):
                clean[str(name)] = [str(p) for p in pkgs if str(p).strip()]
        return {"active": data.get("active") or None, "custom": clean}
    except Exception:  # noqa: BLE001
        return {"active": None, "custom": {}}


def _save_store(store, tools_dir=None):
    path = profiles_path(tools_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001
        return False


def save_custom_profile(name, packages, tools_dir=None):
    """Aik disable-list ko custom profile/template ke tor par save
    karo (CM2 ki 'save list' wali sahulat)."""
    name = (name or "").strip()
    pkgs = [str(p).strip() for p in (packages or []) if str(p).strip()]
    if not name or not pkgs:
        return False
    store = load_store(tools_dir)
    store["custom"][name] = pkgs
    return _save_store(store, tools_dir)


def set_active_profile(name, tools_dir=None):
    store = load_store(tools_dir)
    store["active"] = name or None
    return _save_store(store, tools_dir)


def all_profiles(tools_dir=None):
    """Tamam profiles: builtin (key waisi hi) + custom
    ('custom:<name>' key ke saath)."""
    out = {}
    for key, prof in BUILTIN_PROFILES.items():
        out[key] = {"name": prof["name"],
                    "description": prof["description"],
                    "packages": list(prof["packages"]),
                    "builtin": True}
    store = load_store(tools_dir)
    for name, pkgs in store["custom"].items():
        out[f"custom:{name}"] = {"name": f"{name} (custom)",
                                  "description": "User ka saved "
                                                 "template.",
                                  "packages": list(pkgs),
                                  "builtin": False}
    return out


def pick_profile_key(brand="", tools_dir=None):
    """Kaunsa profile lagega: active custom > brand match > generic."""
    store = load_store(tools_dir)
    active = store.get("active")
    if active and active in store.get("custom", {}):
        return f"custom:{active}"
    if active and active in BUILTIN_PROFILES:
        return active
    b = (brand or "").lower()
    if "samsung" in b:
        return "samsung_it_admin"
    if any(t in b for t in _TRANSSION_BRANDS):
        return "transsion_security_plugin"
    return "generic_bloat_admin"
