"""
mdm_finance_check.py — Finance-Lock Detector (ADB).

Phone par lage financing locks ki PEHCHAN: PayJoy, Easybuy
(Transsion security plugin), NuovoPay, d.light PayGo, Samsung
Knox Guard client, Google Device Lock Controller — package
list se, core/finance_locks.py ke database se.

Ye sirf DETECTION hai — koi remove button ya daawa nahi. Har
lock ke saath imaandar verdict line ati hai ke public removal
rasta hai ya nahi (COMPETITOR-RESEARCH-3 §3). IT Admin / aam
device-owner MDM finance se ALAG label hokar ata hai (CM2 ki
tarah IT Admin aur MDM ko alag pehchanna — §2.2 ka sabak).
"""

import shutil
import subprocess
import sys
from pathlib import Path

from core import engines, finance_locks

OP = {
    "id": "mdm_finance_check",
    "category": "MDM / Transsion",
    "name": "Finance Lock Detector (ADB)",
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


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai. Phone on karke USB debugging "
                "ON karo aur dobara lagao — ye detector sirf ADB mode me "
                "chalta hai.", "ERROR")
        return False
    adb = _resolve_adb(ctx)
    if adb is None:
        return False

    ctx.progress(25, "Packages parhe ja rahe hain...")
    packages = _parse_packages(
        _run_adb(adb, dev.serial, ["pm", "list", "packages"]))
    ctx.progress(55, "Device-owner halat parhi ja rahi hai...")
    dumpsys_text = _run_adb(adb, dev.serial, ["dumpsys", "device_policy"])
    if not packages and not dumpsys_text.strip():
        ctx.log("Device se jawab nahi aya — packages aur device_policy "
                "dono khali aye. Cable check karo aur phone par 'Allow "
                "USB debugging' Allow karke dobara try karo.", "ERROR")
        return False

    findings = finance_locks.classify_finance_locks(packages, dumpsys_text)
    ctx.progress(85, "Natija tayyar hai")

    if not findings:
        ctx.log("Koi mashhoor financing lock nahi mila (PayJoy / "
                "Easybuy / NuovoPay / d.light / Knox Guard / Google "
                "DLC — kisi ka package installed nahi).", "OK")
        ctx.log("Note: ye package-based pehchan hai — jo finance "
                "system firmware ke andar bina alag package ke rehta "
                "ho, wo is scan me nahi ayega; shak ho to MDM Check "
                "(ADB) ki device-owner report bhi dekho.", "INFO")
        return True

    ctx.log(f"{len(findings)} financing lock mile:", "WARN")
    platform_hit = False
    for f in findings:
        ctx.log(f"🔒 {f['name']} — package: {f['package']}"
                + (" (device-owner bhi hai)" if f["is_device_owner"] else ""),
                "WARN")
        ctx.log(f"   Verdict: {f['verdict']}", "INFO")
        if f["kind"] == "platform-finance":
            platform_hit = True
    if platform_hit:
        ctx.log(finance_locks.PLATFORM_NOTE, "INFO")
    ctx.log("Ye sirf PEHCHAN (detection) hai — in locks ka removal "
            "is report se nahi hota; har lock ka asal rasta upar "
            "us ki verdict line me likha hai.", "INFO")
    return True
