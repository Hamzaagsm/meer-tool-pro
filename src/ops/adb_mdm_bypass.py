"""
adb_mdm_bypass.py — ADB MDM Bypass (DNS + Device Owner).

Oumse-class tools ka teesra, ADB wala rasta (OUMSE-TEARDOWN §4):
private DNS se MDM/plugin ke servers block + TestDPC ko
device-owner bana kar plugin ko be-ikhtiyar karna. 5-step
guided pipeline hai: jo qadam phone par technician ke haath ka
hai, wo log me number ke saath likha jata hai; jo ADB se ho
sakta hai, wo op khud karke device se VERIFY karta hai.

Steps:
  1. Device + Android version check (ADB).
  2. Accounts ki halat: device par koi account ho to
     set-device-owner hota hi nahi — op wahan ruk kar phone-side
     hidayat deta hai (accounts hatao ya factory reset karo).
  3. Private DNS: phone par jo hostname darj karna hai wo
     tools/adb-bypass.json ki "dns_hostname" se ata hai —
     technician APNA hostname bharta hai. Kisi teesri party ki
     DNS service ka hostname code me NAHI likha gaya. Phone par
     asal me set hai ya nahi, wo settings readback se check
     hota hai.
  4. TestDPC: installed ho to
     `dpm set-device-owner com.afwsamples.testdpc/.DeviceAdminReceiver`
     (component Google ke official TestDPC README se verify
     shuda: package com.afwsamples.testdpc, receiver
     com.afwsamples.testdpc.DeviceAdminReceiver). Installed na
     ho to op Play Store / official GitHub releases ki rehnumai
     deta hai — koi APK bundle NAHI hai.
  5. Verify: dumpsys device_policy se device-owner ki halat
     parh kar hi natija banta hai.

IMAANDARI:
  - SUCCESS sirf dumpsys verify par. dpm ki output chal jana
    kaafi nahi.
  - Ye DNS + Device Owner wala bandobast hai — plugin ki
    state-layer (proinfo/prodnv) is se NAHI badalti. Factory
    reset ke baad ye setup dobara karna hoga. PERMANENT wala
    daawa is op ka nahi hai — us ke liye MDM Pack ke state-layer
    ops hain.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.runner import TOOLS_DIR
from ops.adb_remove_ads import guard, sh

OP = {
    "id": "adb_mdm_bypass",
    "category": "ADB / Fastboot",
    "name": "ADB MDM Bypass (DNS + Device Owner)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

CONFIG_FILE = TOOLS_DIR / "adb-bypass.json"
TESTDPC_PACKAGE = "com.afwsamples.testdpc"
TESTDPC_COMPONENT = "com.afwsamples.testdpc/.DeviceAdminReceiver"
TESTDPC_COMPONENT_FULL = ("com.afwsamples.testdpc/"
                          "com.afwsamples.testdpc.DeviceAdminReceiver")

_PKG_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+", re.IGNORECASE)


def load_bypass_config(path=CONFIG_FILE):
    """tools/adb-bypass.json parho — kabhi raise nahi.
    Return: {"dns_hostname": str} (khali bhi ho sakti hai)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {"dns_hostname":
                    str(data.get("dns_hostname") or "").strip()}
    except Exception:  # noqa: BLE001
        pass
    return {"dns_hostname": ""}


