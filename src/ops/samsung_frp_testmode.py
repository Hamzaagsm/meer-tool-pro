"""
samsung_frp_testmode.py — Samsung FRP Remove — Test Mode *#0*# (Free).

SERVER-REQUIRED research §4.3(a): public rasta — Emergency Dialer
se *#0*# → test menu → ADB enable → FRP reset. SamFw Tool v6.2
(Oct 2026, FREE) se sabit hai ke ye rasta ab bhi zinda hai — free
version December 2022 se purani firmware par kaam karta hai; us
ke baad paid server (SamFw Server 1/2).

MEER is method ko APNE engine me chalata hai (no-launcher rule:
SamFw ko bundle/launch NAHI karte — sirf public method implement
hota hai, MEER ki apni window/log me):

  1. User Emergency Dialer se *#0*# dial karta hai (phone FRP-locked
     hai — MEER khud dial nahi kar sakta; ye aik qadam user ka hai).
  2. Test mode me ADB nazar ata hai — MEER `adb devices` poll karta
     hai (150 s tak), device milte hi aage barhta hai.
  3. ADB shell se FRP reset: settings/secure me user_setup_complete
     aur device_provisioned = 1 (public documented ADB FRP method).
  4. Tasdeeq: dono values wapas parh kar "1" hon to hi SUCCESS —
     warna imaandar FAIL. Nakli "FRP removed" kabhi nahi.

Had (imaandari se): patch Dec 2022 se purana ho to free rasta
khula hai; us ke baad ka patch ho to test mode band hota hai —
ADB nazar hi nahi ayega aur op server-case guidance ke saath
ruk jayega. Latest-security Exynos/Qualcomm FRP aur KG lock is
op ka kaam NAHI (KG server-side state hai — alag "KG Status" op
dekho). Ye op koi partition nahi mitata, sirf settings likhta
hai; phone ko aakhir me user khud restart karta hai.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core import device_watch, engines

OP = {
    "id": "samsung_frp_testmode",
    "category": "Samsung",
    "name": "FRP Remove — Test Mode *#0*# (Free, Dec 2022 tak)",
    "engine": "adb",
    "modes": (),
    "server_required": False,
}

# Free boundary (SamFw v6.2, research §4.3a): firmware patch
# December 2022 ya us se purana → test-mode rasta khula.
FREE_YEAR, FREE_MONTH = 2022, 12

_WAIT_TIMEOUT_S = 150
_WAIT_POLL_S = 3


# ---------------------------------------------------------------------------
# Pure helpers (testable)
# ---------------------------------------------------------------------------
def parse_patch(patch):
    """Security patch string → (year, month) ya None.

    "2022-12-01" / "2022-12" dono chalte hain; kuch aur mile to None.
    """
    m = re.match(r"^\s*(\d{4})-(\d{1,2})(?:-\d{1,2})?\s*$",
                 str(patch or ""))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return year, month


def patch_is_free(patch):
    """True = free test-mode boundary ke andar (≤ Dec 2022);
    False = us ke baad (server case); None = patch parha nahi gaya."""
    parsed = parse_patch(patch)
    if parsed is None:
        return None
    year, month = parsed
    return (year, month) <= (FREE_YEAR, FREE_MONTH)


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


def frp_reset_cmds(adb, serial):
    """FRP reset ke ADB shell commands (argv lists) — public
    documented method: setup-complete flags settings/secure me 1."""
    return [
        [adb, "-s", serial, "shell", "content", "insert",
         "--uri", "content://settings/secure",
         "--bind", "name:s:user_setup_complete",
         "--bind", "value:s:1"],
        [adb, "-s", serial, "shell", "content", "insert",
         "--uri", "content://settings/secure",
         "--bind", "name:s:device_provisioned",
         "--bind", "value:s:1"],
    ]


def verify_cmds(adb, serial):
    """Tasdeeq ke commands — dono ka jawab "1" hona chahiye."""
    return [
        [adb, "-s", serial, "shell", "settings", "get", "secure",
         "user_setup_complete"],
        [adb, "-s", serial, "shell", "settings", "get", "secure",
         "device_provisioned"],
    ]


def is_settings_one(output):
    """`settings get` ka jawab "1" hai ya nahi (pure)."""
    text = str(output or "").strip()
    if not text:
        return False
    return text.splitlines()[-1].strip() == "1"


_SHELL_ERROR_WORDS = ("failed", "error", "securityexception",
                      "not found", "permission denied", "exception")


def looks_like_shell_error(output):
    """Shell command ki output me ghalti ki nishani (pure)."""
    low = str(output or "").lower()
    return any(w in low for w in _SHELL_ERROR_WORDS)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------
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


def _wait_for_adb(ctx, adb, timeout_s=_WAIT_TIMEOUT_S,
                  poll_s=_WAIT_POLL_S, run_quiet=_run_quiet):
    """Test mode me ADB nazar ane tak poll — serial ya None.

    Har poll par cancel check hota hai; timeout par None.
    """
    deadline = time.monotonic() + max(0.0, timeout_s)
    while True:
        if ctx.is_cancelled():
            return None
        devices = parse_adb_devices(run_quiet([adb, "devices"],
                                              timeout=20))
        for serial, state in devices:
            if state == "device":
                return serial
        for serial, state in devices:
            if state == "unauthorized":
                ctx.log("Device 'unauthorized' mila — phone ki "
                        "screen par 'Allow USB debugging' aya ho to "
                        "Allow karo, phir op dobara chalao.", "WARN")
                return None
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(poll_s, max(0.0, deadline - time.monotonic())))


def _resolve_adb(ctx):
    adb = engines.find_platform_tool("adb")
    if not Path(adb).is_file() and shutil.which(adb) is None:
        ctx.log("adb nahi mila — platform-tools app ke "
                "engines/platform-tools/ ya tools/platform-tools/ "
                "folder me, ya PATH me chahiye.", "ERROR")
        return None
    return adb


# ---------------------------------------------------------------------------
# Asal op
# ---------------------------------------------------------------------------
def run(ctx) -> bool:
    adb = _resolve_adb(ctx)
    if adb is None:
        return False

    dev = getattr(ctx, "device", None)
    serial = None
    if dev is not None and getattr(dev, "mode", None) == "ADB":
        serial = getattr(dev, "serial", "") or ""

    if not serial:
        ctx.log("Test Mode FRP — pehle phone par ye karo:", "INFO")
        ctx.log("1) Phone ON rakho, FRP (Google account) wali screen "
                "par raho.", "INFO")
        ctx.log("2) Emergency Dialer khol kar *#0*# dial karo — "
                "rang-biranga TEST MENU khul jaye to rasta khula "
                "hai.", "INFO")
        ctx.log("3) Cable lagi rehne do — MEER test mode me ADB "
                "nazr ane ka intezar kar raha hai (150 second "
                "tak)...", "INFO")
        ctx.progress(10, "Test mode me ADB ka intezar...")
        serial = _wait_for_adb(ctx, adb)
        if ctx.is_cancelled():
            return False
        if not serial:
            ctx.log("150 second me test mode wala ADB device nazar "
                    "nahi aya.", "ERROR")
            ctx.log("Aam wajahen: (a) *#0*# par test menu khula hi "
                    "nahi — is patch par test mode band hai "
                    "(Dec 2022 ke baad ke patches par aam hai); "
                    "(b) cable/driver masla — Device Manager me "
                    "Samsung ADB dikh raha hai ya nahi check karo.",
                    "WARN")
            ctx.log("Doosra darwaza: patch Dec 2022 se purana ho to "
                    "dobara koshish karo; naya patch ho to ye "
                    "server wala kaam hai (SamFw Server 1/2 jaisi "
                    "paid service) — MEER is par nakli FRP remove "
                    "nahi dega.", "INFO")
            return False
        ctx.log(f"Test mode ADB device mil gaya: {serial}", "OK")
    else:
        ctx.log(f"ADB device pehle se connected: {serial}", "OK")

    # --- Patch boundary parho (maloomat + ummeed, rok nahi) -----------
    patch = ""
    try:
        props = device_watch.adb_getprops(adb, serial)
        patch = (props or {}).get("ro.build.version.security_patch", "")
    except Exception:  # noqa: BLE001 — props na milen to bhi koshish jari
        props = {}
    if patch:
        ctx.log(f"Security Patch: {patch}", "DATA")
        free = patch_is_free(patch)
        if free is True:
            ctx.log("Patch Dec 2022 ya us se purana hai — test-mode "
                    "rasta is firmware par khula hona chahiye.", "OK")
        elif free is False:
            ctx.log("Patch Dec 2022 ke baad ka hai — is patch par "
                    "test mode aam tor par band hota hai. ADB nazar "
                    "aa raha hai is liye koshish jari hai, lekin "
                    "nakami par yehi wajah hogi (server case).",
                    "WARN")
    else:
        ctx.log("Security patch parha nahi gaya — koshish jari hai; "
                "nakami par patch tareekh check karo (Dec 2022 "
                "boundary).", "WARN")

    # --- FRP reset commands ---------------------------------------------
    ctx.progress(40, "FRP reset commands bheje ja rahe hain...")
    for cmd in frp_reset_cmds(adb, serial):
        if ctx.is_cancelled():
            return False
        out = _run_quiet(cmd, timeout=30)
        if looks_like_shell_error(out):
            ctx.log("FRP reset command ne ghalti di: "
                    + " ".join(out.strip().splitlines()[:2]), "ERROR")
            ctx.log("Doosra darwaza: (a) test menu se bahar nikal "
                    "kar dobara *#0*# karo; (b) patch Dec 2022 ke "
                    "baad ka ho to ye rasta band hai — server case.",
                    "INFO")
            return False
    ctx.log("Reset commands bhej diye gaye — tasdeeq ho rahi hai...",
            "INFO")

    # --- Tasdeeq: dono values "1" hon to hi SUCCESS ---------------------
    ctx.progress(70, "Tasdeeq: setup flags parhe ja rahe hain...")
    ok = True
    for cmd in verify_cmds(adb, serial):
        out = _run_quiet(cmd, timeout=30)
        val = str(out or "").strip().splitlines()
        got = val[-1].strip() if val else ""
        ctx.log(f"{cmd[-1]} = {got!r}", "DATA")
        if got != "1":
            ok = False
    if not ok:
        ctx.log("Tasdeeq NAKAM — setup flags '1' nahi hue. FRP "
                "remove NAHI hua (nakli success nahi di jayegi).",
                "ERROR")
        ctx.log("Doosra darwaza: phone ko test mode me dobara lao "
                "aur op dobara chalao; baar-baar nakami par patch "
                "Dec 2022 ke baad ka hoga — wo server case hai.",
                "INFO")
        return False

    ctx.progress(95, "FRP reset verify ho gaya")
    ctx.log("✔ FRP reset verify ho gaya — user_setup_complete aur "
            "device_provisioned dono '1' hain.", "OK")
    ctx.log("Ab phone ko restart karo — setup aage barhega aur "
            "Google account wali rok nahi ani chahiye. Agar phir "
            "bhi FRP screen aye to patch naya hoga — dobara "
            "*#0*# karke op chalao.", "INFO")
    ctx.log("Note: ye op FRP settings reset karta hai — KG (Knox "
            "Guard) lock alag cheez hai; KG laga ho to wo server "
            "ka kaam rehta hai ('KG Status' op se halat parho).",
            "INFO")
    return True
