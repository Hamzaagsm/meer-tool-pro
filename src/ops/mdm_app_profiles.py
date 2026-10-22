"""
mdm_app_profiles.py — App Disable Profiles (AppTool parity).

CM2 ke [AppTool] "Load list to Disable" wali design
(COMPETITOR-RESEARCH-3 §2.2): tayyar disable-profiles +
user ke apne saved templates, ADB `pm disable-user` se
har app ka alag natija log karke.

Profile ka intikhab: tools/app-profiles.json me "active"
custom profile ho to wahi; warna device ke brand se
built-in (Transsion / Samsung / generic). Amal se pehle
MANDATORY snapshot backup (mdm_security_plugin wali
discipline), aakhir me verify, aur jo list asal me lagi
wo custom template ke tor par save ho jati hai — doosre
device par wohi list dobara istemal ke liye (CM2 parity).

Label discipline: app-disable ka natija hamesha BYPASS hai
(reversible amal hai; PERMANENT sirf state-layer patch
path hai).
"""

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core import app_profiles, engines
from core.runner import TOOLS_DIR

OP = {
    "id": "mdm_app_profiles",
    "category": "MDM / Transsion",
    "name": "App Disable Profiles (AppTool)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}


def _run_adb(adb, serial, args):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            [adb, "-s", serial, "shell"] + list(args),
            capture_output=True, text=True, timeout=20, **kwargs)
        return (out.stdout or "") + "\n" + (out.stderr or "")
    except Exception:  # noqa: BLE001
        return ""


def _resolve_adb(ctx):
    path = engines.find_platform_tool("adb")
    if Path(path).is_file() or shutil.which(path):
        return path
    ctx.log("adb nahi mila — platform-tools app ke engines/platform-tools/ "
            "ya tools/platform-tools/ folder me, ya PATH me chahiye.", "ERROR")
    return None


def _parse_packages(text):
    pkgs = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            line = line[len("package:"):].strip()
        if line:
            pkgs.append(line)
    return pkgs


def _list_packages(adb, serial, extra=()):
    return _parse_packages(
        _run_adb(adb, serial, ["pm", "list", "packages"] + list(extra)))


def _snapshot_backup(ctx, dev, profile_name, packages, targets):
    """MANDATORY auto-backup: amal se pehle detection snapshot."""
    slug = re.sub(r"[^a-z0-9]+", "-",
                  (dev.model or "device").lower()).strip("-") or "device"
    folder = TOOLS_DIR / "mdm-backups" / slug
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"apptool-snapshot-{ts}.txt"
    body = [
        "MEER Tool Pro — AppTool profile snapshot (amal se pehle)",
        f"Waqt: {ts}",
        f"Device: {dev.brand or ''} {dev.model or ''}  serial: {dev.serial or ''}",
        f"Profile: {profile_name}",
        "",
        "Profile targets jo device par installed mile:",
        *[f"  - {pkg}" for pkg in targets],
        "",
        "== pm list packages ==",
        *packages,
    ]
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(body), encoding="utf-8")
        return path
    except Exception:  # noqa: BLE001
        return None


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai. Phone on karke USB debugging "
                "ON karo aur dobara lagao — ye op sirf ADB mode me "
                "chalta hai.", "ERROR")
        return False
    adb = _resolve_adb(ctx)
    if adb is None:
        return False

    profiles = app_profiles.all_profiles()
    key = app_profiles.pick_profile_key(dev.brand or "")
    profile = profiles.get(key) or profiles["generic_bloat_admin"]
    ctx.log(f"Profile muntakhib: {profile['name']} [{key}]", "INFO")
    ctx.log(profile["description"], "INFO")
    others = [p["name"] for k, p in profiles.items() if k != key]
    if others:
        ctx.log("Dastiyab profiles: " + "; ".join(others) + " — apna "
                "template tools/app-profiles.json me 'custom' ke tor "
                "par save karke 'active' set karne se wahi lagta hai.",
                "INFO")

    ctx.progress(20, "Packages parhe ja rahe hain...")
    packages = _list_packages(adb, dev.serial)
    if not packages:
        ctx.log("Device se packages ki list nahi ayi — cable / 'Allow "
                "USB debugging' check karke dobara try karo.", "ERROR")
        return False
    installed_lower = {p.lower() for p in packages}
    targets = [p for p in profile["packages"]
               if p.lower() in installed_lower]
    skipped = [p for p in profile["packages"]
               if p.lower() not in installed_lower]
    for pkg in skipped:
        ctx.log(f"Skip: {pkg} — device par installed nahi.", "INFO")
    if not targets:
        ctx.log("Is profile ka koi package is device par installed "
                "nahi mila — karne ko kuch nahi. Device is profile "
                "ke hisaab se saaf hai.", "OK")
        ctx.progress(95, "Profile check mukammal — koi target nahi")
        return True

    # MANDATORY auto-backup (amal se pehle)
    ctx.progress(30, "Auto-backup (snapshot) ban raha hai...")
    snap = _snapshot_backup(ctx, dev, profile["name"], packages, targets)
    if snap is None:
        ctx.log("Auto-backup snapshot NAHI ban saka — backup ke baghair "
                "amal aage nahi barhega (ye lazmi qadam hai). tools/ "
                "folder ki write permission check karen.", "ERROR")
        return False
    ctx.log(f"Auto-backup snapshot tayyar: {snap}", "OK")

    ctx.progress(45, "Profile lagaya ja raha hai (pm disable-user)...")
    for pkg in targets:
        if ctx.is_cancelled():
            return False
        code = ctx.stream([adb, "-s", dev.serial, "shell",
                           "pm", "disable-user", "--user", "0", pkg],
                          timeout=60)
        ctx.log(f"{pkg} — pm disable-user exit code: {code}", "INFO")

    ctx.progress(75, "Natija verify ho raha hai...")
    after_disabled = {p.lower() for p in _list_packages(adb, dev.serial, ["-d"])}
    applied = []
    failed = []
    for pkg in targets:
        if pkg.lower() in after_disabled:
            applied.append(pkg)
            ctx.log(f"{pkg}: disable hai (verify shuda).", "OK")
        else:
            failed.append(pkg)
            ctx.log(f"{pkg}: disable NAHI hua (device-owner/system "
                    "protection ho sakti hai).", "ERROR")

    # CM2 parity: jo list asal me lagi, use template bana kar save
    if applied:
        ts = time.strftime("%Y%m%d-%H%M%S")
        tname = f"applied-{key.split(':')[-1]}-{ts}"
        if app_profiles.save_custom_profile(tname, applied):
            ctx.log(f"Lagayi gayi list template ke tor par save ho "
                    f"gayi: '{tname}' (tools/app-profiles.json) — "
                    "doosre device par yehi list 'active' karke "
                    "dobara lag sakti hai.", "OK")

    ctx.log("NATJA: BYPASS — app-disable reversible amal hai, ye "
            "PERMANENT removal NAHI hai. Device-owner wala MDM ya "
            "firmware-resident plugin reset/re-provisioning par "
            "wapas aa sakta hai; mustaqil rasta state-layer patch "
            "hai (MDM Pack ke proinfo/prodnv ops).", "WARN")
    if failed:
        return False
    ctx.progress(95, "Profile lag gaya — natija: BYPASS (upar note parho)")
    return True