def count_accounts(dumpsys_account_text):
    """dumpsys account ki output se accounts ki tadaad (pure).

    'Accounts: N' wali header line ko tarjeeh; warna 'Account {'
    entries gin lo. Jawab samajh na aye to None.
    """
    text = dumpsys_account_text or ""
    if not text.strip():
        return None
    m = re.search(r"Accounts:\s*(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    entries = text.count("Account {")
    if entries:
        return entries
    if "no accounts" in text.lower():
        return 0
    return None


def parse_device_owner(dumpsys_text):
    """dumpsys device_policy se device-owner ka package (pure).

    Milti-julti shaklen: 'Device Owner:' section me
    'package=com.x.y' line, ya seedhi line me package=...
    Na mile to None.
    """
    text = dumpsys_text or ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "device owner" in line.lower():
            m = re.search(r"package=([A-Za-z0-9_.]+)", line)
            if m:
                return m.group(1)
            for follow in lines[i + 1:i + 5]:
                m = re.search(r"package=([A-Za-z0-9_.]+)", follow)
                if m:
                    return m.group(1)
                m = re.search(
                    r"ComponentInfo\{([A-Za-z0-9_.]+)/", follow)
                if m:
                    return m.group(1)
    return None


def dns_satisfied(mode, specifier):
    """Private DNS asal me hostname mode par set hai? (pure)"""
    return (mode or "").strip().lower() == "hostname" and \
        bool((specifier or "").strip())


def explain_dpm_failure(output):
    """dpm set-device-owner ki aam nakamiyon ki Urdu wazahat (pure)."""
    low = (output or "").lower()
    if "device owner is already set" in low or \
            "already has a device owner" in low:
        return ("Device par PEHLE se aik device owner set hai — "
                "pehle use hataye baghair naya owner nahi banta. "
                "Factory reset ke baad saaf halat me ye op chalao.")
    if "account" in low:
        return ("DPM jawab: device par account(s) maujood hain — "
                "set-device-owner accounts ke saath nahi hota. "
                "Saare accounts hatao ya factory reset karo, phir "
                "dobara try karo.")
    if "provisioned" in low:
        return ("DPM jawab: device 'provisioned' halat me hai — ye "
                "amal setup ke foran baad / reset ke baad wali "
                "saaf halat me hota hai. Factory reset karke, "
                "setup me account jode baghair, ye op chalao.")
    if "not allowed" in low or "securityexception" in low:
        return ("DPM ne ijazat nahi di (ROM ki pabandi ho sakti "
                "hai) — is ROM par ye rasta band ho sakta hai; "
                "state-layer wale MDM ops dekho.")
    return ""


def _getprop(adb, serial, key):
    out, _ = sh(adb, serial, ["getprop", key])
    return (out or "").strip()


def _settings_get(adb, serial, key):
    out, _ = sh(adb, serial, ["settings", "get", "global", key])
    return (out or "").strip()


def run(ctx) -> bool:
    adb, serial = guard(ctx)
    if adb is None:
        return False
    total_steps = 5

    # --- STEP 1: device + version ------------------------------------
    ctx.log(f"STEP 1/{total_steps}: Device aur Android version "
            "check ho raha hai...", "INFO")
    brand = _getprop(adb, serial, "ro.product.brand")
    model = _getprop(adb, serial, "ro.product.model")
    release = _getprop(adb, serial, "ro.build.version.release")
    sdk = _getprop(adb, serial, "ro.build.version.sdk")
    if not release and not model:
        ctx.log("Device se getprop ka jawab nahi aya — cable / "
                "USB debugging ki ijazat check karo.", "ERROR")
        return False
    ctx.log(f"Device: {brand} {model} — Android {release} "
            f"(SDK {sdk})", "DATA")
    ctx.progress(15, "Step 1 mukammal — accounts check ho rahe hain...")

    # --- STEP 2: accounts + maujooda owner ---------------------------
    ctx.log(f"STEP 2/{total_steps}: Accounts aur maujooda "
            "device-owner ki halat...", "INFO")
    acct_text, _ = sh(adb, serial, ["dumpsys", "account"])
    n_accounts = count_accounts(acct_text)
    if n_accounts is None:
        ctx.log("Accounts ki halat dumpsys se confirm nahi ho saki "
                "— aage barhna khatarnak hai (owner set fail ho "
                "sakta hai). Cable dobara laga kar try karo.",
                "ERROR")
        return False
    ctx.log(f"Device par accounts ki tadaad: {n_accounts}", "DATA")
    policy_text, _ = sh(adb, serial, ["dumpsys", "device_policy"])
    existing_owner = parse_device_owner(policy_text)
    if existing_owner:
        if existing_owner.lower() == TESTDPC_PACKAGE:
            ctx.log("TestDPC pehle se hi device owner hai — ye "
                    "chain pehle se mukammal hai. Natija STEP 5 "
                    "wali verify se confirm ho gaya.", "OK")
            ctx.progress(95, "TestDPC pehle se device owner hai")
            return True
        ctx.log(f"Device par pehle se aik device owner set hai: "
                f"{existing_owner} — doosra owner nahi ban sakta. "
                "GUIDE: pehle us owner ko usi ki app se hatao ya "
                "factory reset karke saaf halat me ye op chalao.",
                "ERROR")
        return False
    if n_accounts > 0:
        ctx.log("Device par account(s) maujood hain — is halat me "
                "Android set-device-owner ki ijazat NAHI deta.",
                "ERROR")
        ctx.log("PHONE PAR YE QADAM KARO (technician):", "WARN")
        ctx.log("  1) Settings → Passwords & accounts (ya Users & "
                "accounts) me ja kar HAR account Remove karo "
                "(Google / Transsion / doosre sab), YA", "WARN")
        ctx.log("  2) Factory reset karo (Settings → System → "
                "Reset) aur setup ke doran KOI account mat joro.",
                "WARN")
        ctx.log("  3) USB debugging on karke ye op DOBARA chalao — "
                "baqi steps wahin se aage barhen ge. (Ye rukna "
                "nakami nahi, is tareeqe ki lazmi tayyari hai.)",
                "WARN")
        return False
    ctx.log("Accounts saaf hain, koi device owner pehle se set "
            "nahi — aage barh sakte hain.", "OK")
    ctx.progress(32, "Step 2 mukammal — Private DNS step...")

    # --- STEP 3: Private DNS (phone-side qadam) -----------------------
    ctx.log(f"STEP 3/{total_steps}: Private DNS — MDM ke servers "
            "block karne wala qadam.", "INFO")
    cfg = load_bypass_config()
    hostname = cfg["dns_hostname"]
    cur_mode = _settings_get(adb, serial, "private_dns_mode")
    cur_spec = _settings_get(adb, serial, "private_dns_specifier")
    if dns_satisfied(cur_mode, cur_spec):
        ctx.log(f"Phone par Private DNS pehle se set hai: "
                f"{cur_spec} (hostname mode) — ye qadam mukammal "
                "hai.", "OK")
    else:
        ctx.log(f"Phone ki maujooda Private DNS halat: mode="
                f"{cur_mode or '(khali)'}, hostname="
                f"{cur_spec or '(khali)'}", "DATA")
        if not hostname:
            ctx.log("tools/adb-bypass.json me 'dns_hostname' KHALI "
                    "hai — is op me kisi teesri party ki DNS "
                    "service ka hostname pehle se NAHI likha gaya.",
                    "ERROR")
            ctx.log(f"GUIDE: jo private-DNS hostname tum istemal "
                    f"karte ho (jo MDM/plugin ke servers block "
                    f"kare), wo is file me 'dns_hostname' ke aage "
                    f"likho: {CONFIG_FILE} — phir phone par wo "
                    f"hostname set karke (neeche wala qadam) ye op "
                    f"dobara chalao.", "WARN")
            return False
        ctx.log("PHONE PAR YE QADAM KARO (technician):", "WARN")
        ctx.log("  Setup ke doran ya Settings → Network & internet "
                "→ Private DNS → 'Private DNS provider hostname' "
                f"me YE hostname darj karo: {hostname}", "WARN")
        ctx.log("  Hostname set ho jaye to ye op DOBARA chalao — "
                "readback se verify karke aage barhen ge. (Ye "
                "qadam phone ke haath ka hai; ADB se global "
                "setting likhna is method ka hissa nahi — asal "
                "setup-wizard wali halat chahiye hoti hai.)",
                "WARN")
        return False
    ctx.progress(50, "Step 3 mukammal — TestDPC check ho raha hai...")

    # --- STEP 4: TestDPC + set-device-owner ---------------------------
    ctx.log(f"STEP 4/{total_steps}: TestDPC aur device-owner set "
            "karna.", "INFO")
    pkgs_text, _ = sh(adb, serial, ["pm", "list", "packages",
                                    TESTDPC_PACKAGE])
    installed = TESTDPC_PACKAGE in (pkgs_text or "")
    if not installed:
        ctx.log("TestDPC device par installed NAHI hai.", "ERROR")
        ctx.log("GUIDE: TestDPC sirf OFFICIAL jagah se lo — "
                "Play Store par 'Test DPC' (com.afwsamples.testdpc) "
                "ya Google ke official GitHub releases: "
                "https://github.com/googlesamples/android-testdpc/"
                "releases — install karke ye op dobara chalao. "
                "Kisi aur jagah ki APK is tool se bundle NAHI ki "
                "gayi.", "WARN")
        return False
    ctx.log("TestDPC installed hai. Ab device owner set ho raha "
            f"hai: dpm set-device-owner {TESTDPC_COMPONENT}", "INFO")
    out, code = sh(adb, serial,
                   ["dpm", "set-device-owner", TESTDPC_COMPONENT],
                   timeout=90)
    dpm_text = (out or "").strip() or "(khali)"
    ctx.log(f"dpm jawab (exit {code}): {dpm_text}", "DATA")
    ctx.progress(75, "Step 4 mukammal — verify ho raha hai...")

    # --- STEP 5: Verify (dumpsys device_policy) -----------------------
    ctx.log(f"STEP 5/{total_steps}: Verify — dumpsys "
            "device_policy se asal halat...", "INFO")
    policy_after, _ = sh(adb, serial, ["dumpsys", "device_policy"])
    owner_after = parse_device_owner(policy_after)
    if owner_after and owner_after.lower() == TESTDPC_PACKAGE:
        ctx.log("VERIFY HO GAYA: TestDPC ab is device ka DEVICE "
                "OWNER hai (dumpsys device_policy se confirm).",
                "OK")
        ctx.log("NATJA: ADB MDM Bypass chain mukammal — Private "
                "DNS se MDM servers block + TestDPC device owner "
                "ban gaya, plugin be-ikhtiyar halat me hai. "
                "Note: ye state-layer (proinfo/prodnv) wala "
                "PERMANENT patch NAHI hai — factory reset ke baad "
                "ye setup dobara karna hoga; mustaqil natije ke "
                "liye MDM Pack ke state-layer ops istemal karo.",
                "INFO")
        ctx.progress(95, "ADB MDM Bypass mukammal — verify shuda")
        return True
    ctx.log("Verify FAIL: dumpsys device_policy me TestDPC "
            "device owner ke tor par NAHI aya.", "ERROR")
    hint = explain_dpm_failure(out)
    if hint:
        ctx.log(f"Wazahat: {hint}", "WARN")
    else:
        ctx.log("Upar wale dpm jawab me asal wajah hai — aam "
                "wajahen: device provisioned halat me tha, ya "
                "koi account darmiyan me jur gaya tha. Factory "
                "reset ke baad, account jode baghair, poori "
                "chain dobara chalao.", "WARN")
    return False
