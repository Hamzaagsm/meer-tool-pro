"""
qc_diag_enable.py — Standalone "Enable DIAG" op.

Ab tak DIAG-enable sirf QCN backup/restore ke andar chhupa
helper tha (ops/qc_qcn_backup.diag_enable) — TSM/UAT class ke
tools me ye alag mashhoor op hai (TSM-UAT-RESEARCH §5 G-D),
is liye ab ye apni jagah par hai. Asal kaam wahi helper
karta hai: `setprop sys.usb.config diag,adb` ki koshish —
kamyabi ka asal saboot hamesha Windows Device Manager me
naya DIAG COM port hai (helper wahi kehta hai).

Root: aksar devices par setprop ko root chahiye hota hai —
bina root ke koshish chalegi lekin port nahi ayega; ye hadd
log me saaf likhi jati hai. Kuch brands par DIAG sirf
dialer code se khulta hai — un ke codes bhi log me hain
(Samsung *#0808#, OnePlus/Xiaomi *#*#717717#*#*).
"""

from core import engines
from ops.qc_qcn_backup import diag_enable

OP = {
    "id": "qc_diag_enable",
    "category": "Qualcomm",
    "name": "Enable DIAG Port (ADB)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai — phone on karke "
                "USB debugging ON karo, phir dobara chalayen.",
                "ERROR")
        return False
    if engines.find_platform_tool("adb") is None:
        ctx.log("adb nahi mila (engines/platform-tools check "
                "karo).", "ERROR")
        return False
    ctx.log("Root: setprop wale raste ko aksar ROOT chahiye "
            "hota hai — bina root ke koshish chalegi, lekin "
            "DIAG port tab hi ayega jab ROM ijazat de.", "INFO")
    ctx.log("Dialer-code wale raste (device par khud dial "
            "karen):", "INFO")
    ctx.log("  Samsung: *#0808# → USB Settings me DM+MODEM+ADB "
            "chunen.", "INFO")
    ctx.log("  OnePlus / Xiaomi: *#*#717717#*#* (helper neeche "
            "bhi yahi batayega).", "INFO")
    ctx.log("DIAG tayyar karne ki koshish ho rahi hai (setprop "
            "sys.usb.config = diag,adb)...", "INFO")
    ctx.progress(40, "DIAG enable ho raha hai...")
    ok = diag_enable(ctx)
    if ok:
        ctx.log("DIAG tayyari ki koshish mukammal — asal saboot: "
                "Windows Device Manager → Ports me naya 'DIAG' "
                "COM port nazar ana chahiye. Port na aye to "
                "device root nahi hai ya brand ka apna code "
                "lazmi hai (upar wale codes).", "OK")
        ctx.progress(90, "DIAG tayyari mukammal — port Device "
                          "Manager me check karen")
    return ok
