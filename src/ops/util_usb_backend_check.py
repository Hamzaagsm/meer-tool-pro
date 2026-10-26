"""
util_usb_backend_check.py — USB Backend Check (libusb).

PC ke USB stack ki jaanch — BINA phone ke. MTKClient ke "USB
enumeration error: Operation not supported or unimplemented on this
platform" (Windows 11 25H2, build 26200) ki asal wajah yahi check
pakarta hai, poora FRP op chalaye baghair: kya is PC par libusb1
ya libusb0 backend USB devices ki list bana sakta hai?

Kaam: engines/usb_backend_check.py ko engines/python se chalao aur
us ki NATEEJA line par faisla karo.
  - OK (exit 0): kam az kam aik backend list kar raha hai — USB
    rasta theek hai; FRP nakami ki wajah phir mode/driver/phone hai.
  - FAIL (exit 1): koi backend list nahi kar raha — USB stack is
    PC par toota hai (libusb DLL / filter driver / Windows USB
    backend). Serial (VCOM) rasta phir bhi chal sakta hai — FRP op
    COM port se chalao; USB ke liye libusb filter / Zadig dobara
    lagao (UTILITY > Install Drivers).

Imaandari:
  - Ye op sirf PC ki jaanch hai — phone lagane ki zaroorat nahi,
    aur is ka OK hona FRP ki kamyabi ki zamanat NAHI (wo alag
    cheez hai: mode, DA/auth, chipset).
  - FAIL par bhi serial rasta band nahi hota — op yehi likhta hai.
"""

from core import engines
from core.runner import ENGINES_DIR

OP = {
    "id": "util_usb_backend_check",
    "category": "Utility",
    "name": "USB Backend Check (libusb)",
    "engine": "usb",
    "modes": (),
    "server_required": False,
}

_PROBE = "usb_backend_check.py"


def run(ctx) -> bool:
    probe = ENGINES_DIR / _PROBE
    if not probe.is_file():
        ctx.log("USB Backend Check script nahi mila: %s" % probe, "ERROR")
        ctx.log("Engines package theek se extract nahi hua lagta hai — "
                "MEERToolPro-Engines.zip dobara extract karo taake "
                "engines/ folder EXE ke bilkul barabar me aa jaye.",
                "ERROR")
        return False
    py = engines.find_python()
    if py is None:
        for line in engines.python_missing_hint("USB Backend Check"):
            ctx.log(line, "ERROR")
        return False
    ctx.log("USB backend check chal raha hai — phone ki zaroorat "
            "nahi, sirf is PC ka USB stack parakha ja raha hai.", "INFO")
    code = ctx.stream(py + [str(probe)], timeout=60, cwd=str(ENGINES_DIR))
    if code == 0:
        ctx.log("USB backend OK — kam az kam aik backend USB list kar "
                "raha hai. (Ye FRP ki kamyabi ki zamanat nahi — mode / "
                "DA / chipset alag cheezen hain.)", "OK")
        return True
    if code in (-1, -2, -3):
        ctx.log("USB Backend Check ruk gaya (exit %s) — dobara chalao."
                % code, "ERROR")
        return False
    ctx.log("USB backend FAIL — koi backend USB list nahi kar raha. "
            "Yehi wajah hai ke MTKClient 'USB enumeration error' deta "
            "hai.", "ERROR")
    ctx.log("Agla qadam: UTILITY > Install Drivers (VCOM + Filter + "
            "Vendor Pack) — libusb filter MediaTek USB Port par lagao, "
            "phir ye check dobara chalao. Serial (VCOM) rasta phir bhi "
            "chal sakta hai — FRP op COM port se chalao.", "WARN")
    return False
