"""
mtk_bl_unlock.py — MTKClient se bootloader unlock (seccfg) + vbmeta patch.

Pehle `da seccfg unlock` chalti hai, phir `da vbmeta 3` se verity aur
verification dono band ho jate hain taake unlock ke baad phone aam
tor par boot ho. Unlock fail ho to FAIL; unlock ho jaye lekin vbmeta
patch na ho to bhi FAIL hai (adhoora kaam) — log me saaf likha ata
hai ke pehla hissa ho gaya hai, doosra nahi.
"""

from core import engines
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_bl_unlock",
    "category": "MTK",
    "name": "Bootloader Unlock + vbmeta (seccfg)",
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

    ctx.log("KHABARDAR: Bootloader unlock se tamam user data WIPE ho "
            "jata hai — photos, apps, accounts sab mit jayega. Pehle "
            "zaroori data ka backup lazmi lo.", "WARN")

    # Step 1: seccfg unlock — fail = overall FAIL
    ctx.progress(20, "Bootloader unlock ho raha hai (seccfg)...")
    ctx.log("Step 1/2: Bootloader unlock (da seccfg unlock)", "INFO")
    code = ctx.stream(cmd + ["da", "seccfg", "unlock"] + extra,
                      timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Bootloader unlock fail hua (exit code {code}). Aam "
                "wajahen: device BROM se nikal gaya, ya DA/auth is "
                "chipset ke liye server-required hai (DESIGN.md ki "
                "matrix dekho).", "ERROR")
        return False
    ctx.log("Bootloader unlock ho gaya (seccfg).", "OK")

    # Step 2: vbmeta mode 3 = verity + verification dono band
    ctx.progress(60, "vbmeta patch ho raha hai (verity + verification off)...")
    ctx.log("Step 2/2: vbmeta patch (da vbmeta 3 — disable verity + "
            "disable verification)", "INFO")
    code = ctx.stream(cmd + ["da", "vbmeta", "3"] + extra,
                      timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Unlock ho gaya lekin vbmeta patch nahi hua — ye "
                "ADHOORA (partial) natija hai. Phone is halat me boot "
                "par warning de sakta hai ya boot-loop ho sakta hai. "
                "Device dobara BROM me laga kar yehi op repeat karo "
                "taake vbmeta wala hissa mukammal ho.", "ERROR")
        return False
    ctx.log("vbmeta patch ho gaya (verity + verification off).", "OK")

    ctx.progress(95, "Bootloader unlock + vbmeta mukammal")
    return True
