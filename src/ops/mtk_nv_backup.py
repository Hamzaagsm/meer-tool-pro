"""
mtk_nv_backup.py — MTK NV (nvram + nvdata) jora backup, one-click.

IMEI repair ka sab se saaf rasta yahi hai (REPAIR-METHODS-RESEARCH
§3.1a): device ki apni NV mehfooz ho to kharabi par wohi wapas
likhne se asal IMEI khud-ba-khud wapas aa jata hai — koi number
type hi nahi hota. Android 10+ par IMEI nvdata me bhi rehta hai,
is liye dono hamesha JORA parhe jate hain; aik file wala backup
na-mukammal mana jata hai.
"""

from datetime import datetime

from core import engines
from core.runner import BACKUPS_DIR

OP = {
    "id": "mtk_nv_backup",
    "category": "MTK",
    "name": "NV Backup (nvram + nvdata)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}

PAIR = ("nvram", "nvdata")


def _engine(ctx):
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke "
                "engines/mtkclient/ folder me rakho.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def _guard(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone "
                "band karke Volume dono dabaye hue cable lagao.",
                "ERROR")
        return False
    return True


def read_pair(ctx, cmd, cwd, extra, outdir):
    """nvram+nvdata parho — (nvram_path, nvdata_path) ya None."""
    files = [outdir / f"{name}.bin" for name in PAIR]
    arg = ",".join(str(f) for f in files)
    code = ctx.stream(cmd + ["r", ",".join(PAIR), arg] + extra,
                      timeout=600, cwd=cwd)
    if code != 0:
        return None
    ok = [f for f in files if f.is_file() and f.stat().st_size > 0]
    if len(ok) != len(PAIR):
        return None
    return files


def run(ctx) -> bool:
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    extra = engines.mtk_extra_args()
    outdir = BACKUPS_DIR / ("mtk-nv-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False
    ctx.progress(30, "nvram + nvdata parhe ja rahe hain...")
    files = read_pair(ctx, cmd, cwd, extra, outdir)
    if ctx.is_cancelled():
        return False
    if files is None:
        ctx.log("NV backup FAIL — jora (nvram + nvdata) mukammal "
                "nahi parha ja saka. Aik file wala backup NV backup "
                "NAHI mana jata. Wajah upar ki lines me hai "
                "(BROM/auth/cable).", "ERROR")
        return False
    for f in files:
        ctx.log(f"{f.name}: {f.stat().st_size} bytes", "DATA")
    ctx.log(f"NV backup mukammal: {outdir} — yahi jora 'NV Restore' "
            "se wapas likha jayega; asal IMEI isi ke saath mehfooz "
            "hai.", "OK")
    ctx.progress(95, "NV backup mukammal")
    return True
