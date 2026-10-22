"""
mtk_info.py — MTKClient ke zariye BROM mode me device info / GPT parhna.

MTKClient open-source engine hai. Teen jagah dhoondhte hain:
  1. PATH par `mtk` command
  2. app ke tools/mtkclient/ folder me mtk.py (vendored copy)
  3. `python -m mtkclient` module ke tor par

Engine na mile to operation CRASH nahi hota — log me saaf wajah aur
setup guide aati hai, aur FAIL return hota hai (nakli success kabhi nahi).
"""

import shutil
import sys
from pathlib import Path

from core.runner import TOOLS_DIR

OP = {
    "id": "mtk_info",
    "category": "MTK",
    "name": "Read Info / GPT (BROM)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


def find_mtk():
    """MTKClient chalane ki command (list) ya None wapas karo."""
    exe = shutil.which("mtk")
    if exe:
        return [exe]
    vendored = TOOLS_DIR / "mtkclient" / "mtk.py"
    if vendored.is_file():
        return [sys.executable, str(vendored)]
    vendored2 = TOOLS_DIR / "mtkclient" / "mtk"
    if vendored2.is_file():
        return [sys.executable, str(vendored2)]
    return None


def run(ctx) -> bool:
    cmd = find_mtk()
    if cmd is None:
        ctx.log("MTKClient engine setup nahi hai.", "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke tools/mtkclient/ "
                "folder me rakho, ya system me 'mtk' command install karo. "
                "Engine ke baghair ye operation chal hi nahi sakta — "
                "ye nakami nahi, setup ki kami hai.", "WARN")
        return False
    dev = ctx.device
    if not dev or dev.mode not in ("BROM", "PRELOADER"):
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band karke "
                "Volume dono dabaye hue cable lagao (model ke hisaab se "
                "test-point bhi lag sakta hai).", "WARN")
        # Phir bhi koshish: MTKClient khud wait karta hai — user ko mauqa do
    ctx.progress(10, "MTKClient device ka intezaar kar raha hai...")
    ctx.log("Phone ko BROM mode me lagao — MTKClient handshake karega.", "INFO")
    code = ctx.stream(cmd + ["printgpt"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "GPT parh li gayi")
        return True
    ctx.log(f"MTKClient exit code {code} ke saath band hua. Aam wajahen: "
            "device BROM me nahi aya, DA/auth is chipset ke liye server-"
            "required hai (DESIGN.md ki matrix dekho), ya USB driver "
            "(MediaTek VCOM) nahi laga.", "ERROR")
    return False
