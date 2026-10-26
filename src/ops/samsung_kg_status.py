"""
samsung_kg_status.py — KG Status Read (Samsung Knox Guard).

KG (Knox Guard) ki halat jahan publicly parhi ja sakti hai
wahan se parh kar dikhata hai: ADB getprop ke knox/kg keys +
knoxguard service, ya Fastboot getvar. Download Mode screen
ki 'KG STATE' line bhi parse hoti hai (parse_download_mode_text)
— teen asal halaten: Prenormal / Checking / Completed
(Research-2 §3.3). Griffin jaise paid tools KG removal/
relock-fixer bechte hain — is op ka kaam sirf PARHNA + imaandar
tashreeh hai; removal ka koi daawa nahi (COMPETITOR-RESEARCH-3
§2.3/§4 P1). Locked halat (Prenormal/Checking/Active) mile to
op asal rasta bhi batata hai: KG remove SERVER ka kaam hai
(Chimera ADB bypass sirf temporary hai, reset par relock).

⚠ RELOCK WARNING har natije ke saath ati hai: KG state
Samsung ke server par hoti hai — koi bhi bypass ke baad
device dobara lock ho sakta hai; paid tools is ke liye alag
'KG Relock Fixer' bechte hain, jo is baat ka saboot hai ke
relock asal khatra hai.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from core import engines

OP = {
    "id": "samsung_kg_status",
    "category": "Samsung",
    "name": "KG Status (Knox Guard) — Read Only",
    "engine": "adb",
    "modes": ("ADB", "FASTBOOT"),
    "server_required": False,
}

# Download-Mode par dikhne wale maroof KG states aur un ki
# saada tashreeh — jo token in me na ho, us ki tashreeh NAHI
# banayi jati (raw value hi dikhta hai).
# (Research-2 §3.3: Download Mode screen par KG STATE ki teen
# asal halaten — Prenormal / Checking / Completed.)
_KNOWN_STATES = {
    "locked": "KG LOCKED hai — device Knox Guard se band hai.",
    "active": "KG ACTIVE hai — enrollment zinda hai, lock lag sakta hai.",
    "checking": "KG CHECKING — device server se halat check kar raha hai.",
    "prenormal": "KG PRENORMAL — device abhi Knox Guard server se "
                 "mukammal 'Completed' nahi hua; OEM unlock band "
                 "rehta hai jab tak halat Completed na ho. Naye ya "
                 "finance (qist) wale phone aam tor par isi halat "
                 "me hote hain.",
    "normal": "KG NORMAL — koi KG lock nahi laga.",
    "prenotification": "KG PRENOTIFICATION — lock se pehle ki warning halat.",
    "completed": "KG COMPLETED — provisioning mukammal ho chuki hai.",
}

# Halaten jin me KG lock ya enrollment zinda samjhi jaye — in
# par sirf status nahi, asal rasta bhi batana lazmi hai.
_LOCKED_TOKENS = ("locked", "active", "prenormal", "checking",
                  "prenotification")

_LOCKED_ROUTE = (
    "Asal rasta (KG locked/active/prenormal ho to): KG remove "
    "SERVER ka kaam hai — KG ki halat Samsung ke server par hoti "
    "hai, phone ke partition erase karne se nahi mit-ti. Paid "
    "tools ka ADB-based KG BYPASS (Chimera, Mar 2026) sirf "
    "temporary hai — factory reset + internet par dobara lock ho "
    "jata hai (is liye wo REMOVE nahi, BYPASS hai). Permanent "
    "remove ke liye finance company / Samsung server se release "
    "chahiye. MEER KG remove/bypass NAHI banata — sirf halat "
    "parhta hai. KG 26.01 'Hardened Security' wale financed "
    "devices par aur sakht hai.")


def parse_download_mode_text(text):
    """Download Mode screen ka text → {'state': token|None,
    'lines': [KG/RMM wali lines]}. (Pure — testable.)

    Screen par aam tor par aisi lines hoti hain:
        KG STATE : PRENORMAL
        RMM STATE : PRENORMAL
        KG STATUS: CHECKING
    Sirf maroof tokens (prenormal/checking/completed/locked/
    active/normal) pehchane jate hain — kuch aur mile to raw
    line hi saboot hai, andaza nahi.
    """
    lines = []
    state = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        low = line.lower()
        if "kg" in low or "rmm" in low:
            if line and line not in lines:
                lines.append(line)
            if state is None:
                for token in _KNOWN_STATES:
                    # "kg state : prenormal" jaisi line me token
                    # dhoondho; "prenotification" ko "prenormal"
                    # se pehle na pakro — lamba token pehle.
                    if token in low:
                        state = token
                        break
    # "prenotification" me "prenormal" nahi ata, lekin safety:
    # agar line me dono hon to lamba token jeete.
    if state is None:
        return {"state": None, "lines": lines}
    return {"state": state, "lines": lines}


def locked_route_guidance(state):
    """Locked-ish state ho to asal rasta, warna None. (Pure.)"""
    if state and str(state).lower() in _LOCKED_TOKENS:
        return _LOCKED_ROUTE
    return None

_RELOCK_WARNING = (
    "⚠ RELOCK WARNING: KG ki asal halat Samsung ke SERVER par "
    "hoti hai, phone ke andar nahi. Koi bhi bypass lag jaye to "
    "bhi device dobara lock ho sakta hai — bare paid tools is "
    "ke liye alag 'KG Relock Fixer' bechte hain. Ye op sirf "
    "halat PARHTA hai; KG removal ka daawa is tool me NAHI hai.")


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


def _resolve_tool(ctx, name):
    path = engines.find_platform_tool(name)
    if Path(path).is_file() or shutil.which(path):
        return path
    ctx.log(f"{name} nahi mila — platform-tools app ke "
            "engines/platform-tools/ ya tools/platform-tools/ "
            "folder me, ya PATH me chahiye.", "ERROR")
    return None


def _kg_lines(text):
    hits = []
    for raw in (text or "").splitlines():
        low = raw.lower()
        if "knox" in low or "kgstate" in low or "knoxguard" in low \
                or "[kg" in low or " kg:" in low or "kg_" in low:
            line = raw.strip()
            if line and line not in hits:
                hits.append(line)
    return hits


def _interpret(lines):
    """Raw lines se pehchana hua state token — sirf maroof
    tokens par tashreeh, warna imaandar 'raw hi saboot hai'."""
    notes = []
    blob = " ".join(lines).lower()
    for token, meaning in _KNOWN_STATES.items():
        if token in blob:
            notes.append(meaning)
            break
    return notes


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device ADB ya Fastboot mode me nahi hai. KG status "
                "parhne ke liye phone on karke ADB mode me lagao "
                "(ya Fastboot mode me).", "ERROR")
        return False

    lines = []
    if dev.mode == "ADB":
        adb = _resolve_tool(ctx, "adb")
        if adb is None:
            return False
        ctx.progress(30, "Properties parhi ja rahi hain...")
        props = _run_quiet([adb, "-s", dev.serial, "shell", "getprop"])
        lines += _kg_lines(props)
        ctx.progress(60, "KnoxGuard service check ho rahi hai...")
        services = _run_quiet([adb, "-s", dev.serial, "shell",
                               "service", "list"])
        for raw in services.splitlines():
            if "knox" in raw.lower():
                line = "service: " + raw.strip()
                if line not in lines:
                    lines.append(line)
        kg_dump = _run_quiet([adb, "-s", dev.serial, "shell",
                              "dumpsys", "knoxguard"])
        if kg_dump.strip() and "not found" not in kg_dump.lower() \
                and "no such" not in kg_dump.lower():
            for line in _kg_lines(kg_dump)[:5]:
                if line not in lines:
                    lines.append(line)
    else:  # FASTBOOT
        fastboot = _resolve_tool(ctx, "fastboot")
        if fastboot is None:
            return False
        ctx.progress(40, "Fastboot variables parhe ja rahe hain...")
        getvar = _run_quiet([fastboot, "getvar", "all"], timeout=30)
        lines += _kg_lines(getvar)

    if not lines:
        ctx.log("Is mode se koi KG/Knox property publicly readable "
                "nahi mili — is ka matlab ye NAHI ke KG nahi hai; "
                "aksar firmwares ye values chhupa deti hain.", "WARN")
        ctx.log("Download Mode ki screen par bhi KG halat dikhti "
                "hai — phone Download Mode me lao (band karo, Vol "
                "Down + Vol Up dabaye hue cable lagao; One UI 8.5 "
                "par pehle Maintenance Mode ON karna parta hai) aur "
                "screen par 'KG STATE' wali line parho: PRENORMAL "
                "(OEM unlock band, server se Completed ka intezar), "
                "CHECKING (server se halat check ho rahi hai), ya "
                "COMPLETED (provisioning mukammal).", "INFO")
        ctx.log(_RELOCK_WARNING, "WARN")
        return False

    ctx.log("KG / Knox ki publicly readable maloomat:", "INFO")
    for line in lines:
        ctx.log(f"  {line}", "DATA")
    notes = _interpret(lines)
    for note in notes:
        ctx.log(f"Tashreeh: {note}", "OK")
    if not notes:
        ctx.log("Upar ki raw values hi saboot hain — in tokens ki "
                "koi maroof tashreeh public documented nahi, is "
                "liye andaza nahi lagaya jayega.", "INFO")
    # Locked-ish halat ho to sirf status nahi — asal rasta bhi.
    blob = " ".join(lines).lower()
    state = None
    for token in _KNOWN_STATES:
        if token in blob:
            state = token
            break
    guidance = locked_route_guidance(state)
    if guidance:
        ctx.log(guidance, "WARN")
    elif state in ("completed", "normal"):
        ctx.log("KG lock nahi dikh raha — is halat me FRP / "
                "bootloader-unlock ke free raste (jahan applicable "
                "hon) band nahi hote.", "OK")
    ctx.log(_RELOCK_WARNING, "WARN")
    ctx.progress(95, "KG status parha gaya (sirf read — koi tabdeeli nahi)")
    return True
