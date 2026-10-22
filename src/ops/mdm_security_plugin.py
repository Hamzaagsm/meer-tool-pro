"""
mdm_security_plugin.py — Transsion MDM pack: security plugin remove.

Mechanism (FENIX-FEATURES-RESEARCH.md §1): plugin TEEN layers par
jeeta hai — (a) firmware system app (documented family naam
"Easybuy Security Plugin"), (b) enrollment STATE jo proinfo /
prodnv / persist jaisi partitions me rehti hai, (c) provisioning
jo factory reset ke baad plugin ko dobara zinda kar deti hai.
Reset sirf userdata saaf karta hai — is liye plugin "wapas aa
jata hai" (user ka apna 2026-10-19 wala case yahi tha).

⚠ Plugin ka EXACT package ID kisi reliable public source me
documented NAHI hai ("saboot nahi mila" — research §1.1). Is liye
detection NAAM se nahi, PEHCHAN se hoti hai: device-admin /
device-owner list + label/keyword heuristics. Koi package
"confirmed plugin" kabhi nahi kehlata.

Flow: detection → MANDATORY auto-backup (ADB snapshot; partition
backup ke liye BROM Proinfo Backup op ki hidayat) → ADB-level
disable/uninstall → verify → natija hamesha in alfaz me:
package-level amal = "BYPASS (reset par wapas aa sakta hai)";
PERMANENT sirf state-layer patch + asal factory-reset survival
check ke baad kehlata hai — wo daawa is op se NAHI hota.
"""

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core import engines
from core.runner import TOOLS_DIR

