"""
adb_remove_ads.py — Remove Ads (ADB Servicing Tasks pack).

TSM/UAT class ke tools "servicing tasks" advertise karte
hain — ye pack unhi public ADB kaamon ko asal op banata hai
(TSM-UAT-RESEARCH §5 G-C). Packages core/app_profiles.py ke
profiles se ate hain: Xiaomi/MIUI device par 'xiaomi_ads_set'
(MSA / systemAdSolution / analytics), warna 'generic_bloat_admin'
(Facebook/Microsoft ke system ad components).

Tareeqa: `pm disable-user --user 0` — baghair root, baghair
uninstall; Restore Ads op se (ya Settings se) wapas enable
ho jata hai.

IMAANDARI:
  - Root: NAHI chahiye (log me saaf likha jata hai).
  - Jo package device par installed hi nahi, wo SKIP hota
    hai — nakami nahi (profiles TEMPLATE hain).
  - SUCCESS sirf device-side saboot par: disable ke baad
    `pm list packages -d` me wo package asal me nazar aye.
    Sirf command chal jana kaafi nahi.
"""

import subprocess
import sys

from core import app_profiles, engines

OP = {
    "id": "adb_remove_ads",
    "category": "ADB / Fastboot",
    "name": "Remove Ads (Servicing)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}


def guard(ctx):
    """(adb, serial) ya (None, None) — ADB ops ka mushtaraka
    guard."""
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai — phone on karke "
                "USB debugging ON karo.", "ERROR")
        return None, None
    adb = engines.find_platform_tool("adb")
    if adb is None:
        ctx.log("adb nahi mila (engines/platform-tools check "
                "karo).", "ERROR")
        return None, None
    return adb, dev.serial


def sh(adb, serial, args, timeout=60):
    """adb shell capture — (output, exit_code)."""
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([str(adb), "-s", serial, "shell"] +
                             [str(a) for a in args],
                             capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        return (out.stdout or "") + (out.stderr or ""), out.returncode
    except Exception as e:  # noqa: BLE001
        return f"error: {e}", -1


def _package_set(adb, serial, extra_args):
    out, _ = sh(adb, serial, ["pm", "list", "packages"] + extra_args)
    pkgs = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.add(line[len("package:"):].strip())
    return pkgs


def pick_ads_profile_key(brand_text):
    """Brand/model ke matan se ads profile chuno (pure)."""
    text = (brand_text or "").lower()
    if any(b in text for b in ("xiaomi", "redmi", "poco", "miui")):
        return "xiaomi_ads_set"
    return "generic_bloat_admin"


def apply_and_verify(ctx, adb, serial, packages, action):
    """packages par disable/enable lagao + device se verify.

    action: "disable" | "enable"
    Returns (done, failed, skipped) teeno lists.
    disable: sirf installed packages target hote hain; saboot
    = `pm list packages -d` me maujoodgi.
    enable: sirf jo is waqt disabled hain; saboot = disabled
    list se ghayab hona.
    """
    installed = _package_set(adb, serial, [])
    disabled = _package_set(adb, serial, ["-d"])
    done, failed, skipped = [], [], []
    if action == "disable":
        targets = []
        for pkg in packages:
            if pkg not in installed:
                skipped.append(pkg)
                ctx.log(f"SKIP {pkg} — device par installed nahi "
                        "(ye nakami nahi hai).", "INFO")
            elif pkg in disabled:
                done.append(pkg)
                ctx.log(f"{pkg} pehle se disabled hai.", "INFO")
            else:
                targets.append(pkg)
        for pkg in targets:
            out, _ = sh(adb, serial,
                        ["pm", "disable-user", "--user", "0", pkg])
            ctx.log(f"pm disable-user {pkg}: "
                    f"{out.strip() or '(no output)'}", "DATA")
        if targets:
            disabled_after = _package_set(adb, serial, ["-d"])
            for pkg in targets:
                (done if pkg in disabled_after else failed).append(pkg)
    else:  # enable
        targets = []
        for pkg in packages:
            if pkg not in disabled:
                skipped.append(pkg)
            else:
                targets.append(pkg)
        for pkg in targets:
            out, _ = sh(adb, serial, ["pm", "enable", pkg])
            ctx.log(f"pm enable {pkg}: "
                    f"{out.strip() or '(no output)'}", "DATA")
        if targets:
            disabled_after = _package_set(adb, serial, ["-d"])
            for pkg in targets:
                (failed if pkg in disabled_after else done).append(pkg)
    return done, failed, skipped


def run(ctx) -> bool:
    adb, serial = guard(ctx)
    if adb is None:
        return False
    dev = ctx.device
    brand_text = f"{getattr(dev, 'brand', '') or ''} " \
                 f"{getattr(dev, 'model', '') or ''}"
    key = pick_ads_profile_key(brand_text)
    profiles = app_profiles.all_profiles()
    prof = profiles.get(key)
    if prof is None:
        ctx.log(f"Profile '{key}' nahi mila — app files check "
                "karo.", "ERROR")
        return False
    ctx.log("Root: NAHI chahiye — ye aam ADB shell ka kaam hai.",
            "INFO")
    ctx.log(f"Profile: {prof['name']} ({key}) — brand ke hisaab "
            f"se chuna gaya ({brand_text.strip() or 'unknown'}).",
            "INFO")
    ctx.log("Tareeqa: pm disable-user (uninstall NAHI) — Restore "
            "Ads op se kabhi bhi wapas enable ho jayega.", "INFO")
    ctx.progress(35, "Ads packages disable ho rahe hain...")
    done, failed, skipped = apply_and_verify(
        ctx, adb, serial, prof["packages"], "disable")
    for pkg in done:
        ctx.log(f"✓ {pkg} disabled (device list se verify).",
                "DATA")
    for pkg in failed:
        ctx.log(f"✗ {pkg} disable NAHI hua (ROM ne ijazat nahi "
                "di — kuch OEM shells system apps par pabandi "
                "lagate hain).", "WARN")
    if failed:
        ctx.log(f"Natija: {len(done)} disable hue, "
                f"{len(failed)} nakam — poora kaam nahi hua, is "
                "liye FAIL.", "ERROR")
        return False
    if not done:
        ctx.log("Is device par is profile ka koi package "
                "installed nahi mila — disable karne ko kuch "
                "tha hi nahi.", "ERROR")
        return False
    ctx.log(f"Remove Ads mukammal — {len(done)} packages "
            "disable + device se verify shuda.", "OK")
    ctx.progress(95, "Remove Ads mukammal")
    return True
