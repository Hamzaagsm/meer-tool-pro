"""
oneplus_arb_warning.py — ColorOS 16 ARB Fuse Warning (OnePlus).

GUIDE OP — koi flash, koi write nahi. Sirf build version parh
kar fuse status batata hai aur fused phone par EDL flash se
rokta hai.

SERVER-REQUIRED-ROUTES-RESEARCH-2 §4.2(b): ColorOS 16.0.3.500+
update karte hi QFPROM eFuse blow hota hai — purana ROM flash =
hard brick, motherboard hi rasta; fused par EDL unbrick band,
server bhi nahi. OnePlus ka statement (downgrade wapas ayega)
vs XDA "permanent fuse" — dono likhe jate hain (core.arb_check).

Flow:
  1. ADB device ho to getprop se build version parho
     (ro.build.version.oplusrom / ro.build.display.id /
     ro.build.version.incremental).
  2. Device na ho to guide: Settings → About phone → Version
     se build parho, phir dobara chalao.
  3. Fuse status + warning lines log karo. Fused ho to saaf
     FAIL jaisa rok-lagao (return False — flash ke liye unsafe),
     not-fused / unknown par guide ke saath True (unknown par
     bhi flash se pehle check ki warning ke saath).

EDL flash link: is op ko qc_edl_flash ke saath link karne ka
snippet parent report me hai — qc_edl_flash.py khud EDIT NAHI
hua (shared-file rule).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from core import arb_check, device_watch, engines

OP = {
    "id": "oneplus_arb_warning",
    "category": "Qualcomm",
    "name": "OnePlus ARB Fuse Warning (ColorOS 16)",
    "engine": "guide",
    "modes": (),
    "server_required": False,
}

_BUILD_PROPS = (
    "ro.build.version.oplusrom",
    "ro.build.display.id",
    "ro.build.version.incremental",
)


def build_from_props(props):
    """getprop dict se pehli usable build string (pure)."""
    for key in _BUILD_PROPS:
        val = str((props or {}).get(key, "") or "").strip()
        if val:
            return val
    return ""


def _resolve_adb(ctx):
    adb = engines.find_platform_tool("adb")
    if Path(adb).is_file() or shutil.which(adb):
        return adb
    ctx.log("adb nahi mila — platform-tools app ke tools/ folder me "
            "ya PATH me chahiye.", "ERROR")
    return None


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


def run(ctx) -> bool:
    dev = getattr(ctx, "device", None)
    build = ""
    model = ""
    if dev is not None:
        model = " ".join(str(x or "") for x in
                         (getattr(dev, "brand", ""),
                          getattr(dev, "model", ""),
                          getattr(dev, "chip", ""))).strip()
    if dev is not None and getattr(dev, "mode", "") == "ADB":
        adb = _resolve_adb(ctx)
        if adb is None:
            return False
        ctx.progress(30, "Build version parha ja raha hai...")
        props = device_watch.adb_getprops(adb, dev.serial)
        build = build_from_props(props)
        if not build:
            ctx.log("ADB se build version nahi mili — getprop khali aya.",
                    "WARN")
    elif dev is not None:
        ctx.log("Device ADB mode me nahi hai — fuse check ke liye phone "
                "ON karke ADB mode me lagao (USB debugging ON).",
                "WARN")

    if not build:
        ctx.log("OnePlus ARB fuse check — build version ke baghair "
                "faisla nahi ho sakta:", "INFO")
        ctx.log("Phone par: Settings → About phone → Version → "
                "build number parho (masalan 16.0.3.500). Phir phone "
                "ADB mode me laga kar ye op dobara chalao — ya build "
                "number upar wali line se milao: 16.0.3.500 ya us se "
                "naya = FUSED.", "INFO")
        for line in arb_check.arb_warning_lines("unknown"):
            ctx.log(line, "WARN")
        ctx.log("Affected models: OnePlus 13, 13T, 15, Ace 5, Ace 5 Pro "
                "(ColorOS 16 CN builds; OxygenOS same codebase).",
                "INFO")
        return True

    result = arb_check.check_build(build, model)
    ctx.log(f"Model: {model or 'na-maloom'}", "INFO")
    if result["affected_model"]:
        ctx.log("Ye model ARB-fuse wali list me hai (OnePlus 13 / 13T / "
                "15 / Ace 5 / Ace 5 Pro).", "WARN")
    for line in result["lines"]:
        ctx.log(line, "WARN" if result["status"] == "fused" else "INFO")
    if result["status"] == "fused":
        ctx.log("⛔ FUSED hai — is phone par purana ROM / EDL downgrade "
                "FLASH MAT KARO. Fused par EDL unbrick band hai — "
                "server bhi nahi, motherboard hi rasta hai. Ye op "
                "is liye FAIL de raha hai taake ghalat flash se "
                "brick na ho.", "ERROR")
        ctx.progress(95, "ARB fuse check: FUSED — flash roko")
        return False
    ctx.progress(95, "ARB fuse check mukammal")
    return True
