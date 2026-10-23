"""
qc_edl_info.py — EDL (9008) mode me bkerler edl se GPT / partition info parhna.

Device EDL mode me hona lazmi hai, edl client engines/edl/ se milta hai
aur firehose loader user ki apni library (tools/loaders/qualcomm/) se
uthaya jata hai — koi loader bundle nahi kiya gaya.

Driver pre-check (Windows): engine chalane se pehle PC par purana
UsbDk laga hua mile to saaf WARN ajata hai — Windows ke naye builds
(24H2 / 26200) par UsbDk USB engines ko native crash (0xC0000005)
kar deta hai. Wahee exit code aye to generic error ki jagah khaas
driver wali line ati hai.
"""

import sys
from pathlib import Path

from core import engines

_CRASH_CODES = (3221225477, -1073741819)  # 0xC0000005 dono suraton me

_CRASH_LINE = (
    "Engine crash hua (0xC0000005) — ye phone ka masla nahi, PC ke "
    "USB driver layer ka hai: UsbDk hatao + VCOM/filter setup karo "
    "(UTILITY → Install Drivers)."
)

_USBDK_WARN = (
    "Is PC par purana UsbDk laga hai — naye Windows par ye USB "
    "engines (edl) ko crash karta hai. Naye pack ke drivers me "
    "UsbDk nahi hai; 'Install Drivers' chalao aur UsbDk Control "
    "Panel se uninstall kar do."
)


def _usbdk_installed() -> bool:
    """PC par UsbDk mojood hai ya nahi (best-effort, kabhi raise nahi).

    Nishaan: 'UsbDk Runtime Library' folder (Program Files dono
    suraton me) ya UsbDk service ki registry key. Sirf Windows
    par check hota hai."""
    if not sys.platform.startswith("win"):
        return False
    for base in (r"C:\Program Files", r"C:\Program Files (x86)"):
        try:
            if (Path(base) / "UsbDk Runtime Library").is_dir():
                return True
        except Exception:  # noqa: BLE001 — check kabhi rukawat nahi
            pass
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\UsbDk")
        key.Close()
        return True
    except Exception:  # noqa: BLE001 — key na mile to yehi jawab hai
        return False


def _driver_precheck(ctx):
    """Engine se pehle driver ki halat — UsbDk mile to WARN."""
    if _usbdk_installed():
        ctx.log(_USBDK_WARN, "WARN")

OP = {
    "id": "qc_edl_info",
    "category": "Qualcomm",
    "name": "EDL Read Info / GPT",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
}


def _resolve_edl(ctx):
    """Guard + engine + loader — (cmd, cwd, loader) ya None (FAIL tayyar)."""
    dev = ctx.device
    if not dev or dev.mode != "EDL":
        ctx.log("Device EDL (9008) mode me nahi mila. Phone band karke "
                "Volume Up+Down dono dabaye hue cable lagao — Device "
                "Manager me 'Qualcomm HS-USB QDLoader 9008' ana chahiye.", "ERROR")
        return None
    cmd, cwd, note = engines.find_edl()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("EDL client"):
                ctx.log(line, "WARN")
        else:
            ctx.log(note, "ERROR")
            ctx.log("Guide: engines/edl/ me edl client ki copy honi chahiye.", "WARN")
        return None
    ctx.log(note, "INFO")
    loader, lnote = engines.pick_qualcomm_loader(dev)
    if loader is None:
        ctx.log(lnote, "ERROR")
        ctx.log("Guide: loaders Loaders Library "
                "(tools/loaders/qualcomm/) se ate hain — pack install "
                "hai ya nahi, 'EDL Loader Library' op se check karo; "
                "apne alag loaders bhi wahan <brand>/ subfolder me "
                "rakh sakte ho, ya 'Loaders Library Import' op se "
                "andar kar sakte ho.", "WARN")
        return None
    if lnote:
        ctx.log(lnote, "INFO")
    ctx.log(f"Loader: {loader}", "INFO")
    return cmd, cwd, loader


def run(ctx) -> bool:
    resolved = _resolve_edl(ctx)
    if resolved is None:
        return False
    cmd, cwd, loader = resolved
    _driver_precheck(ctx)
    ctx.progress(20, "GPT parhi ja rahi hai...")
    code = ctx.stream(cmd + ["printgpt", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "GPT parh li gayi")
        return True
    if code in _CRASH_CODES:
        ctx.log(_CRASH_LINE, "ERROR")
        return False
    ctx.log(f"edl printgpt fail hua (exit code {code}). Aam wajahen: "
            "loader is model/chip ka nahi hai; 9008 driver (Qualcomm "
            "HS-USB) nahi laga; ya cable/port ka masla hai.", "ERROR")
    return False
