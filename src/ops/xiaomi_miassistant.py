"""
xiaomi_miassistant.py — Xiaomi MiAssistant sideload se Recovery ROM flash.

Xiaomi phones Recovery me 'Connect with MiAssistant' select karne
par ADB 'sideload' state me ate hain — is halat me official
Recovery ROM (.zip) `adb sideload` se bheja jata hai. Ye op pehle
`adb devices` se halat ASAL me parhta hai (sideload confirm kiye
baghair kuch nahi bhejta), phir tools/firmware-xiaomi/ ki AKELI
.zip bhejta hai.

Imaandari: exit 0 = ROM transfer mukammal. MiAssistant flash se
Mi Account / FRP lock NAHI jata — wo Xiaomi ke server se bandha
hai, is op ka aisa koi daawa nahi.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from core import engines
from core.runner import TOOLS_DIR

OP = {
    "id": "xiaomi_miassistant",
    "category": "Xiaomi",
    "name": "MiAssistant Sideload Flash (Recovery ROM)",
    "engine": "adb",
    "modes": (),
    "server_required": False,
}


def _run_quiet(cmd, timeout=20):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        return (out.stdout or "") + "\n" + (out.stderr or "")
    except Exception:  # noqa: BLE001
        return ""


def parse_adb_devices(text):
    """`adb devices` output → [(serial, state), ...] (pure)."""
    found = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) >= 2:
            found.append((parts[0].strip(), parts[1].strip().lower()))
    return found


def run(ctx) -> bool:
    adb = engines.find_platform_tool("adb")
    if not Path(adb).is_file() and shutil.which(adb) is None:
        ctx.log("adb nahi mila — platform-tools setup chahiye "
                "(engines/platform-tools/ ya tools/platform-tools/).",
                "ERROR")
        return False

    # --- Device halat: sideload confirm kiye baghair aage nahi ----------
    ctx.progress(15, "adb devices parha ja raha hai...")
    devices = parse_adb_devices(_run_quiet([adb, "devices"], timeout=20))
    sideload = [s for s, st in devices if st == "sideload"]
    normal = [s for s, st in devices if st == "device"]
    unauth = [s for s, st in devices if st == "unauthorized"]
    offline = [s for s, st in devices if st == "offline"]

    if normal and not sideload:
        ctx.log("Phone normal ADB mode me hai — MiAssistant sideload "
                "ke liye pehle: (1) phone ko Recovery me lao (band "
                "karke Vol Up + Power dabao, Xiaomi logo par chhoro), "
                "(2) Recovery menu me 'Connect with MiAssistant' "
                "select karo, (3) cable lagi rehne do, (4) ye op "
                "dobara chalao. Abhi ROM nahi bheja jayega.", "ERROR")
        return False
    if unauth and not sideload:
        ctx.log("Device 'unauthorized' hai — phone ki screen par "
                "'Allow USB debugging' ka prompt aya hoga, use Allow "
                "karo (ya Recovery me 'Connect with MiAssistant' "
                "select karo) aur op dobara chalao.", "ERROR")
        return False
    if offline and not sideload:
        ctx.log("Device 'offline' hai — cable nikaal kar dobara "
                "lagao, doosri cable/port try karo, phir op dobara "
                "chalao.", "ERROR")
        return False
    if not sideload:
        ctx.log("Koi device sideload halat me nahi mila. Phone ko "
                "Recovery me lao (Vol Up + Power) → 'Connect with "
                "MiAssistant' select karo → cable lagao → op dobara "
                "chalao.", "ERROR")
        return False
    serial = sideload[0]
    ctx.log(f"Device sideload halat me mila: {serial}", "OK")

    # --- ROM: bilkul aik .zip -------------------------------------------
    folder = TOOLS_DIR / "firmware-xiaomi"
    zips = []
    if folder.is_dir():
        zips = sorted(p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() == ".zip")
    if not zips:
        ctx.log("Recovery ROM nahi mili. Is model ki official "
                "Recovery ROM (.zip) tools/firmware-xiaomi/ folder "
                "me rakho — sirf wahi ROM jo bilkul is model ke "
                "liye ho (ghalat ROM = brick ka khatra).", "ERROR")
        return False
    if len(zips) > 1:
        names = ", ".join(p.name for p in zips)
        ctx.log(f"firmware-xiaomi/ me {len(zips)} .zip files hain "
                f"({names}) — ghalat ROM bhejna khatarnak hai, is "
                "liye sirf AIK .zip rakho jo is model ki ho, baki "
                "hata do, phir op dobara chalao.", "ERROR")
        return False
    rom = zips[0]
    ctx.log(f"ROM: {rom.name}", "DATA")

    # --- Imaandar notes (flash se pehle lazmi) ---------------------------
    ctx.log("Note: MiAssistant-mode flash aksar models par "
            "userdata wipe kar deta hai (factory reset jaisa "
            "asar), lekin ye model par depend karta hai — customer "
            "ko pehle bata do aur mumkin ho to backup mashwara do.",
            "WARN")
    ctx.log("Note: Mi Account / FRP lock is se NAHI jata — wo "
            "Xiaomi ke SERVER se bandha hai; is op ka aisa koi "
            "daawa nahi.", "WARN")
    ctx.log("Note: sirf official Recovery ROM istemal karo jo "
            "bilkul is model ke liye ho — ghalat ROM brick kar "
            "sakta hai.", "WARN")

    if ctx.is_cancelled():
        ctx.log("ROM bhejne se pehle cancel kar diya gaya.", "WARN")
        return False

    # --- Sideload ---------------------------------------------------------
    ctx.progress(30, "ROM bheja ja raha hai (waqt lag sakta hai)...")
    ctx.log("ROM transfer shuru — cable mat nikalna...", "CMD")
    code = ctx.stream([adb, "-s", serial, "sideload", str(rom)],
                      timeout=2400)
    if ctx.is_cancelled():
        ctx.log("Transfer ke darmiyan cancel hua — phone ki halat "
                "screen par check karo; ROM na-mukammal gaya ho to "
                "Recovery me ja kar op dobara chalao.", "WARN")
        return False
    if code != 0:
        ctx.log(f"adb sideload fail hua (exit code {code}) — upar "
                "wali output dekho: aksar wajah ghalat/na-mukammal "
                "ROM, cable masla, ya phone ka sideload se bahar "
                "ana hoti hai. Halat check karke op dobara chalao.",
                "ERROR")
        return False

    ctx.progress(95, "ROM transfer mukammal")
    ctx.log("ROM transfer mukammal (adb ne exit 0 diya). Phone ab "
            "khud ROM install karega — screen par progress dekho, "
            "mukammal hone par phone reboot hoga. Pehli boot me "
            "waqt lag sakta hai.", "OK")
    ctx.log("Yaad rahe: Mi Account / FRP pehle se laga tha to wo "
            "setup par waisa hi rahega — ye server ka lock hai, "
            "flash se nahi jata.", "INFO")
    return True
