"""
mdm_payjoy.py — Transsion MDM pack: PayJoy lock ki pehchan aur removal.

PayJoy aik financing lock hai. Ye op sirf us device par istemal ke
liye hai jis ka haq malik ko haasil hai (qarz mukammal/shuda device).
Detection hamesha asal package list se hoti hai — jo package asal
me mile wahi log hota hai.

Imaandar bunyaad: PayJoy aam tor par DEVICE OWNER ke tor par chalta
hai, aur us surat me ADB se asal removal mumkin NAHI — ye SERVER /
authorized-removal wala case hai (qarz mukammal hone par PayJoy khud
backend se lock release karta hai). Sirf sideloaded / non-owner
surat me ADB disable/uninstall asal me ho sakta hai, aur wahan bhi
success sirf verify ke baad milta hai. NATIJA hamesha "BYPASSED"
kehlata hai, "permanent/removed" kabhi nahi — PayJoy apne server
se check-in karta hai (research §2), aur Fenix bhi isay BYPASS hi
kehta hai. Partition-level per-model data research-pending hai —
koi patch andaze se nahi likha gaya.

Source: FENIX-FEATURES-RESEARCH.md (2026-10-22) — asal package naam
aur device-owner / server-release haqeeqat wahan ki tehqeeq se hai.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from core import engines

OP = {
    "id": "mdm_payjoy",
    "category": "MDM / Transsion",
    "name": "PayJoy Lock Remove",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

_EXACT_PAYJOY = "com.payjoy.access"
_PKG_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+", re.IGNORECASE)
_OWNER_KEYS = ("device owner", "profile owner")


def _run_adb(adb, serial, args):
    """adb shell command chala kar output text wapas karo (khali bhi ho sakti hai)."""
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
    text = _run_adb(adb, serial, ["pm", "list", "packages"] + list(extra))
    return _parse_packages(text), text


def _owner_packages(dumpsys_text, installed_lower):
    """dumpsys device_policy se device-owner package(s) — installed list me hon to."""
    owners = set()
    for raw in (dumpsys_text or "").splitlines():
        line = raw.strip()
        low = line.lower()
        if any(k in low for k in _OWNER_KEYS) or "admin" in low \
                or "package=" in low:
            for tok in _PKG_RE.findall(line):
                if tok.lower() in installed_lower:
                    owners.add(tok)
    return owners


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

    ctx.progress(15, "PayJoy package aur device-owner parhe ja rahe hain...")
    packages, packages_raw = _list_packages(adb, dev.serial)
    disabled, _ = _list_packages(adb, dev.serial, ["-d"])
    dumpsys_text = _run_adb(adb, dev.serial, ["dumpsys", "device_policy"])

    if not packages_raw.strip() and not dumpsys_text.strip():
        ctx.log("Device se jawab nahi aya — packages aur device_policy "
                "dono khali aye. Cable check karo aur phone par 'Allow "
                "USB debugging' Allow karke dobara try karo.", "ERROR")
        return False

    installed = list(packages)
    for pkg in disabled:
        if pkg not in installed:
            installed.append(pkg)
    installed_lower = {p.lower() for p in installed}
    owners = _owner_packages(dumpsys_text, installed_lower)
    owners_lower = {o.lower() for o in owners}

    # Detection: exact naam pehla target, "payjoy" token scan backup
    targets = []
    for pkg in installed:
        if pkg.lower() == _EXACT_PAYJOY:
            targets.append(pkg)
    for pkg in installed:
        if "payjoy" in pkg.lower() and pkg not in targets:
            targets.append(pkg)

    if not targets:
        ctx.log("Is device par PayJoy ka koi package nahi mila.", "INFO")
        ctx.progress(95, "Check mukammal — PayJoy nahi mila")
        return True

    for pkg in targets:
        ctx.log(f"PayJoy package mila: {pkg}", "DATA")
    payjoy_is_owner = any(p.lower() in owners_lower for p in targets)
    if owners:
        for owner in sorted(owners):
            is_payjoy_owner = "payjoy" in owner.lower()
            ctx.log(f"Device-owner package: {owner} — owner package "
                    f"payjoy wala {'hai' if is_payjoy_owner else 'nahi hai'}.",
                    "DATA")
    else:
        ctx.log("Koi device-owner package dumpsys me nahi mila.", "INFO")

    # --- Surat 1: PayJoy device-owner NAHI — ADB removal asal me mumkin hai
    if not payjoy_is_owner:
        ctx.progress(35, "PayJoy disable/uninstall ho raha hai...")
        for pkg in targets:
            if ctx.is_cancelled():
                return False
            code = ctx.stream(
                [adb, "-s", dev.serial, "shell", "pm", "disable-user",
                 "--user", "0", pkg], timeout=60)
            ctx.log(f"{pkg} — pm disable-user exit code: {code}", "INFO")
            if ctx.is_cancelled():
                return False
            code = ctx.stream(
                [adb, "-s", dev.serial, "shell", "pm", "uninstall",
                 "--user", "0", pkg], timeout=60)
            ctx.log(f"{pkg} — pm uninstall exit code: {code}", "INFO")

        ctx.progress(75, "Natija verify ho raha hai...")
        after_pkgs, _ = _list_packages(adb, dev.serial)
        after_disabled, _ = _list_packages(adb, dev.serial, ["-d"])
        remaining = {p.lower() for p in after_pkgs} | \
            {p.lower() for p in after_disabled}
        all_gone = True
        for pkg in targets:
            if pkg.lower() in remaining:
                all_gone = False
                ctx.log(f"{pkg}: ab bhi device par hai — removal verify "
                        "nahi hua.", "ERROR")
            else:
                ctx.log(f"{pkg}: gaya — package-level removal verify "
                        "hua (natija: BYPASSED).", "OK")
        if all_gone:
            ctx.log("NATJA: BYPASSED — package is device/user se hat "
                    "gaya hai, lekin ye 'permanent removal' NAHI "
                    "kehlata: PayJoy ka lock us ke server se bandha "
                    "hai (research §2).", "WARN")
            ctx.log("⚠ Warning: phone ke online hone par dobara lock "
                    "ho sakta hai agar contract open ho.", "WARN")
            ctx.progress(95, "PayJoy bypass mukammal (verify shuda)")
            return True
        ctx.log("PayJoy removal mukammal nahi hua — upar verify ki "
                "tafseel dekho.", "ERROR")
        return False

    # --- Surat 2: PayJoy device-owner HAI — ADB se asal removal mumkin nahi
    ctx.log("PayJoy device-owner ke tor par chal raha hai (uska admin "
            "receiver AccessAdminReceiver hai) — yehi wajah hai ke "
            "mamooli uninstall is par fail hota hai.", "WARN")
    ctx.progress(35, "PayJoy disable ki koshish ho rahi hai...")
    for pkg in targets:
        if pkg.lower() not in owners_lower:
            continue
        if ctx.is_cancelled():
            return False
        code = ctx.stream(
            [adb, "-s", dev.serial, "shell", "pm", "disable-user",
             "--user", "0", pkg], timeout=60)
        ctx.log(f"{pkg} — pm disable-user exit code: {code}", "INFO")

    ctx.progress(75, "Disable ki halat verify ho rahi hai...")
    after_disabled, _ = _list_packages(adb, dev.serial, ["-d"])
    after_disabled_lower = {p.lower() for p in after_disabled}
    for pkg in targets:
        if pkg.lower() not in owners_lower:
            continue
        if pkg.lower() in after_disabled_lower:
            ctx.log(f"{pkg}: disable hai — lock aarzi tor par be-asar "
                    "hai, lekin ye mustaqil removal NAHI hai.", "WARN")
        else:
            ctx.log(f"{pkg}: disable bhi verify nahi hua — package "
                    "ab bhi active halat me hai.", "WARN")
    ctx.log("Imaandar natija: device-owner package ADB se mukammal "
            "uninstall aam tor par NAHI hota. PayJoy app har ~60 second "
            "backend se check-in karti hai, is liye 'disable kar diya' "
            "mustaqil hal nahi — relock ho jata hai.", "WARN")
    ctx.log("NATJA label: BYPASSED (aarzi) — 'permanent/removed' "
            "kabhi nahi. ⚠ Warning: phone ke online hone par dobara "
            "lock ho sakta hai agar contract open ho.", "WARN")
    ctx.log("Brand route note: Transsion par asal state route TMETA "
            "session hai (MDM List → Transsion META tab); Samsung par "
            "ye KG/MDM family ka case hai — dono me server check-in "
            "wala lock sirf bypass hota hai.", "INFO")
    ctx.log("Mustaqil removal ke asal raste: (a) qarz mukammal hone "
            "par PayJoy ki apni official / backend (SERVER/authorized) "
            "release — asal aur mustaqil yahi rasta hai; (b) MTK model "
            "ho to stock firmware ki mukammal flash; (c) per-model "
            "partition data (research pending).", "INFO")
    return False