OP = {
    "id": "mdm_security_plugin",
    "category": "MDM / Transsion",
    "name": "Security Plugin Remove (Transsion)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

# Pehchan ke keyword tokens — ye sirf CANDIDATE dete hain, confirmed nahi.
_HEURISTIC_TOKENS = ("securityplugin", "security_plugin", "easybuy",
                     "plugin", "financ", "mixtel", "mdm", "kist",
                     "installment", "deviceadmin")
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
    """dumpsys device_policy se device-owner/admin package(s) — installed list me hon to."""
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


def _snapshot_backup(ctx, dev, packages, dumpsys_text, targets):
    """MANDATORY auto-backup: detection snapshot model ki library folder
    me. Partition-level backup (proinfo/prodnv/persist) is se nahi hota —
    us ke liye BROM Proinfo Backup op hai. Returns Path ya None."""
    slug = re.sub(r"[^a-z0-9]+", "-",
                  (dev.model or "device").lower()).strip("-") or "device"
    folder = TOOLS_DIR / "mdm-backups" / slug
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"plugin-snapshot-{ts}.txt"
    body = [
        "MEER Tool Pro — Security Plugin detection snapshot",
        f"Waqt: {ts}",
        f"Device: {dev.brand or ''} {dev.model or ''}  serial: {dev.serial or ''}",
        "",
        "Detected targets:",
        *[f"  - {pkg}  [{kind}]" for pkg, kind in targets],
        "",
        "== pm list packages ==",
        *packages,
        "",
        "== dumpsys device_policy ==",
        dumpsys_text or "(khali)",
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

    ctx.progress(15, "Packages aur device-admin list parhe ja rahe hain...")
    packages, packages_raw = _list_packages(adb, dev.serial)
    disabled, _ = _list_packages(adb, dev.serial, ["-d"])
    dumpsys_text = _run_adb(adb, dev.serial, ["dumpsys", "device_policy"])

    if not packages_raw.strip() and not dumpsys_text.strip():
        ctx.log("Device se jawab nahi aya — packages aur device_policy "
                "dono khali aye. Cable check karo aur phone par 'Allow "
                "USB debugging' Allow karke dobara try karo.", "ERROR")
        return False

    # Plugin launcher se chhupa ho sakta hai — disabled list bhi shamil karo
    installed = list(packages)
    for pkg in disabled:
        if pkg not in installed:
            installed.append(pkg)
    installed_lower = {p.lower() for p in installed}
    owners = _owner_packages(dumpsys_text, installed_lower)
    owners_lower = {o.lower() for o in owners}
    if owners:
        for owner in sorted(owners):
            ctx.log(f"Device-owner/admin package (dumpsys se): {owner}", "DATA")
    ctx.log("Note: proinfo ke MDM markers ADB se nahi parhe ja sakte — "
            "un ka scan BROM route (Proinfo Backup op) se hota hai.", "INFO")

    # --- Detection: pehchan, naam nahi (research §1.1/§1.5) ---
    # Tier 1: device-owner/admin — strong andesha. Tier 2: keyword candidate.
    targets = []
    seen = set()

    def _add(pkg, kind):
        key = pkg.lower()
        if key not in seen:
            seen.add(key)
            targets.append((pkg, kind))

    for pkg in installed:
        if pkg.lower() in owners_lower:
            _add(pkg, "device-owner/admin — plugin honay ka strong andesha")
    for pkg in installed:
        low = pkg.lower()
        hits = [tok for tok in _HEURISTIC_TOKENS if tok in low]
        if hits:
            _add(pkg, "candidate — keyword pehchan: %s (confirmed NAHI)"
                 % ", ".join(hits))

    if not targets:
        ctx.log("Koi security plugin jaisa package nahi mila (na "
                "device-owner/admin list me, na keyword pehchan me) — "
                "device is hisaab se saaf hai.", "INFO")
        ctx.progress(95, "Check mukammal — device saaf hai")
        return True

    for pkg, kind in targets:
        ctx.log(f"Target mila [{kind}]: {pkg}", "WARN")

    # --- MANDATORY auto-backup (research §1.5: backup ke baghair patch nahi)
    ctx.progress(25, "Auto-backup (detection snapshot) ban raha hai...")
    snap = _snapshot_backup(ctx, dev, installed, dumpsys_text, targets)
    if snap is None:
        ctx.log("Auto-backup snapshot NAHI ban saka — backup ke baghair "
                "amal aage nahi barhega (ye lazmi qadam hai). tools/ "
                "folder ki write permission check karen.", "ERROR")
        return False
    ctx.log(f"Auto-backup snapshot tayyar: {snap}", "OK")
    ctx.log("Partition-level backup (proinfo/prodnv/persist) ke liye "
            "pehle BROM 'Proinfo Backup' op chalayen — state-layer patch "
            "se pehle wo backup lazmi hai.", "INFO")

    ctx.progress(35, "Plugin par ADB-level amal ho raha hai...")
    for pkg, kind in targets:
        if ctx.is_cancelled():
            return False
        is_owner = pkg.lower() in owners_lower
        ctx.log(f"— {pkg} par amal shuru" + (" (device-owner/admin hai)" if is_owner else ""), "INFO")
        steps = [
            ("disable-user", ["pm", "disable-user", "--user", "0", pkg]),
            ("clear", ["pm", "clear", pkg]),
            ("uninstall", ["pm", "uninstall", "--user", "0", pkg]),
        ]
        for label, args in steps:
            if ctx.is_cancelled():
                return False
            code = ctx.stream([adb, "-s", dev.serial, "shell"] + args,
                              timeout=60)
            ctx.log(f"{pkg} — pm {label} exit code: {code}", "INFO")
            if label == "uninstall" and code != 0 and is_owner:
                ctx.log(f"{pkg} device-owner/admin hai — is surat me "
                        "uninstall fail hona aam hai, disable hi asal "
                        "bandobast hai (neeche verify me asal halat "
                        "ayegi).", "WARN")

    ctx.progress(75, "Natija verify ho raha hai...")
    after_pkgs, _ = _list_packages(adb, dev.serial)
    after_disabled, _ = _list_packages(adb, dev.serial, ["-d"])
    after_lower = {p.lower() for p in after_pkgs}
    after_disabled_lower = {p.lower() for p in after_disabled}

    any_active = False
    for pkg, kind in targets:
        low = pkg.lower()
        if low not in after_lower and low not in after_disabled_lower:
            ctx.log(f"{pkg}: package-level par gaya (verify shuda).", "OK")
        elif low in after_disabled_lower:
            ctx.log(f"{pkg}: disable hai (device-owner ki wajah se "
                    "uninstall nahi hua) — verify shuda disable halat.", "WARN")
        else:
            any_active = True
            ctx.log(f"{pkg}: ab bhi active hai — amal mukammal "
                    "nahi hua.", "ERROR")

    # --- Natija: imaandar label (research §1.5) ---
    ctx.log("NATJA: BYPASS — package-level amal mukammal hua, lekin ye "
            "PERMANENT removal NAHI hai. Plugin teen layers par jeeta "
            "hai: app + enrollment state (proinfo/prodnv/persist) + "
            "reset ke baad ki provisioning. Sirf app hatane se state "
            "reh jati hai — factory reset par plugin WAPAS AA SAKTA "
            "HAI (yehi 2026-10-19 wala case tha: sirf userdata saaf "
            "hua tha, state layer reh gaya tha).", "WARN")
    ctx.log("PERMANENT sirf tab kehlayega jab state-layer patch "
            "(TMETA/BROM route se proinfo/prodnv patch) ke BAAD asal "
            "factory reset karke survival check ho jaye — wo check "
            "kiye baghair koi mustaqil daawa nahi.", "INFO")

    if any_active:
        return False
    ctx.progress(95, "Amal mukammal — natija: BYPASS (upar ka note parho)")
    return True
