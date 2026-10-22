"""
mdm_list.py — MDM List (Fenix-style per-model panel) ka data + actions.

Hamza ne apne Fenix Tool Pro ki screens bheji theen: Unlock module me
per-model **MDM List** hoti hai — har model ke saath method tags
([MDL][PL][DA] ya [TMETA][MDM][UBL]) aur model select karne par mode
tabs (Download / Transsion META / ADB / FASTBOOT) khulte hain. Ye
module usi sakht ko MEER Tool Pro me deta hai:

  - Model database: `tools/mdm-models.json` — EXE ke saath rehti hai,
    **user-editable** hai (per-model data Hamza ke apne kaam se bharta
    hai). File na ho to seed entries ke saath khud ban jati hai.
  - Har tab ke action **asal ops par wired** hain: ya to mojooda plugin
    ops ko delegate karte hain (mtk_frp_reset, mtk_bl_unlock,
    mdm_security_plugin, mdm_payjoy, mdm_meta_guide), ya engines se
    seedha wahi sequence chalate hain (Download tab ka DA-wala reset,
    RESTORE MDM ka model-matched proinfo write).
  - Jahan per-model data library me nahi, wahan **guided FAIL** —
    nakli success kabhi nahi.

GUI (main.py) is module ko sirf data + action-factories ke liye
istemal karti hai; tamam execution runner ke through hi hoti hai.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core import engines
from core.runner import TOOLS_DIR

MODELS_FILE = TOOLS_DIR / "mdm-models.json"
BACKUP_DIR = TOOLS_DIR / "mdm-backups"

# Seed entries — Hamza ki Fenix screens se (model / code / chipset /
# tags). Ye sirf shuruaati fehrist hai; asal per-model data (DA files,
# backups) user ke apne kaam se jama hota hai aur JSON me barhaya
# ja sakta hai.
SEED_MODELS = [
    {"brand": "Infinix", "model": "GT 20 Pro", "code": "X6871",
     "chipset": "MT6895 Dimensity 8200 Ultimate",
     "tags": ["MediaTek", "MDL", "PL", "DA", "TMETA", "MDM", "UBL"], "verified": False},
    {"brand": "Infinix", "model": "GT 30 5G", "code": "X6876",
     "chipset": "MT7400-class Dimensity",
     "tags": ["MediaTek", "MDL", "PL", "DA"], "verified": False},
    {"brand": "Infinix", "model": "GT 30 Pro 5G", "code": "X6873",
     "chipset": "MT6833 Dimensity 700-class",
     "tags": ["MediaTek", "MDL", "PL", "DA"], "verified": False},
    {"brand": "Infinix", "model": "Hot 10", "code": "X682C",
     "chipset": "MT6768 Helio G70",
     "tags": ["MediaTek", "MDL", "PL", "DA"], "verified": False},
    {"brand": "Infinix", "model": "HOT 70", "code": "X6895B",
     "chipset": "Helio G100",
     "tags": ["MediaTek", "TMETA", "MDM", "UBL"], "verified": False},
    {"brand": "Tecno", "model": "Spark Go 3", "code": "KN3",
     "chipset": "Unisoc T606_64",
     "tags": ["Unisoc", "FDL", "Diag", "MDM", "Exploit"], "verified": False},
]


def load_models():
    """tools/mdm-models.json parho. Dedicated DB agent wali schema:
    bare array ya {"models": [...]}; har entry {brand, model, code,
    chipset, tags, verified}. Purani {name,...} entries bhi normalize
    ho jati hain. File na ho to SEED_MODELS se ban jati hai.
    Returns (models, note|None)."""
    path = MODELS_FILE
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"models": SEED_MODELS}, indent=2),
                            encoding="utf-8")
        except Exception:
            pass
        return [dict(m) for m in SEED_MODELS], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data if isinstance(data, list) else data.get("models", [])
        models = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            m = dict(entry)
            if not m.get("name"):
                m["name"] = (str(m.get("brand", "")) + " "
                             + str(m.get("model", ""))).strip() or "Unknown"
            m.setdefault("code", "")
            m.setdefault("chipset", "")
            m.setdefault("tags", [])
            models.append(m)
        if models:
            return models, None
        return [dict(m) for m in SEED_MODELS], "models file khaali — seed list use ho rahi hai"
    except Exception as e:  # noqa: BLE001
        return [dict(m) for m in SEED_MODELS], f"seed (JSON parh nahi saka: {e})"


def model_label(m):
    parts = [m.get("name", "")]
    tail = " - ".join(x for x in (m.get("code", ""), m.get("chipset", "")) if x)
    if tail:
        parts.append(tail)
    label = " — ".join(parts)
    if m.get("verified"):
        label += " ✓"
    return label


def model_tabs(m):
    """Model ke tags/chipset-family se kaun se mode tabs nazar ayenge.

    MTK models: Download (sirf MDL/PL/DA tags par) / Transsion META
    (sirf TMETA par) / ADB / FASTBOOT.
    Unisoc models (Fenix screens batch 3+4): Download / DIAG / Network
    / PATCHER / ADB / FASTBOOT — aur module header me FDL Exploit
    checkbox (fdl_exploit flag).
    """
    tags = {t.upper() for t in m.get("tags", [])}
    if "UNISOC" in tags:
        return {"download": True, "diag": True, "network": True,
                "patcher": True, "adb": True, "fastboot": True,
                "fdl_exploit": True}
    return {
        "download": bool(tags & {"MDL", "PL", "DA"}),
        "meta": "TMETA" in tags,
        "adb": True,
        "fastboot": True,
    }


def da_files():
    """tools/loaders/ ke tamam .bin files (Download tab ke DA dropdown ke liye)."""
    base = TOOLS_DIR / "loaders"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.bin") if p.is_file())


# --------------------------------------------------------------------------
# Action factories — har factory aik runner-compatible op object deta hai
# (OP dict + run(ctx)); execution hamesha runner ke through hoti hai.
# --------------------------------------------------------------------------
def _op(op_id, name, run, engine="mdm-list"):
    return SimpleNamespace(OP={
        "id": op_id, "category": "MDM / Transsion", "name": name,
        "engine": engine, "modes": (), "server_required": False,
    }, run=run)


def _engine_or_fail(ctx):
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
        else:
            ctx.log(note, "ERROR")
            ctx.log("Guide: MTKClient app ke engines/mtkclient/ folder "
                    "me hona chahiye.", "WARN")
        return None, None
    return cmd, cwd


def _brom_guard(ctx):
    dev = ctx.device
    if not dev or dev.mode not in ("BROM", "PRELOADER"):
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band "
                "karke Volume dono dabaye hue cable lagao (kuch models "
                "par test-point lagta hai).", "ERROR")
        return False
    return True


# ---------------------------------------------------------------------------
# New-Auth guard (FENIX-FEATURES-RESEARCH §4.3): sab se naye Dimensity chips
# par META entry "new Auth" mang sakti hai jo server-assisted ho sakti hai —
# wahan TMETA ops guided-FAIL karte hain, fake success kabhi nahi.
# ---------------------------------------------------------------------------

NEW_AUTH_TOKENS = ("MT6835", "MT6878", "MT6983",
                   "Dimensity 6300", "Dimensity 6400", "Dimensity 7300",
                   "Dimensity 9000", "Dimensity 9400")


def _new_auth_guard(ctx, model):
    """True = aage barho; False = guided fail ho chuka."""
    hay = " ".join([str(model.get("chipset", "")), str(ctx.device.chip or "")])
    hit = next((x for x in NEW_AUTH_TOKENS if x.lower() in hay.lower()), None)
    if not hit:
        return True
    ctx.log("Chip pehchana gaya: %s — is class par META entry ke liye 'new "
            "Auth' darkar ho sakta hai (research §4.3)." % hit, "WARN")
    ctx.log("Ye auth server-assisted ho sakti hai aur public tor par "
            "documented nahi — is liye TMETA route yahan ruk raha hai.",
            "ERROR")
    ctx.log("Doosra darwaza: Download/BROM route (agar tags me MDL/DA ho) "
            "ya ADB tab ke ops try karen.", "INFO")
    return False


def download_frp_op(model, da_path):
    """Download tab: FACTORY RESET + FRP - [GPT] — muntakhib DA ke saath."""
    label = "FACTORY RESET + FRP - [GPT]"

    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        if da_path is None:
            ctx.log("Koi DA file muntakhib nahi.", "ERROR")
            ctx.log("Guide: is model ka DA (.bin) app ke tools/loaders/ "
                    "folder me rakho, phir dropdown se select karke "
                    "dobara chalao. Ghalat DA phone ko nuksan de sakta "
                    "hai — sirf isi model ka DA istemal karo.", "WARN")
            return False
        if not _brom_guard(ctx):
            return False
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        extra = ["--loader", str(da_path)]
        ctx.log(f"DA: {da_path}", "INFO")
        steps = [("frp", True), ("userdata", True),
                 ("metadata", False), ("persist", False)]
        for i, (part, fatal) in enumerate(steps):
            if ctx.is_cancelled():
                return False
            ctx.progress(10 + i * 20, f"{part} erase ho raha hai...")
            code = ctx.stream(cmd + ["e", part] + extra,
                              timeout=300, cwd=cwd)
            if code != 0:
                if fatal:
                    ctx.log(f"{part} erase fail hua (exit code {code}) — "
                            "DA is model ka na ho sakta hai, ya device "
                            "BROM se nikal gaya.", "ERROR")
                    return False
                ctx.log(f"{part} erase nahi hua — kuch devices par ye "
                        "partition hota hi nahi ya mehfooz hota hai; "
                        "aage barh rahe hain.", "WARN")
        ctx.progress(90, "Reset bheja ja raha hai...")
        ctx.stream(cmd + ["reset"] + extra, timeout=180, cwd=cwd)
        return True

    return _op("mdm_list_download_frp", label, run, engine="mtkclient")


def meta_unlock_op(model):
    def run(ctx):
        if not _new_auth_guard(ctx, model):
            return False
        ctx.log(f"Model: {model_label(model)} — TMETA route "
                "(Preloader/META connection se seccfg amal).", "INFO")
        import ops.mtk_bl_unlock as m
        return m.run(ctx)
    return _op("mdm_list_meta_unlock",
               "UNLOCK BOOTLOADER NEW SEC - [TMETA]", run, engine="mtkclient")


def meta_frp_op(model):
    def run(ctx):
        if not _new_auth_guard(ctx, model):
            return False
        ctx.log(f"Model: {model_label(model)} — TMETA route "
                "(FRP + reset, persist ke saath).", "INFO")
        import ops.mtk_frp_reset as m
        return m.run(ctx)
    return _op("mdm_list_meta_frp",
               "FACTORY RESET + FRP - [TMETA]", run, engine="mtkclient")


def meta_security_plugin_op(model):
    def run(ctx):
        if not _new_auth_guard(ctx, model):
            return False
        ctx.log(f"Model: {model_label(model)}", "INFO")
        dev = ctx.device
        if dev and dev.mode == "ADB":
            ctx.log("Device ADB mode me hai — Security Plugin op ka "
                    "package wala rasta chal raha hai.", "INFO")
            import ops.mdm_security_plugin as m
            return m.run(ctx)
        if dev and dev.mode in ("BROM", "PRELOADER"):
            ctx.log("Device BROM/Preloader me hai — package removal ADB "
                    "se hota hai; yahan se sirf persist (MDM config) "
                    "erase ho sakta hai, jo lock ke wapas ane ki jad "
                    "kaat-ta hai.", "WARN")
            cmd, cwd = _engine_or_fail(ctx)
            if cmd is None:
                return False
            code = ctx.stream(cmd + ["e", "persist"] +
                              engines.mtk_extra_args(), timeout=300, cwd=cwd)
            if code == 0:
                ctx.log("Persist erase ho gaya. Ab phone on karke ADB "
                        "mode me 'Security Plugin Remove' op chalao taake "
                        "package bhi saaf ho.", "OK")
                return True
            ctx.log("Persist erase nahi hua — partition mehfooz ho "
                    "sakta hai. ADB wala rasta try karo.", "ERROR")
            return False
        ctx.log("Device kisi mode me nahi mila — phone ko ADB (on "
                "karke) ya BROM/Preloader mode me lagao.", "ERROR")
        return False
    return _op("mdm_list_meta_security",
               "SECURITY PLUGIN NEW SEC - [TMETA]", run, engine="adb/mtkclient")


def meta_payjoy_op(model):
    def run(ctx):
        if not _new_auth_guard(ctx, model):
            return False
        ctx.log(f"Model: {model_label(model)}", "INFO")
        dev = ctx.device
        if dev and dev.mode == "ADB":
            import ops.mdm_payjoy as m
            return m.run(ctx)
        if dev and dev.mode in ("BROM", "PRELOADER"):
            ctx.log("PayJoy ka lock device-owner + backend check-in par "
                    "chalta hai — BROM se is ka koi public partition "
                    "rasta is build me NAHI hai (per-model data research "
                    "pending hai). Phone on karke ADB mode me lagao — "
                    "wahan detection + imaandar natija milega; device-"
                    "owner surat me asal hal PayJoy ki authorized "
                    "release hi hai.", "ERROR")
            return False
        ctx.log("Device kisi mode me nahi mila — phone ADB mode me "
                "lagao.", "ERROR")
        return False
    return _op("mdm_list_meta_payjoy",
               "BYPASS PAYJOY ALL SEC - [TMETA]", run, engine="adb")


def meta_enable_adb_op(model):
    def run(ctx):
        if not _new_auth_guard(ctx, model):
            return False
        ctx.log(f"Model: {model_label(model)}", "INFO")
        ctx.log("Ye amal phone ke META connection ko verify karta "
                "hai — ADB enable ka koi universal command maujood "
                "nahi; ye model ke META firmware par munhasir hai. "
                "META port mil jaye to connection tayyar samjho.",
                "WARN")
        import ops.mdm_meta_guide as m
        return m.run(ctx)
    return _op("mdm_list_meta_enable_adb",
               "ENABLE ADB - [TMETA]", run, engine="guide")


def meta_disable_adb_op(model):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        dev = ctx.device
        if not dev or dev.mode != "ADB":
            ctx.log("Device ADB mode me nahi hai — ADB band karne ke "
                    "liye phone pehle ADB mode me laga hona chahiye.",
                    "ERROR")
            return False
        adb = engines.find_platform_tool("adb")
        ctx.log("adb_enabled = 0 bheja ja raha hai — is ke baad USB "
                "debugging band ho jayegi aur ADB connection kat "
                "sakta hai (yehi is amal ka maqsad hai).", "WARN")
        code = ctx.stream([adb, "-s", dev.serial, "shell", "settings",
                           "put", "global", "adb_enabled", "0"],
                          timeout=30)
        if code == 0:
            ctx.log("ADB disable ka hukum bhej diya gaya.", "OK")
            return True
        ctx.log(f"Command fail hua (exit code {code}).", "ERROR")
        return False
    return _op("mdm_list_meta_disable_adb",
               "DISABLE ADB - [TMETA]", run, engine="adb")


def meta_restore_mdm_op(model):
    """RESTORE MDM - [TMETA]: model ke ORIGINAL proinfo backup ko wapas
    likhta hai (patch se pehle wali halat) — backup library se."""
    def run(ctx):
        if not _new_auth_guard(ctx, model):
            return False
        ctx.log(f"Model: {model_label(model)}", "INFO")
        if not _brom_guard(ctx):
            return False
        code = (model.get("code") or "").lower()
        name_slug = "".join(ch.lower() if ch.isalnum() else "-"
                            for ch in model.get("name", "")).strip("-")
        candidates = []
        if BACKUP_DIR.is_dir():
            for p in BACKUP_DIR.rglob("*.bin"):
                if "proinfo" not in p.name.lower():
                    continue
                folder = p.parent.name.lower()
                if (code and code in folder) or \
                        (name_slug and name_slug in folder) or \
                        (code and code in p.name.lower()):
                    candidates.append(p)
        if not candidates:
            ctx.log("Is model ka original proinfo backup library me "
                    "nahi mila.", "ERROR")
            ctx.log("Guide: RESTORE MDM ke liye pehle us model ka saaf "
                    "backup 'Proinfo Backup (MDM Library)' op se lena "
                    "hota hai — backups tools/mdm-backups/<model>/ me "
                    "bante hain. Baghair backup ke restore mumkin "
                    "nahi, aur tool nakli restore nahi karega.", "WARN")
            return False
        src = max(candidates, key=lambda p: p.stat().st_mtime)
        ctx.log(f"Restore file: {src}", "INFO")
        ctx.log("Ye ASAL partition write hai — sirf isi model ki apni "
                "original file likhi ja rahi hai.", "WARN")
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        code_rc = ctx.stream(cmd + ["w", "proinfo", str(src)] +
                             engines.mtk_extra_args(),
                             timeout=300, cwd=cwd)
        if code_rc == 0:
            ctx.log("Original proinfo wapas likh di gayi — MDM halat "
                    "backup wali surat par restore ho gayi.", "OK")
            return True
        ctx.log(f"Proinfo write fail hua (exit code {code_rc}).",
                "ERROR")
        return False
    return _op("mdm_list_meta_restore",
               "RESTORE MDM - [TMETA]", run, engine="mtkclient")


# META tab ke buttons ki tartib (Fenix screens ke mutabiq)
META_ACTIONS = [
    ("UNLOCK BOOTLOADER NEW SEC - [TMETA]", meta_unlock_op),
    ("SECURITY PLUGIN NEW SEC - [TMETA]", meta_security_plugin_op),
    ("BYPASS PAYJOY ALL SEC - [TMETA]", meta_payjoy_op),
    ("FACTORY RESET + FRP - [TMETA]", meta_frp_op),
    ("ENABLE ADB - [TMETA]", meta_enable_adb_op),
    ("DISABLE ADB - [TMETA]", meta_disable_adb_op),
    ("RESTORE MDM - [TMETA]", meta_restore_mdm_op),
]


# ==========================================================================
# UNISOC (SPD) side — Fenix screens batch 3+4 (Tecno Spark Go 3, KN3)
# DIAG tab = Unisoc ka TMETA. Hamare paas apna FDL engine v1 me NAHI hai
# (SPD coverage = official tools launcher + PAC guide) — is liye DIAG
# ops imaandari se teen surton me hain: (a) ADB mode par asal delegate,
# (b) SPD/DIAG port ki asal verification, (c) guided FAIL jahan engine
# ya per-model data maujood nahi.
# ==========================================================================
def _adb_guard(ctx):
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai — phone on karke USB "
                "debugging ON karo aur lagao.", "ERROR")
        return False
    return True


def _fdl_note(ctx, fdl_provider):
    on = False
    try:
        on = bool(fdl_provider()) if fdl_provider else False
    except Exception:
        on = False
    ctx.log(f"FDL Exploit route: {'ON' if on else 'OFF'} "
            f"({'exploit FDL' if on else 'stock PAC wale FDL'}).", "INFO")
    return on


def diag_unlock_op(model, fdl_provider=None):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        ctx.log("Unisoc bootloader unlock DIAG/FDL protocol se hota "
                "hai — hamare paas apna FDL engine is build me NAHI "
                "hai (SPD coverage: official tools launcher + PAC "
                "guide).", "ERROR")
        ctx.log("Guide: rasta ye hai — model ka stock PAC tools/spd/ "
                "me rakho, SPD tab ke official tools se kaam karo. "
                "Jhooti one-click unlock yahan nahi di gayi.", "WARN")
        return False
    return _op("mdm_list_diag_unlock",
               "UNLOCK BOOTLOADER NEW SEC - [DIAG]", run, engine="spd-diag")


def diag_security_plugin_op(model, fdl_provider=None):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        dev = ctx.device
        if dev and dev.mode == "ADB":
            import ops.mdm_security_plugin as m
            return m.run(ctx)
        ctx.log("DIAG mode se package removal prodnv partition "
                "mechanism se hota hai — us ka engine is build me "
                "nahi (research pending). Phone ADB mode me lagao to "
                "package wala asal rasta chalega (Security Plugin "
                "Remove op).", "ERROR")
        return False
    return _op("mdm_list_diag_security",
               "SECURITY PLUGIN NEW SEC - [DIAG]", run, engine="adb/spd-diag")


def diag_payjoy_op(model, fdl_provider=None):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        dev = ctx.device
        if dev and dev.mode == "ADB":
            import ops.mdm_payjoy as m
            return m.run(ctx)
        ctx.log("PayJoy ka hal DIAG se is build me maujood nahi — "
                "phone ADB mode me lagao, wahan detection + imaandar "
                "natija milega (device-owner surat me asal rasta "
                "PayJoy ki authorized release hai).", "ERROR")
        return False
    return _op("mdm_list_diag_payjoy",
               "BYPASS PAYJOY ALL SEC - [DIAG]", run, engine="adb")


def diag_payjoy_frp_op(model, fdl_provider=None):
    """Combo: pehle PayJoy (ADB), phir FRP ke liye PAC guide wala rasta."""
    def run(ctx):
        ctx.log(f"Model: {model_label(model)} — COMBO: PayJoy + FRP",
                "INFO")
        _fdl_note(ctx, fdl_provider)
        if not _adb_guard(ctx):
            return False
        import ops.mdm_payjoy as pj
        if not pj.run(ctx):
            ctx.log("Combo pehle hisay (PayJoy) par ruk gaya — upar "
                    "wajah dekho. FRP wala hisa nahi chalaya gaya.",
                    "ERROR")
            return False
        ctx.log("PayJoy hisa ho gaya. Ab FRP ke liye PAC wala rasta:",
                "INFO")
        import ops.spd_frp_pac_guide as guide
        return guide.run(ctx)
    return _op("mdm_list_diag_payjoy_frp",
               "BYPASS PAYJOY ALL SEC + FRP - [DIAG]", run, engine="adb/spd")


def diag_black_screen_op(model, fdl_provider=None):
    """BLACK SCREEN NEW SEC — research §4.9: fix = per-model prodnv
    byte-pattern patch (library data). Library me model ka prodnv backup
    ho to wahi route; warna stock PAC route (pakka ilaj, fix ki
    guarantee nahi)."""
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        slug = (model.get("code") or model.get("name", "")).replace(" ", "-").lower()
        found = []
        lib = TOOLS_DIR / "mdm-backups"
        if lib.exists() and slug:
            for d in lib.iterdir():
                if d.is_dir() and slug in d.name.lower():
                    found += [f for f in d.rglob("*prodnv*") if f.is_file()]
        if found:
            ctx.log("Library me is model ka prodnv backup MILA: %s"
                    % found[0], "OK")
            ctx.log("Route: SPD Research Tool se ye prodnv wapas likhen "
                    "(DIAG/FDL session) — black-screen pattern isi state "
                    "me theek hota hai.", "INFO")
        else:
            ctx.log("Library me is model ka prodnv backup NAHI — ye fix "
                    "model-data ke baghair mumkin nahi. Pehle kisi theek "
                    "phone se prodnv backup library me rakhen.", "WARN")
            ctx.log("Filhal stock PAC flash route khul raha hai — ye "
                    "black screen fix ki guarantee nahi.", "INFO")
        import ops.spd_launcher as launcher
        return launcher.run(ctx)
    return _op("mdm_list_diag_blackscreen",
               "BLACK SCREEN NEW SEC - [DIAG]", run, engine="spd")


def diag_enable_adb_op(model, fdl_provider=None):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        dev = ctx.device
        if dev and dev.mode == "ADB":
            ctx.log("ADB pehle se ON hai — device ADB mode me mila.",
                    "OK")
            return True
        from core import device_watch
        found = [d for d in device_watch.scan_serial_modes()
                 if d.mode == "SPD"]
        if found:
            ctx.log(f"DIAG port mil gaya: {found[0].detail or found[0].port} "
                    "— connection tayyar hai. ADB enable ka asal command "
                    "set model ke DIAG firmware par munhasir hai; koi "
                    "universal command maujood nahi.", "OK")
            return True
        ctx.log("Na ADB mila na DIAG (SPD) port — phone band karke "
                "Volume keys dabaye hue cable lagao (DIAG port Device "
                "Manager me Spreadtrum Diag ayega).", "ERROR")
        return False
    return _op("mdm_list_diag_enable_adb",
               "ENABLE ADB - [DIAG]", run, engine="spd-diag")


def diag_disable_adb_op(model, fdl_provider=None):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        base = meta_disable_adb_op(model)
        return base.run(ctx)
    return _op("mdm_list_diag_disable_adb",
               "DISABLE ADB - [DIAG]", run, engine="adb")


def diag_restore_mdm_op(model, fdl_provider=None):
    """RESTORE MDM - [DIAG]: Unisoc ki MDM data prodnv me hoti hai.
    Library se model ka prodnv backup dhoondhta hai; asal write
    Research Tool + PAC se hota hai (hamare paas FDL writer nahi)."""
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        _fdl_note(ctx, fdl_provider)
        code = (model.get("code") or "").lower()
        found = []
        if BACKUP_DIR.is_dir():
            for p in BACKUP_DIR.rglob("*.bin"):
                if "prodnv" in p.name.lower() and (
                        not code or code in p.parent.name.lower()
                        or code in p.name.lower()):
                    found.append(p)
        if not found:
            ctx.log("Is model ka prodnv backup library me nahi mila.",
                    "ERROR")
            ctx.log("Guide: pehle Research Tool se is model ke saaf "
                    "phone ka prodnv backup lekar tools/mdm-backups/"
                    "<model>/ me rakho — baghair backup ke restore "
                    "mumkin nahi.", "WARN")
            return False
        src = max(found, key=lambda p: p.stat().st_mtime)
        ctx.log(f"Prodnv backup mila: {src}", "INFO")
        ctx.log("Asal write-back Research Download se hota hai: stock "
                "PAC load karo, sirf prodnv partition select karke is "
                "file se flash karo. Hamare tool ke paas apna FDL "
                "writer is build me NAHI hai — is liye write yahan se "
                "nahi chalayi gayi (nakli restore nahi hoga).", "WARN")
        return False
    return _op("mdm_list_diag_restore",
               "RESTORE MDM - [DIAG]", run, engine="spd-diag")


def diag_power_off_op(model, fdl_provider=None):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        dev = ctx.device
        if not dev or dev.mode != "ADB":
            ctx.log("POWER OFF sirf ADB mode se bheja ja sakta hai — "
                    "DIAG port se power command ka channel is build "
                    "me nahi.", "ERROR")
            return False
        adb = engines.find_platform_tool("adb")
        code = ctx.stream([adb, "-s", dev.serial, "reboot", "-p"],
                          timeout=30)
        if code == 0:
            ctx.log("Power off ka hukum bhej diya gaya.", "OK")
            return True
        ctx.log(f"Command fail hua (exit code {code}).", "ERROR")
        return False
    return _op("mdm_list_diag_poweroff",
               "POWER OFF - [DIAG]", run, engine="adb")


# DIAG tab ke buttons ki tartib (Fenix screens batch 3+4 ke mutabiq)
DIAG_ACTIONS = [
    ("UNLOCK BOOTLOADER NEW SEC - [DIAG]", diag_unlock_op),
    ("SECURITY PLUGIN NEW SEC - [DIAG]", diag_security_plugin_op),
    ("BLACK SCREEN NEW SEC - [DIAG]", diag_black_screen_op),
    ("BYPASS PAYJOY ALL SEC - [DIAG]", diag_payjoy_op),
    ("BYPASS PAYJOY ALL SEC + FRP - [DIAG]", diag_payjoy_frp_op),
    ("ENABLE ADB - [DIAG]", diag_enable_adb_op),
    ("DISABLE ADB - [DIAG]", diag_disable_adb_op),
    ("RESTORE MDM - [DIAG]", diag_restore_mdm_op),
    ("POWER OFF - [DIAG]", diag_power_off_op),
]


# ==========================================================================
# Network tab (Unisoc) — IMEI / MAC / Cert
# Usool (Hamza ka pakka): IMEI sirf ORIGINAL (dabbe/sticker wala) restore
# hota hai — change/clone kabhi nahi. Aur NV ka koi bhi kaam ho, pehle
# Backup Cert lazmi hai.
# ==========================================================================
def _adb_capture(adb, serial, args, timeout=20):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([adb, "-s", serial] + args,
                             capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def _luhn_ok(num):
    if not num.isdigit() or len(num) != 15:
        return False
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _read_ids(ctx, adb, serial):
    """ADB se IMEI/MAC parhne ki asal koshish — jo mile wahi wapas."""
    ids = {"imei1": "", "imei2": "", "bt_mac": "", "wifi_mac": ""}
    dump = _adb_capture(adb, serial, ["shell", "dumpsys", "iphonesubinfo"])
    found = []
    for cand in re.findall(r"\b\d{15}\b", dump or ""):
        if _luhn_ok(cand) and cand not in found:
            found.append(cand)
    props = _adb_capture(adb, serial, ["shell", "getprop"])
    for key in ("ril.imei", "gsm.baseband.imei", "persist.radio.imei"):
        for line in (props or "").splitlines():
            if key in line:
                for cand in re.findall(r"\b\d{15}\b", line):
                    if _luhn_ok(cand) and cand not in found:
                        found.append(cand)
    if found:
        ids["imei1"] = found[0]
        if len(found) > 1:
            ids["imei2"] = found[1]
    bt = _adb_capture(adb, serial,
                      ["shell", "settings", "get", "secure",
                       "bluetooth_address"]).strip()
    if re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", bt or ""):
        ids["bt_mac"] = bt.upper()
    wifi = _adb_capture(adb, serial,
                        ["shell", "cat", "/sys/class/net/wlan0/address"]
                        ).strip()
    if re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", wifi or ""):
        ids["wifi_mac"] = wifi.upper()
    return ids


def _model_folder(model):
    code = (model.get("code") or "").strip()
    if code:
        return code
    return "".join(ch.lower() if ch.isalnum() else "-"
                   for ch in model.get("name", "model")).strip("-")


def network_read_op(model):
    def run(ctx):
        if not _adb_guard(ctx):
            return False
        adb = engines.find_platform_tool("adb")
        ids = _read_ids(ctx, adb, ctx.device.serial)
        got = False
        for key, label in (("imei1", "IMEI 1"), ("imei2", "IMEI 2"),
                           ("bt_mac", "BT MAC"), ("wifi_mac", "WiFi MAC")):
            if ids[key]:
                ctx.log(f"{label}: {ids[key]}", "DATA")
                got = True
        if not got:
            ctx.log("IMEI/MAC parha nahi ja saka — kuch firmwares ADB "
                    "se ye maloomat band rakhte hain (root/DIAG ke "
                    "baghair). Ye nakami saaf report ki gayi hai.",
                    "ERROR")
            return False
        ctx.log("Upar wali values Network tab ke fields me likh lo — "
                "Restore Original IMEI ke liye dabbe wala asal number "
                "hi istemal hoga.", "INFO")
        return True
    return _op("mdm_list_net_read", "READ IMEI - [NETWORK]", run, engine="adb")


def network_backup_cert_op(model):
    """Backup Cert — NV kaam se pehle lazmi. ADB se parhi hui cert
    maloomat (IMEI/MAC + device info) library me mehfooz karta hai;
    asal NV partition backup PAC/Research route se hota hai (guide)."""
    def run(ctx):
        if not _adb_guard(ctx):
            return False
        adb = engines.find_platform_tool("adb")
        dev = ctx.device
        ids = _read_ids(ctx, adb, dev.serial)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = BACKUP_DIR / _model_folder(model) / f"cert-{ts}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            record = {
                "model": model.get("name", ""), "code": model.get("code", ""),
                "brand": dev.brand, "device_model": dev.model,
                "chip": dev.chip, "serial": dev.serial,
                "when": datetime.now().isoformat(timespec="seconds"),
                "ids": ids,
                "note": "Cert maloomat ka backup (ADB se parha hua). "
                        "Asal NV partition backup Research Tool / PAC "
                        "route se hota hai.",
            }
            (folder / "cert-info.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Cert backup likha nahi ja saka: {e}", "ERROR")
            return False
        ctx.log(f"Cert backup mehfooz: {folder}", "OK")
        for key, label in (("imei1", "IMEI 1"), ("imei2", "IMEI 2"),
                           ("bt_mac", "BT MAC"), ("wifi_mac", "WiFi MAC")):
            if ids[key]:
                ctx.log(f"{label}: {ids[key]}", "DATA")
        ctx.log("Note: ye cert ki MALOOMAT ka backup hai. Asal NV "
                "partition ka backup Research Tool se PAC ke saath "
                "hota hai — khatarnak NV kaam se pehle wo bhi lazmi "
                "samjho.", "WARN")
        return True
    return _op("mdm_list_net_backup_cert", "BACKUP CERT - [NETWORK]",
               run, engine="adb")


def _find_cert_backup(model):
    base = BACKUP_DIR / _model_folder(model)
    if not base.is_dir():
        return None
    certs = sorted(base.glob("cert-*/cert-info.json"))
    return certs[-1] if certs else None


def network_restore_cert_op(model):
    def run(ctx):
        cert = _find_cert_backup(model)
        if cert is None:
            ctx.log("Is model ka cert backup library me nahi mila — "
                    "pehle BACKUP CERT chalao.", "ERROR")
            return False
        ctx.log(f"Cert backup mila: {cert}", "INFO")
        try:
            data = json.loads(cert.read_text(encoding="utf-8"))
            ids = data.get("ids", {})
            for key, label in (("imei1", "IMEI 1"), ("imei2", "IMEI 2"),
                               ("bt_mac", "BT MAC"),
                               ("wifi_mac", "WiFi MAC")):
                if ids.get(key):
                    ctx.log(f"{label}: {ids[key]}", "DATA")
        except Exception:
            pass
        ctx.log("Asal NV restore Research Download se hota hai (PAC "
                "ke saath NV items wapas likhe jate hain) — hamare "
                "paas apna FDL/NV writer is build me NAHI hai, is "
                "liye restore yahan se execute nahi hui. Backup ki "
                "values upar mehfooz hain.", "WARN")
        return False
    return _op("mdm_list_net_restore_cert", "RESTORE CERT - [NETWORK]",
               run, engine="adb")


def network_restore_imei_op(model, imei_provider):
    """RESTORE ORIGINAL IMEI — sirf dabbe/sticker wala asal number.
    Pehle Backup Cert lazmi (gate), IMEI ki Luhn tasdeeq asal hoti
    hai; NV write ka engine (DIAG/FDL) is build me nahi — imaandar
    guided natija."""
    def run(ctx):
        ctx.log("Usool: yahan sirf phone ka ORIGINAL IMEI (dabbe/"
                "sticker wala) restore hota hai — IMEI change ya "
                "clone kabhi nahi.", "WARN")
        try:
            imei1, imei2 = imei_provider()
        except Exception:
            imei1, imei2 = "", ""
        imei1 = (imei1 or "").strip()
        imei2 = (imei2 or "").strip()
        if not imei1:
            ctx.log("IMEI 1 field khali hai — Network tab me dabbe "
                    "wala asal IMEI likho.", "ERROR")
            return False
        for label, val in (("IMEI 1", imei1), ("IMEI 2", imei2)):
            if val and not _luhn_ok(val):
                ctx.log(f"{label} durust nahi lagta (15 hindsay + "
                        "checksum fail): {val}", "ERROR")
                return False
        if _find_cert_backup(model) is None:
            ctx.log("Pehle BACKUP CERT lazmi hai — NV ke kisi kaam se "
                    "pehle backup ke baghair aage nahi barhte. Pehle "
                    "Backup Cert chalao.", "ERROR")
            return False
        ctx.log(f"IMEI 1 (original): {imei1}", "DATA")
        if imei2:
            ctx.log(f"IMEI 2 (original): {imei2}", "DATA")
        ctx.log("Tayyari mukammal hai (backup maujood, IMEI valid) — "
                "lekin asal NV write DIAG/FDL engine se hoti hai jo "
                "is build me NAHI hai. Is liye write execute nahi "
                "hui; values tumhare cert backup me mehfooz hain aur "
                "asal write official DIAG route se hogi.", "WARN")
        return False
    return _op("mdm_list_net_restore_imei",
               "RESTORE ORIGINAL IMEI - [NETWORK]", run, engine="adb")


# ==========================================================================
# PATCHER tab — PATCH ANTICRACK DISABLE - [PAC FIRMWARE]
# Offline file op: stock .pac andar, "patched" copy bahir. IMAANDARI:
# anticrack ka byte-level patch mechanism public tor par established
# NAHI hai — is liye ye op asal me sirf aik working copy + patch
# report banata hai aur guided FAIL deta hai. Nakli patch kabhi nahi.
# ==========================================================================
def pac_patch_op(model, pac_path):
    def run(ctx):
        ctx.log(f"Model: {model_label(model)}", "INFO")
        if pac_path is None or not Path(pac_path).is_file():
            ctx.log("Koi .pac file muntakhib nahi hui — PATCHER tab "
                    "se pehle stock .pac select karo.", "ERROR")
            return False
        src = Path(pac_path)
        if src.suffix.lower() != ".pac":
            ctx.log(f"Ye .pac file nahi lagti: {src.name}", "ERROR")
            return False
        out_dir = src.parent / "patched"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / (src.stem + "_workingcopy.pac")
            dst.write_bytes(src.read_bytes())
            report = out_dir / (src.stem + "_patch-report.txt")
            report.write_text(
                "MEER TOOL PRO — PAC patch report\n"
                f"Model: {model_label(model)}\n"
                f"Source: {src}\nWorking copy: {dst}\n"
                f"Size: {src.stat().st_size} bytes\n\n"
                "HALAT: Anticrack ka byte-level patch mechanism "
                "public tor par established nahi hai — is liye ye "
                "copy ABHI UNMODIFIED hai. Ise 'patched' samajh kar "
                "flash MAT karo. Asal patch data research se sabit "
                "hone par hi is op me shamil hoga.\n",
                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Working copy nahi ban saki: {e}", "ERROR")
            return False
        ctx.log(f"Working copy tayyar: {dst}", "INFO")
        ctx.log(f"Patch report: {report}", "INFO")
        ctx.log("Lekin imaandari se: anticrack patch ka asal "
                "mechanism abhi public research se sabit NAHI hua — "
                "is copy me koi byte patch NAHI lagi. Ise patched "
                "samajh kar flash karna khatarnak hoga. Ye op abhi "
                "designed/guided halat me hai.", "WARN")
        return False
    return _op("mdm_list_patcher_anticrack",
               "PATCH ANTICRACK DISABLE - [PAC FIRMWARE]", run,
               engine="local-file")
