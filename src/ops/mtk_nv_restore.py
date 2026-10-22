"""
mtk_nv_restore.py — MTK NV (nvram + nvdata) jora restore.

Device ki APNI NV wapas likhna = asal IMEI wapas (REPAIR-METHODS
§3.1a). Sharten (koi shortcut nahi):
  1. **IMEI gate** (core/imei_gate.py) — warning + user ki
     tasdeeq; baghair tasdeeq write shuru hi nahi hoti.
  2. Restore ke liye pehle se maujood mukammal jora (NV Backup
     wala folder) lazmi — na ho to FAIL.
  3. **Pre-restore snapshot lazmi:** maujooda haal ka jora pehle
     parh kar alag folder me mehfooz hota hai; snapshot fail ho
     to restore RUK jata hai — baghair wapsi ke raste ke write
     nahi hota.
"""

from datetime import datetime

from core import engines
from core.imei_gate import imei_write_gate
from core.runner import BACKUPS_DIR
from ops.mtk_nv_backup import PAIR, _engine, _guard, read_pair

OP = {
    "id": "mtk_nv_restore",
    "category": "MTK",
    "name": "NV Restore (nvram + nvdata) — Original IMEI Wapas",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
    "imei_write": True,
}


def _latest_pair_folder():
    """Sab se naya mtk-nv-* folder jis me mukammal jora ho."""
    if not BACKUPS_DIR.is_dir():
        return None
    cands = []
    for d in BACKUPS_DIR.glob("mtk-nv-2*"):
        if not d.is_dir() or "prerestore" in d.name:
            continue
        files = [d / f"{n}.bin" for n in PAIR]
        if all(f.is_file() and f.stat().st_size > 0 for f in files):
            cands.append(d)
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def run(ctx) -> bool:
    # IMEI GATE sab se pehle — warning + tasdeeq ke baghair
    # koi snapshot/write koshish bhi nahi.
    if not imei_write_gate(ctx):
        return False
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    extra = engines.mtk_extra_args()

    src = _latest_pair_folder()
    if src is None:
        ctx.log("Restore ke liye mukammal NV jora (nvram + nvdata) "
                "backups me nahi mila — pehle isi phone ka 'NV "
                "Backup (nvram + nvdata)' chalao. Baghair backup "
                "ke restore ka koi matlab nahi.", "ERROR")
        return False
    ctx.log(f"Restore ka source jora: {src}", "INFO")

    # Pre-restore snapshot — maujooda haal mehfooz, warna ruk jao
    snap = BACKUPS_DIR / ("mtk-nv-prerestore-" +
                          datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        snap.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Snapshot folder nahi ban saka: {e}", "ERROR")
        return False
    ctx.progress(25, "Pre-restore snapshot liya ja raha hai (maujooda NV)...")
    got = read_pair(ctx, cmd, cwd, extra, snap)
    if ctx.is_cancelled():
        return False
    if got is None:
        ctx.log("Pre-restore snapshot NAHI ban saka — is halat me "
                "restore karna wapsi ka rasta band kar dega, is "
                "liye write ROK di gayi hai. Pehle snapshot ki "
                "nakami ki wajah (upar ki lines) theek karo.",
                "ERROR")
        return False
    ctx.log(f"Snapshot mehfooz: {snap}", "OK")

    files = [src / f"{n}.bin" for n in PAIR]
    arg = ",".join(str(f) for f in files)
    ctx.progress(60, "NV jora wapas likha ja raha hai...")
    code = ctx.stream(cmd + ["w", ",".join(PAIR), arg] + extra,
                      timeout=600, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"NV write fail hua (exit code {code}). Maujooda "
                f"haal ka snapshot yahan mehfooz hai: {snap} — "
                "zarurat pare to wohi jora dobara restore kar sakte "
                "ho.", "ERROR")
        return False
    ctx.log("NV jora wapas likh diya gaya — device ka asal IMEI "
            "usi ke saath wapas aa gaya hoga. Phone on karke "
            "*#06# se dabbe wale number se mila kar tasdeeq karo.",
            "OK")
    ctx.progress(95, "NV restore mukammal")
    return True
