"""
mtk_info.py — MTKClient ke zariye BROM mode me device info / GPT parhna.

Engine resolution ab markazi helper (core.engines) se hoti hai — wahi
tarteeb tamam MTK ops me istemal hoti hai. Engine ya Python na mile to
operation CRASH nahi hota — log me saaf wajah aur setup guide aati hai,
aur FAIL return hota hai (nakli success kabhi nahi).

Device mode ghalat ho to bhi ye op koshish karta hai: sirf WARN deta
hai, kyun ke MTKClient khud device ka intezaar karta hai — user ko
mauqa milna chahiye ke phone BROM me laga kar operation chala sake.

Driver pre-check (Windows): engine chalane se pehle PC par purana
UsbDk laga hua mile to saaf WARN ajata hai — Windows ke naye builds
(24H2 / 26200) par UsbDk MTKClient ko native crash (0xC0000005)
kar deta hai. Wahee exit code aye to generic error ki jagah khaas
driver wali line ati hai — phone par shak nahi, driver par seedha
ishara.
"""

import re
import sys
from dataclasses import replace
from pathlib import Path

from core import engines
from core.device_watch import DeviceInfo
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_info",
    "category": "MTK",
    "name": "Read Info / GPT (BROM)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


_CRASH_CODES = (3221225477, -1073741819)  # 0xC0000005 dono suraton me

_CRASH_LINE = (
    "Engine crash hua (0xC0000005) — ye phone ka masla nahi, PC ke "
    "USB driver layer ka hai: UsbDk hatao + VCOM/filter setup karo "
    "(UTILITY → Install Drivers)."
)

_USBDK_WARN = (
    "Is PC par purana UsbDk laga hai — naye Windows par ye "
    "MTKClient ko crash karta hai. Naye pack ke drivers me UsbDk "
    "nahi hai; 'Install Drivers' chalao aur UsbDk Control Panel "
    "se uninstall kar do."
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


_CPU_RE = re.compile(r"CPU:\s*(MT\d+[A-Z]*|Helio\s+\S+|Dimensity\s+\S+)",
                     re.IGNORECASE)


def _cpu_hook(found):
    """MTKClient ki output se chip pakro (pehli saaf line hi)."""

    def _hook(line):
        if "chip" in found:
            return
        m = _CPU_RE.search(line or "")
        if m:
            found["chip"] = " ".join(m.group(1).split())

    return _hook


def _push_chip(ctx, found):
    """Read Info ke baad chip panel me bhejo (update_device chain).

    Sirf tab jab chip mili ho aur device object DeviceInfo jaisa ho —
    warna khamoshi (panel watcher wali halat par hi rahega)."""
    chip = found.get("chip")
    if not chip or not ctx.update_device:
        return
    try:
        dev = ctx.device
        if dev is None:
            return
        if isinstance(dev, DeviceInfo):
            new = replace(dev, chip=chip,
                          mode=dev.mode or "BROM",
                          detail=dev.detail or "MediaTek BROM")
        else:
            # Test/legacy device objects — attribute set best-effort
            new = dev
            try:
                new.chip = chip
            except Exception:  # noqa: BLE001
                return
        ctx.update_device(new)
    except Exception:  # noqa: BLE001 — panel update kabhi op nahi rokta
        pass


def _engine(ctx):
    """(cmd_prefix, cwd) ya (None, None) — nakami par guided log de chuka hoga."""
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke engines/mtkclient/ "
                "folder me rakho, ya system me 'mtk' command install karo. "
                "Engine ke baghair ye operation chal hi nahi sakta — "
                "ye nakami nahi, setup ki kami hai.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def run(ctx) -> bool:
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    _driver_precheck(ctx)
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band karke "
                "Volume dono dabaye hue cable lagao (kuch models par "
                "test-point lagta hai).", "WARN")
        # Phir bhi koshish: MTKClient khud wait karta hai — user ko mauqa do
    ctx.progress(10, "MTKClient device ka intezaar kar raha hai...")
    ctx.log("Phone ko BROM mode me lagao — MTKClient handshake karega.", "INFO")
    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")
    found_chip = {}
    code = ctx.stream(cmd + ["printgpt"] + extra, timeout=180, cwd=cwd,
                      line_hook=_cpu_hook(found_chip))
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "GPT parh li gayi")
        # 2026-10-24: Read Info ke baad chip panel me aaye — warna
        # upar "—" rehta hai aur maloomat sirf log me dab jati hai.
        # Sirf wahi chip jo MTKClient ne khud chhapi ho.
        _push_chip(ctx, found_chip)
        return True
    if code in _CRASH_CODES:
        ctx.log(_CRASH_LINE, "ERROR")
        return False
    ctx.log(f"MTKClient exit code {code} ke saath band hua. Aam wajahen: "
            "device BROM me nahi aya; DA/auth is chipset ke liye server-"
            "required ho sakta hai (DESIGN.md ki matrix dekho); ya USB "
            "driver (MediaTek VCOM) nahi laga.", "ERROR")
    return False
