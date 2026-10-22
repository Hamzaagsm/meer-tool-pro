"""
mdm_adb_check.py — Transsion MDM pack: ADB se MDM / device-owner check.

`dumpsys device_policy` aur `pm list packages` asal me phone se parh
kar batata hai ke koi device-owner MDM active hai ya nahi. Ye sirf
CHECK hai — removal is op se nahi hota. Transsion par removal ka
mechanism proinfo (MTK) / prodnv (SPD) partition se hai, aur per-model
patch data tumhare apne backups se ayega; tool kisi model ko pehle
se supported nahi kehta.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from core import engines, finance_locks

OP = {
    "id": "mdm_adb_check",
    "category": "MDM / Transsion",
    "name": "MDM Check (ADB)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

_OWNER_KEYS = ("device owner", "profile owner")
_FINDING_KEYS = ("Device Owner", "Profile Owner", "device owner", "admin")


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


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai. Phone on karke USB debugging "
                "ON karo aur dobara lagao — ye check sirf ADB mode me "
                "chalta hai.", "ERROR")
        return False
    adb = _resolve_adb(ctx)
    if adb is None:
        return False

    ctx.progress(20, "device_policy parha ja raha hai...")
    dumpsys_text = _run_adb(adb, dev.serial, ["dumpsys", "device_policy"])
    ctx.progress(55, "packages ki list parhi ja rahi hai...")
    packages_text = _run_adb(adb, dev.serial, ["pm", "list", "packages"])

    if not dumpsys_text.strip() and not packages_text.strip():
        ctx.log("Device se jawab nahi aya — dono commands khali aye. "
                "Cable check karo aur phone par 'Allow USB debugging' "
                "Allow karke dobara try karo.", "ERROR")
        return False

    # dumpsys findings: Device Owner / Profile Owner / admin wali lines
    findings = []
    seen = set()
    for raw in dumpsys_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(key in line for key in _FINDING_KEYS):
            if line not in seen:
                seen.add(line)
                findings.append(line)
            if len(findings) >= 10:
                break

    # packages: sirf naam wala hissa (package: prefix hata kar)
    packages = []
    for raw in packages_text.splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            line = line[len("package:"):].strip()
        if line:
            packages.append(line)

    suspicious = [p for p in packages
                  if "mdm" in p.lower() or "kiosk" in p.lower()
                  or "deviceowner" in p.lower()]
    transsion_pkgs = [p for p in packages if "transsion" in p.lower()]

    for pkg in transsion_pkgs:
        ctx.log(f"Transsion system package: {pkg} — ye system packages "
                "hain, MDM ka saboot nahi.", "INFO")
    for pkg in suspicious:
        ctx.log(f"MDM-shuba wala package mila: {pkg}", "WARN")
    for line in findings:
        ctx.log(f"device_policy: {line}", "DATA")

    # Finance-lock pehchan (P1): PayJoy / Easybuy / NuovoPay /
    # d.light / Knox Guard / Google DLC — verdict lines ke saath.
    finance = finance_locks.classify_finance_locks(packages, dumpsys_text)
    for f in finance:
        ctx.log(f"FINANCE LOCK mila: {f['name']} ({f['package']})"
                + (" (device-owner bhi hai)" if f["is_device_owner"] else ""),
                "WARN")
        ctx.log(f"   Verdict: {f['verdict']}", "INFO")
    if finance:
        ctx.log("Tafseeli finance report ke liye 'Finance Lock "
                "Detector (ADB)' op bhi maujood hai.", "INFO")

    owner_found = any(
        any(key in line.lower() for key in _OWNER_KEYS) for line in findings
    )

    ctx.progress(90, "Check mukammal")
    if owner_found:
        for line in findings:
            if any(key in line.lower() for key in _OWNER_KEYS):
                ctx.log(f"MDM ACTIVE hai — owner package: {line}", "WARN")
        ctx.log("Removal Transsion par proinfo (MTK) / prodnv (SPD) "
                "partition mechanism se hota hai — is pack ke Proinfo "
                "ops dekho; per-model patch data tumhare apne backups "
                "se ayega, tool kisi model ko pehle se supported nahi "
                "kehta.", "INFO")
        return True

    ctx.log("Koi device-owner MDM active nahi mila.", "OK")
    return True
