"""
reset_honesty.py — Reset ops ke liye imaandari (honesty) helper.

Har reset op (factory reset / FRP reset / userdata wipe) asal me
USERDATA-level amal hai: apps, accounts aur user data jata hai,
lekin MDM / finance locks (PayJoy, Knox Guard, Google DLC,
Easybuy/Transsion security plugin waghera) ki SERVER / state-layer
halat is se NAHI badalti. Ye helper do kaam karta hai:

  - pre_reset_honesty(ctx): reset se PEHLE — device ADB mode me
    ho to package list parh kar core/finance_locks.py ke
    classifier se finance/MDM locks ki pehchan karta hai, aur
    hamesha (ADB ho ya na ho) USERDATA-level wali label lines
    log karta hai.
  - result_label(ctx, info): reset ke BAAD natija label lagata
    hai — finance lock mila ho to saaf WARN ke wo lock baqi
    reh sakta hai.

Usool: ye module KABHI raise nahi karta — helper khud fail ho
jaye to bhi asal reset op rukna nahi chahiye; error par WARN
log karke khali/partial natija wapas hota hai.

Classifier API (core/finance_locks.py):
    classify_finance_locks(packages, dumpsys_text="")
        -> [{lock_id, name, package, kind, is_device_owner,
             verdict}, ...]
"""

import subprocess
import sys

from core import engines, finance_locks

# Hamesha lagne wali label line (pre_reset_honesty ki shart c).
LABEL_LINE = (
    "Reset-honesty: ye operation USERDATA-level reset hai — "
    "apps/accounts/data jayenge, lekin MDM/finance (PayJoy/KG/DLC) "
    "ki server state is se nahi badalti.")


def _capture_packages(adb, serial):
    """`adb shell pm list packages` ki output se package naam.

    Subprocess capture ka pattern ops/fastboot_frp.py ke
    getvar_all jaisa hai (Windows par CREATE_NO_WINDOW, timeout,
    har error par khali list — kabhi raise nahi).
    """
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            [adb, "-s", serial, "shell", "pm", "list", "packages"],
            capture_output=True, text=True, timeout=25, **kwargs)
        text = (out.stdout or "") + "\n" + (out.stderr or "")
    except Exception:  # noqa: BLE001
        return []
    pkgs = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            line = line[len("package:"):].strip()
        if line:
            pkgs.append(line)
    return pkgs


def pre_reset_honesty(ctx) -> dict:
    """Reset se pehle finance-lock check + honesty labels.

    Wapas: {"finance_found": [lock names], "checked": bool}
      - checked=True sirf tab jab ADB mode me package list asal
        me parhi gayi aur classify hui.
      - ADB na ho (ya list na aye) to checked=False — sirf
        label lines lagti hain.
    Kabhi raise nahi karta.
    """
    info = {"finance_found": [], "checked": False}
    try:
        # (c) Hamesha wali label lines — ADB ho ya na ho.
        ctx.log(LABEL_LINE, "INFO")
        ctx.log(
            "Reset-honesty: reset ke baad MDM/finance lock wapas "
            "aa sakta hai agar wo server/state-layer par hai — "
            "reset ko MDM/finance removal mat samjho.", "WARN")

        dev = getattr(ctx, "device", None)
        if dev is None or getattr(dev, "mode", None) != "ADB":
            # (b) ADB nahi — live check mumkin nahi.
            ctx.log(
                "Reset-honesty: device ADB mode me nahi hai, is "
                "liye finance-lock ki live pehchan nahi ho saki "
                "(checked=False). Shak ho to pehle phone ADB mode "
                "me laga kar Finance Check op chalao.", "WARN")
            return info

        # (a) ADB hai — package list capture + classify.
        adb = engines.find_platform_tool("adb")
        packages = _capture_packages(adb, getattr(dev, "serial", "") or "")
        if not packages:
            ctx.log(
                "Reset-honesty: ADB se package list nahi ayi — "
                "finance-lock check nahi ho saka (checked=False). "
                "Cable / 'Allow USB debugging' check karo.", "WARN")
            return info

        findings = finance_locks.classify_finance_locks(packages)
        info["checked"] = True
        if not findings:
            ctx.log(
                "Reset-honesty: package list check hui — koi "
                "mashhoor finance/MDM lock nahi mila (PayJoy / "
                "Easybuy / NuovoPay / d.light / Knox Guard / "
                "Google DLC).", "INFO")
            return info

        info["finance_found"] = [f["name"] for f in findings]
        for f in findings:
            ctx.log(
                f"Reset-honesty: finance/MDM lock MILA — "
                f"{f['name']} (package: {f['package']}).", "WARN")
        ctx.log(
            "Reset-honesty: ye lock RESET se NAHI jata — "
            "server/state-layer wala lock hai; reset ke baad "
            "phone phir lock ho sakta hai. Pehle MDM Pack / "
            "Finance Check op dekho.", "WARN")
        return info
    except Exception as exc:  # noqa: BLE001 — helper kabhi raise nahi
        try:
            ctx.log(
                f"Reset-honesty: check ke dauran error aya ({exc}) — "
                "reset-honesty check mukammal nahi ho saka.", "WARN")
        except Exception:  # noqa: BLE001
            pass
        return info


def result_label(ctx, info):
    """Reset ke baad ka natija label.

    Hamesha: "Natija label: USERDATA-LEVEL RESET".
    info["finance_found"] khali na ho to extra WARN ke wo lock
    baqi reh sakta hai. Kabhi raise nahi karta.
    """
    try:
        ctx.log("Natija label: USERDATA-LEVEL RESET", "INFO")
        found = []
        if isinstance(info, dict):
            found = info.get("finance_found") or []
        if found:
            names = ", ".join(str(n) for n in found)
            ctx.log(
                f"Natija label: finance/MDM lock ({names}) ki "
                "server/state-layer halat is reset se NAHI badli "
                "— lock baqi reh sakta hai aur reset ke baad "
                "phone phir lock ho sakta hai.", "WARN")
    except Exception:  # noqa: BLE001 — helper kabhi raise nahi
        pass
