"""
mtk_info.py — MTKClient ke zariye BROM mode me device info / GPT parhna.

Engine resolution ab markazi helper (core.engines) se hoti hai — wahi
tarteeb tamam MTK ops me istemal hoti hai. Engine ya Python na mile to
operation CRASH nahi hota — log me saaf wajah aur setup guide aati hai,
aur FAIL return hota hai (nakli success kabhi nahi).

Device mode ghalat ho to bhi ye op koshish karta hai: sirf WARN deta
hai, kyun ke MTKClient khud device ka intezaar karta hai — user ko
mauqa milna chahiye ke phone BROM me laga kar operation chala sake.
"""

from core import engines
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_info",
    "category": "MTK",
    "name": "Read Info / GPT (BROM)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


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
    code = ctx.stream(cmd + ["printgpt"] + extra, timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "GPT parh li gayi")
        return True
    ctx.log(f"MTKClient exit code {code} ke saath band hua. Aam wajahen: "
            "device BROM me nahi aya; DA/auth is chipset ke liye server-"
            "required ho sakta hai (DESIGN.md ki matrix dekho); ya USB "
            "driver (MediaTek VCOM) nahi laga.", "ERROR")
    return False
