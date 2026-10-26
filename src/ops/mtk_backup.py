"""
mtk_backup.py — MTKClient se poora readback (tamam partitions ka backup).

Pehle GPT parhi jati hai (uska fail hona sirf WARN hai), phir `rl` se
tamam partitions backups/ ke andar tareekh-wale folder me read hoti
hain. Aakhir me asal files check hoti hain: koi file read hi na hui
ho to FAIL hai — khali folder ko success nahi kaha jayega.

Flash ya koi bhi khatarnak op se pehle yahi backup sab se bara
sahara hai — ghalti ho jaye to wapas isi se restore mumkin hota hai.
"""

from datetime import datetime

from core import engines
from core.mtk_serial_fallback import MtkTransport, ensure_mtk_entry
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_backup",
    "category": "MTK",
    "name": "Full Backup / Readback (All Partitions)",
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
                "sirf cable lagao (button zaroori nahi — preloader port "
                "khud pakra jayega); na ho to Volume dono dabaye hue "
                "cable lagao (kuch models par test-point lagta hai).",
                "ERROR")
        return False
    return True


def run(ctx) -> bool:
    # Entry: cable-only wait (Y91i jaisa VCOM-bound case) — na mile
    # to asal _guard ki ERROR rehnumai + False (pehle wala bartao).
    ok, entry_note = ensure_mtk_entry(ctx)
    if not ok and not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")
    transport = MtkTransport(ctx, cmd, cwd, extra, entry_note=entry_note)

    outdir = BACKUPS_DIR / ("mtk-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001 — folder na bane to guided FAIL
        ctx.log(f"Backup folder nahi ban saka ({outdir}): {e}", "ERROR")
        return False
    ctx.log(f"Backup yahan save hoga: {outdir}", "INFO")
    ctx.log("Poora readback lamba chal sakta hai — phone ki battery aur "
            "PC ki khali jagah check kar lo, cable mat hatana.", "WARN")

    # Step 1: GPT — fail = sirf WARN, readback phir bhi koshish hogi
    ctx.progress(5, "GPT parhi ja rahi hai...")
    ctx.log("Step 1/2: GPT parhna (printgpt)", "INFO")
    code = transport.stream_step(["printgpt"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("GPT parhne me masla aya — phir bhi readback ki koshish "
                "jari hai; agar partitions na mile to wo bhi fail ho "
                "jayega aur wajah log me ajayegi.", "WARN")

    # Step 2: tamam partitions ka readback
    ctx.progress(15, "Tamam partitions read ho rahi hain (lamba waqt lag sakta hai)...")
    ctx.log("Step 2/2: Full readback shuru (rl) — ye ghanta bhi le sakta "
            "hai, sabr karo aur cable lagi rehne do.", "INFO")
    code = transport.stream_step(["rl", str(outdir)], timeout=3600)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Readback exit code {code} ke saath band hua — jo files "
                "ban chuki hain wo phir bhi check ki jayengi.", "WARN")

    # Tasdeeq: asal files bani hain ya nahi — khali folder success nahi
    try:
        files = [p for p in outdir.rglob("*") if p.is_file() and p.stat().st_size > 0]
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder check nahi ho saka: {e}", "ERROR")
        return False
    if not files:
        ctx.log("Backup FAIL: koi partition read nahi hua — folder khali "
                "hai. Aam wajahen: device BROM se nikal gaya, DA/auth "
                "server-required hai, ya cable/USB masla hai.", "ERROR")
        return False
    total = sum(p.stat().st_size for p in files)
    mb = total / (1024 * 1024)
    ctx.log(f"Backup mukammal: {len(files)} files, kul size "
            f"{mb:.1f} MB — jagah: {outdir}", "OK")
    ctx.progress(95, "Backup mukammal")
    return True
