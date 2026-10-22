"""
mtk_bl_lock.py — MTKClient se bootloader dobara lock karna (seccfg lock).

Relock tabhi mehfooz hai jab phone bilkul stock halat me ho — stock
firmware flash hua ho, koi modified partition (custom recovery,
patched vbmeta, root waghera) na ho. Gair-stock halat me relock
karne se phone boot-loop ya brick ho sakta hai, is liye operation
shuru hone se pehle saaf warning di jati hai.
"""

from core import engines
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_bl_lock",
    "category": "MTK",
    "name": "Bootloader Relock (seccfg)",
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


def _guard(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band karke "
                "Volume dono dabaye hue cable lagao (kuch models par "
                "test-point lagta hai).", "ERROR")
        return False
    return True


def run(ctx) -> bool:
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")

    ctx.log("KHABARDAR: Relock se pehle phone par bilkul STOCK firmware "
            "flash hona chahiye — koi modified partition (custom recovery, "
            "patched vbmeta, root waghera) ho to relock ke baad phone "
            "boot-loop ya brick ho sakta hai. Agar stock nahi hai to "
            "pehle Flash op se stock firmware flash karo, phir relock "
            "karo.", "WARN")

    ctx.progress(20, "Bootloader relock ho raha hai (seccfg lock)...")
    ctx.log("Bootloader relock (da seccfg lock) chal raha hai...", "INFO")
    code = ctx.stream(cmd + ["da", "seccfg", "lock"] + extra,
                      timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Bootloader relock fail hua (exit code {code}). Aam "
                "wajahen: device BROM se nikal gaya, ya DA/auth is "
                "chipset ke liye server-required hai (DESIGN.md ki "
                "matrix dekho). Bootloader abhi unlocked hi hai — ghabrane "
                "ki baat nahi, dobara koshish ki ja sakti hai.", "ERROR")
        return False

    ctx.progress(95, "Bootloader relock mukammal")
    ctx.log("Bootloader dobara lock ho gaya. Phone on karke check karo — "
            "agar stock firmware tha to aam tor par boot hoga.", "OK")
    return True
