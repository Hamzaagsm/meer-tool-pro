"""
qc_efs_restore.py — Qualcomm EFS partitions ka selective restore.

EFS wapas likhna NV/IMEI wala kaam hai — sharten:
  1. **IMEI gate** (warning + tasdeeq) sab se pehle.
  2. Source = sab se naya mukammal qc-efs-* backup (isi tool ke
     'EFS Backup' wala). Na ho to FAIL.
  3. **Pre-restore snapshot lazmi:** maujooda EFS set pehle
     alag folder me parha jata hai; core set ka snapshot na
     bane to write RUK jati hai.
  4. Sirf wohi partitions likhe jate hain jo source backup me
     asal maujood hain.
"""

from datetime import datetime

from core.imei_gate import imei_write_gate
from core.runner import BACKUPS_DIR
from ops.qc_edl_info import _resolve_edl
from ops.qc_efs_backup import ALL_PARTS, CORE_PARTS, read_efs_set

OP = {
    "id": "qc_efs_restore",
    "category": "Qualcomm",
    "name": "EFS Restore (modemst1/2, fsg, fsc) — Original IMEI",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
    "imei_write": True,
}


def _latest_efs_folder():
    if not BACKUPS_DIR.is_dir():
        return None
    cands = []
    for d in BACKUPS_DIR.glob("qc-efs-2*"):
        if not d.is_dir() or "prerestore" in d.name:
            continue
        if all((d / f"{n}.bin").is_file() and
               (d / f"{n}.bin").stat().st_size > 0
               for n in CORE_PARTS):
            cands.append(d)
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def run(ctx) -> bool:
    # IMEI GATE — warning + tasdeeq sab se pehle.
    if not imei_write_gate(ctx):
        return False
    resolved = _resolve_edl(ctx)
    if resolved is None:
        return False
    cmd, cwd, loader = resolved

    src = _latest_efs_folder()
    if src is None:
        ctx.log("Restore ke liye mukammal EFS backup (modemst1, "
                "modemst2, fsg wala qc-efs-* folder) nahi mila — "
                "pehle 'EFS Backup' chalao. Baghair apne backup ke "
                "restore nahi hoga.", "ERROR")
        return False
    ctx.log(f"Restore ka source: {src}", "INFO")
    ctx.log("⚠️ Ye EFS SIRF usi device ki hai jis ka backup liya "
            "tha — doosre phone ka EFS likhna us ki pehchan "
            "badal dega (jurm + brick risk). Tasdeeq ke saath hi "
            "aage barho.", "WARN")

    snap = BACKUPS_DIR / ("qc-efs-prerestore-" +
                          datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        snap.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Snapshot folder nahi ban saka: {e}", "ERROR")
        return False
    ctx.progress(25, "Pre-restore snapshot (maujooda EFS) liya ja raha hai...")
    got = read_efs_set(ctx, cmd, cwd, loader, snap)
    if ctx.is_cancelled():
        return False
    if any(n not in got for n in CORE_PARTS):
        ctx.log("Pre-restore snapshot ka core set NAHI ban saka — "
                "baghair wapsi ke raste ke EFS write nahi hogi. "
                "Restore ROK di gayi hai.", "ERROR")
        return False
    ctx.log(f"Snapshot mehfooz: {snap}", "OK")

    written = []
    for name in ALL_PARTS:
        f = src / f"{name}.bin"
        if not f.is_file():
            continue
        if ctx.is_cancelled():
            return False
        ctx.progress(60, f"{name} wapas likha ja raha hai...")
        code = ctx.stream(cmd + ["w", name, str(f),
                                 f"--loader={loader}"],
                          timeout=300, cwd=cwd)
        if code != 0:
            ctx.log(f"{name} write fail hua (exit code {code}). "
                    f"Ab tak likhe gaye: "
                    f"{', '.join(written) if written else 'koi nahi'}. "
                    f"Maujooda haal ka snapshot yahan hai: {snap}",
                    "ERROR")
            return False
        written.append(name)
        ctx.log(f"{name} likh diya gaya.", "OK")
    ctx.log("EFS restore mukammal — likhe gaye: "
            + ", ".join(written) + ". Phone restart karke network "
            "aur *#06# (asal IMEI) check karo.", "OK")
    ctx.progress(95, "EFS restore mukammal")
    return True
