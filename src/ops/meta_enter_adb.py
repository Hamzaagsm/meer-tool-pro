"""
meta_enter_adb.py — "Enter META Mode (ADB — bina button)".

Hamza ki pakar (2026-10-24) ke mutabiq META mode me jane ke liye
koi button nahi dabana parta: phone ON + ADB se META me jaya jata
hai. Ye op wahi rasta hai — public tareeqa `adb reboot meta`
(Hovatek/XDA par MediaTek META entry ke liye documented), phir
META port (VID 0x0E8D) ka 60-second poll.

SUCCESS sirf tab hai jab META port asal me nazar ajaye — `adb
reboot meta` ka exit code akela kabhi success nahi. Kuch models
par (naye Dimensity) ye command sirf aik jhalak dikha kar normal
reboot ho jata hai — wahan ye op imaandari se FAIL dega aur
cable-only fallback batayega; nakli success kabhi nahi.

Ye op BROM wale `meta_enter` se alag hai: wo BROM/Preloader se
shuru hota hai, ye phone-ON + ADB se. Dono ka verifier aik hai:
meta_session.find_meta_port().
"""

import shutil
import time
from pathlib import Path

from core import engines, meta_session

OP = {
    "id": "meta_enter_adb",
    "category": "MTK / META",
    "name": "Enter META Mode (ADB — bina button)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

_POLL_SECONDS = 60
_POLL_INTERVAL = 1.5


def run(ctx) -> bool:
    adb = engines.find_platform_tool("adb")
    if not Path(adb).is_file() and shutil.which(adb) is None:
        ctx.log("adb nahi mila — platform-tools app ke tools/ folder me ya "
                "PATH me chahiye.", "ERROR")
        return False
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai. Phone ON karo, USB "
                "debugging ON karo, cable lagao — phir ye op chalao. "
                "(Phone band halat me ye op nahi chalta; us ke liye "
                "band phone sirf cable se lagao phir 'Enter META "
                "Mode (MTKClient)' op chalao.)", "ERROR")
        return False
    ctx.log("Phone ON + ADB se META mode me bheja ja raha hai — "
            "koi button nahi dabana. (`adb reboot meta`)", "INFO")
    ctx.progress(10, "adb reboot meta bheja ja raha hai...")
    code = ctx.stream([adb, "reboot", "meta"], timeout=60)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"adb exit code {code} ke saath band hua — phir bhi "
                "META port ki asal verification hogi; port ajaye to "
                "hi kaam bane ga.", "WARN")
    ctx.progress(30, "META port ka intezaar...")

    pyserial_note = None
    start = time.monotonic()
    while True:
        if ctx.is_cancelled():
            return False
        elapsed = time.monotonic() - start
        if elapsed > _POLL_SECONDS:
            break
        ctx.progress(30 + int(elapsed / _POLL_SECONDS * 60),
                     "META port ka intezaar...")
        try:
            port = meta_session.find_meta_port()
        except meta_session.MetaError as e:
            pyserial_note = str(e)
            port = None
        if port is not None:
            desc = getattr(port, "description", "") or "MediaTek META"
            ctx.progress(95, "META port mil gaya")
            ctx.log(f"META port asal me mil gaya: {port.device} "
                    f"({desc}) — phone META mode me hai, BINA kisi "
                    "button ke. Ab META session wale ops (Read Info "
                    "/ META IMEI Write / FRP Erase) chal sakte hain.",
                    "OK")
            return True
        deadline = time.monotonic() + _POLL_INTERVAL
        while time.monotonic() < deadline:
            if ctx.is_cancelled():
                return False
            time.sleep(0.2)

    if pyserial_note:
        ctx.log(pyserial_note, "ERROR")
    ctx.log("META port 60 second me nazar nahi aya — phone META mode "
            "me nahi gaya. Wajahen check karo: (1) kuch models par "
            "`adb reboot meta` sirf aik jhalak dikha kar normal "
            "reboot ho jata hai (naye Dimensity par ye rasta model "
            "ki had hai, tool ki kharabi nahi), (2) phone par 'Allow "
            "USB debugging' Allow kiya ho, (3) MediaTek VCOM driver "
            "laga ho (driver na ho to META port banta hi nahi). "
            "Fallback: band phone sirf cable se lagao (koi button "
            "nahi), phir 'Enter META Mode (MTKClient)' op chalao.",
            "ERROR")
    return False
