"""
mtk_sn_writer.py — SN Write Tool / Modem META launcher + guide.

**Ye op khud kuch NAHI likhta** — ye MediaTek ke OFFICIAL tools
(SN Write Tool / Modem META) ko kholta hai aur un ke asal flow ki
mukammal hidayat deta hai. Asal IMEI likhne ka wo rasta jab NV
backup maujood na ho (REPAIR-METHODS-RESEARCH §3.1b):

    phone META mode me → Load DB (model ke stock firmware se
    AP_DB + MD1_DB) → IMEI Download → DABBE/STICKER wala asal
    IMEI darj → Write.

Hamza ki warning (core/imei_gate.py wali) guide ke andar shuru
me hi chhapti hai — official tool khulne se pehle hi technician
ko wazeh ho ke yahan sirf device ka apna asal number jayega.

Official tools is package me bundle NAHI hain (MediaTek ki apni
distribution hai) — user apni copy tools/snwriter/ me rakhta
hai; exe na mile to guided FAIL + poori guide phir bhi log me
ati hai taake tareeqa mehfooz rahe.
"""

import subprocess

from core.imei_gate import IMEI_WARNING
from core.runner import TOOLS_DIR

OP = {
    "id": "mtk_sn_writer",
    "category": "MTK",
    "name": "SN Writer / Modem META (Launcher + Guide) — Original IMEI",
    "engine": "launcher",
    "modes": (),
    "server_required": False,
}

_EXE_HINTS = ("snwriter", "sn_write", "snwrite", "modemmeta",
              "modem_meta", "maui", "meta")

_GUIDE = [
    "=== SN WRITER / MODEM META — ASAL IMEI RESTORE KA FLOW ===",
    "1) Pehle isi model ka STOCK firmware PC par rakho — us ke "
    "andar se do database files chahiye hongi: AP_DB aur MD1_DB "
    "(firmware ke andar aksar 'APDB_...' / 'MD1_DB...' naamon se "
    "hoti hain). DB model se match na kare to write fail hoga.",
    "2) Neeche khulne wale tool (SN Writer ya Modem META) me apna "
    "target select karo: SN Writer me 'IMEI Download' / Modem META "
    "me IMEI wala section.",
    "3) 'Load DB' se pehle AP_DB, phir MD1_DB load karo (jo tool "
    "jitni mange).",
    "4) Phone band karke META mode me lagao (tool khud tareeqa "
    "batata hai — aam tor par battery/cable wali state jo tool ki "
    "hidayat me likhi ho).",
    "5) IMEI wale khane me **SIRF dabbe / sticker wala asal IMEI** "
    "likho. Purane Maui META rawaj ke mutabiq tool check digit "
    "khud sambhalta hai — number hamesha device ka apna ho.",
    "6) Write/Start dabao, SUCCESS ka intezar karo, phir phone on "
    "karke *#06# se dabbe wale number se milao.",
    "Note: MEER Tool Pro khud is flow me koi number NAHI likhta — "
    "ye sirf official tool ka launcher + guide hai. NV backup "
    "maujood ho to pehla rasta hamesha 'NV Restore' hai (wo is "
    "se zyada saaf hai).",
]


def _find_tool_exe():
    folder = TOOLS_DIR / "snwriter"
    if not folder.is_dir():
        return None
    exes = sorted(p for p in folder.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".exe")
    if not exes:
        return None
    for exe in exes:
        if any(h in exe.name.lower() for h in _EXE_HINTS):
            return exe
    return exes[0]


def _find_db_files():
    """Stock firmware folders me AP_DB / MD1_DB ki talaash (guide ke liye)."""
    found = {"ap": [], "md": []}
    for base in (TOOLS_DIR / "firmware", TOOLS_DIR / "snwriter"):
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            n = p.name.upper()
            if n.startswith("APDB") or n.startswith("AP_DB"):
                found["ap"].append(p)
            elif n.startswith("MD1_DB") or n.startswith("MD1DB"):
                found["md"].append(p)
    return found


def run(ctx) -> bool:
    # Warning pehle — ye guide IMEI write ke official raste ki
    # hai, is liye Hamza ki shart yahan lafz-ba-lafz chhapegi.
    ctx.log("=" * 72, "WARN")
    ctx.log(IMEI_WARNING, "WARN")
    ctx.log("=" * 72, "WARN")
    for line in _GUIDE:
        ctx.log(line, "INFO")

    dbs = _find_db_files()
    for p in dbs["ap"][:3]:
        ctx.log(f"AP_DB mili: {p}", "DATA")
    for p in dbs["md"][:3]:
        ctx.log(f"MD1_DB mili: {p}", "DATA")
    if not dbs["ap"] and not dbs["md"]:
        ctx.log("AP_DB / MD1_DB abhi tools/firmware/ me nahi milin — "
                "model ka stock firmware wahan rakho ge to agli dafa "
                "ye khud nazar ayengi (tool me wahi select karni "
                "hain).", "WARN")

    exe = _find_tool_exe()
    if exe is None:
        ctx.log("SN Write Tool / Modem META ki copy tools/snwriter/ "
                "me nahi mili — is liye tool khola nahi ja saka. Ye "
                "MediaTek ke official free tools hain lekin is "
                "package me bundle NAHI kiye gaye; apni copy ke exe "
                "wahan rakho, phir ye op wahi se kholega. Guide upar "
                "mehfooz hai.", "ERROR")
        return False
    ctx.progress(50, f"Official tool khola ja raha hai: {exe.name}")
    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"Tool khul nahi saka ({exe.name}): {exc}", "ERROR")
        return False
    ctx.progress(90, "Tool khul gaya")
    ctx.log(f"{exe.name} khul gaya hai — upar wale flow se sirf "
            "asal (dabbe wala) IMEI restore karo.", "OK")
    return True
