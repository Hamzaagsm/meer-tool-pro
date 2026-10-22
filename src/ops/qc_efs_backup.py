"""
qc_efs_backup.py — Qualcomm EFS partitions ka selective backup.

Poora `rl` readback lamba hota hai; EFS ka asal kaam sirf in
partitions se hai: modemst1, modemst2, fsg (+ fsc jahan ho) —
asal IMEI/EFS inhi me rehta hai (REPAIR-METHODS-RESEARCH §3.3).
Sirf yehi parhe jate hain, files ki asal maujoodgi (size > 0)
check karke hi SUCCESS milta hai. fsc har model me nahi hota —
us ka na milna WARN hai, nakami nahi.
"""

from datetime import datetime

from core.runner import BACKUPS_DIR
from ops.qc_edl_info import _resolve_edl

OP = {
    "id": "qc_efs_backup",
    "category": "Qualcomm",
    "name": "EFS Backup (modemst1/2, fsg, fsc)",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
}

CORE_PARTS = ("modemst1", "modemst2", "fsg")
OPTIONAL_PARTS = ("fsc",)
ALL_PARTS = CORE_PARTS + OPTIONAL_PARTS


def read_efs_set(ctx, cmd, cwd, loader, outdir):
    """EFS set parho — {partition: Path} jo asal parha gaya.
    Core partitions ki nakami log me wazeh ati hai."""
    got = {}
    for name in ALL_PARTS:
        if ctx.is_cancelled():
            break
        out = outdir / f"{name}.bin"
        code = ctx.stream(cmd + ["r", name, str(out),
                                 f"--loader={loader}"],
                          timeout=300, cwd=cwd)
        if code == 0 and out.is_file() and out.stat().st_size > 0:
            got[name] = out
            ctx.log(f"{name}: {out.stat().st_size} bytes parha gaya.",
                    "DATA")
        elif name in OPTIONAL_PARTS:
            ctx.log(f"{name} nahi parha ja saka — ye partition har "
                    "model me nahi hota, aage barh rahe hain.", "WARN")
        else:
            ctx.log(f"{name} parhne me nakami (exit code {code}) — "
                    "ye core EFS partition hai.", "WARN")
    return got


def run(ctx) -> bool:
    resolved = _resolve_edl(ctx)
    if resolved is None:
        return False
    cmd, cwd, loader = resolved
    outdir = BACKUPS_DIR / ("qc-efs-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False
    ctx.progress(25, "EFS partitions parhi ja rahi hain...")
    got = read_efs_set(ctx, cmd, cwd, loader, outdir)
    if ctx.is_cancelled():
        return False
    missing = [n for n in CORE_PARTS if n not in got]
    if missing:
        ctx.log("EFS backup NA-MUKAMMAL — core partitions nahi "
                f"parhe ja sake: {', '.join(missing)}. Aadha EFS "
                "backup asal backup NAHI mana jata.", "ERROR")
        return False
    ctx.log(f"EFS backup mukammal: {outdir} "
            f"({', '.join(sorted(got))}) — yehi set 'EFS Restore' "
            "se wapas likha jayega.", "OK")
    ctx.progress(95, "EFS backup mukammal")
    return True
