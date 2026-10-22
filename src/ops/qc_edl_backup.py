"""
qc_edl_backup.py — EDL (9008) mode me tamam partitions ka full backup.

bkerler edl ke `rl` se har partition backups/ ke andar waqt ke naam wale
folder me parha jata hai. Kaam mukammal tab mana jata hai jab folder me
asal (size > 0) files maujood hon — khali folder success nahi.
"""

from datetime import datetime

from core import engines
from core.runner import BACKUPS_DIR

OP = {
    "id": "qc_edl_backup",
    "category": "Qualcomm",
    "name": "EDL Full Backup (All Partitions)",
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

    outdir = BACKUPS_DIR / ("qc-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    outdir.mkdir(parents=True, exist_ok=True)
    ctx.log(f"Backup folder: {outdir}", "INFO")
    ctx.progress(10, "Full backup chal raha hai — waqt lag sakta hai...")
    code = ctx.stream(cmd + ["rl", str(outdir), f"--loader={loader}"],
                      timeout=3600, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"edl backup fail hua (exit code {code}).", "ERROR")
        return False

    files = [p for p in outdir.rglob("*")
             if p.is_file() and p.stat().st_size > 0]
    if not files:
        ctx.log("Backup folder me koi asal file nahi bani — backup "
                "mukammal nahi hua.", "ERROR")
        return False
    total = sum(p.stat().st_size for p in files)
    ctx.log(f"Backup files: {len(files)}, total size: "
            f"{total / (1024 * 1024):.2f} MB — jagah: {outdir}", "INFO")
    ctx.progress(95, "Backup mukammal")
    return True
