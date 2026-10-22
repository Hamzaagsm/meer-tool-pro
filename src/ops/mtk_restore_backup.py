"""
mtk_restore_backup.py — MTK Full Backup ka one-click restore.

mtk_backup (Full Backup / Readback) se bani backups/mtk-<ts>/
folder ko wapas phone par likhta hai: folder ki GPT se scatter
banta hai (core/scatter_build — wahi API jo Scatter Creator op
istemal karta hai), scatter ko core.platforms_mtk.parse_scatter
se parh kar sirf is_download + file-maujood entries scatter ki
tartib me `w` se aik-aik karke likhi jati hain (mtk_flash wali
tartib). Koi aik write fail ho to wahin ruk jata hai — adhoora
restore success NAHI kaha jata.

IMEI gate SAB SE PEHLE hai: full restore nvram/nvdata bhi wapas
likhta hai, yani asal IMEI wala NV data bhi restore hota hai —
is liye imei_write_gate ki tasdeeq baghair ye op aik qadam bhi
aage nahi barhta.

Ye ASAL flash hai — ghalat backup (doosre model ka) phone ko
brick kar sakta hai. Preloader wali entry par khaas warning
mtk_flash ki tarah yahan bhi ati hai.
"""

from core import engines, scatter_build
from core.imei_gate import imei_write_gate
from core.platforms_mtk import parse_scatter
from core.runner import BACKUPS_DIR
from ops.mtk_frp_reset import _engine, _guard

OP = {
    "id": "mtk_restore_backup",
    "category": "MTK",
    "name": "Restore Backup (One-Click — Backup Folder → Flash)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
    "imei_write": True,
}


def _find_backup_folder():
    """Sab se naya backups/mtk-* folder jis me gpt.bin ho.

    'prerestore' / 'nv' naam wale folder skip hain — wo NV jore ke
    snapshot hain, poora backup nahi; unhen restore karna ghalti
    hogi.
    """
    if not BACKUPS_DIR.is_dir():
        return None
    folders = []
    for p in BACKUPS_DIR.glob("mtk-*"):
        if not p.is_dir():
            continue
        lname = p.name.lower()
        if "prerestore" in lname or "nv" in lname:
            continue
        if scatter_build.find_gpt_file(p) is not None:
            folders.append(p)
    if not folders:
        return None
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return folders[0]


def run(ctx) -> bool:
    # SAB SE PEHLE IMEI gate — full restore NV (IMEI) bhi likhta hai.
    if not imei_write_gate(ctx):
        return False
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False

    folder = _find_backup_folder()
    if folder is None:
        ctx.log("backups/ me koi mukammal MTK backup folder nahi "
                "mila (mtk-* folder jis me gpt.bin ho). Pehle MTK "
                "'Full Backup / Readback (All Partitions)' op "
                "chalao — restore usi backup se hoga.", "ERROR")
        return False
    ctx.log(f"Backup folder: {folder}", "INFO")

    gpt_path = scatter_build.find_gpt_file(folder)
    try:
        partitions = scatter_build.parse_gpt_binary(
            gpt_path.read_bytes())
    except Exception as e:  # noqa: BLE001
        ctx.log(f"GPT parhne me ghalti ({gpt_path.name}): {e}",
                "ERROR")
        return False
    file_names, warnings = scatter_build.match_files(folder,
                                                     partitions)
    for warn in warnings:
        ctx.log(warn, "WARN")
    text = scatter_build.build_scatter_text(partitions, file_names)
    scatter_path = folder / f"{folder.name}_scatter.txt"
    try:
        scatter_path.write_text(text, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Scatter file likhi nahi gayi: {e}", "ERROR")
        return False
    ctx.log(f"Scatter tayyar: {scatter_path}", "INFO")

    mapping = parse_scatter(scatter_path)
    queue = [(name, mapping[name]) for name in mapping]
    if not queue:
        ctx.log("Scatter se koi restore ke qabil partition nahi "
                "mila — backup folder me partition images maujood "
                "nahi lagtin. Backup dobara check karo.", "ERROR")
        return False

    ctx.log(f"Restore queue tayyar: {len(queue)} partitions wapas "
            "likhe jayenge.", "INFO")
    for part, fpath in queue:
        ctx.log(f"  • {part}  ←  {fpath.name}", "DATA")
    ctx.log("KHABARDAR: Ye poora backup WAPAS likha jayega — phone "
            "ki maujooda halat (data samait) is backup wali halat "
            "se badal jayegi. Battery full rakho, cable bilkul mat "
            "hatana, aur tasdeeq karo ke ye backup BILKUL ISI phone "
            "ka hai — doosre model ka backup phone ko brick kar "
            "sakta hai.", "WARN")

    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")

    total = len(queue)
    for idx, (part, fpath) in enumerate(queue, start=1):
        if ctx.is_cancelled():
            return False
        if part.lower().startswith("preloader"):
            ctx.log("KHAS KHABARDAR: Preloader likha ja raha hai — "
                    "ghalat preloader phone ko bilkul band (hard "
                    "brick) kar sakta hai. Ye backup isi phone ka "
                    "hai to hi aage barho.", "WARN")
        pct = 5 + int(90 * (idx - 1) / total)
        ctx.progress(pct, f"Restore ho raha hai: {part} ({idx}/{total})")
        ctx.log(f"Restore {idx}/{total}: {part} likha ja raha "
                "hai...", "INFO")
        code = ctx.stream(cmd + ["w", part, str(fpath)] + extra,
                          timeout=1800, cwd=cwd)
        if ctx.is_cancelled():
            return False
        if code != 0:
            ctx.log(f"Restore FAIL: {part} nahi likha gaya (exit "
                    f"code {code}) — operation yahin ruk gaya hai. "
                    "Phone adhoori halat me hai; restore mukammal "
                    "kiye baghair use on karne ki koshish mat karo.",
                    "ERROR")
            return False
        ctx.log(f"{part} restore ho gaya ({idx}/{total}).", "OK")

    ctx.progress(95, "Restore mukammal")
    ctx.log(f"Restore mukammal: {total} partitions wapas likhe "
            "gaye. Ab phone ko reset / power on karke check karo — "
            "pehli boot par kuch minute lag sakte hain.", "OK")
    return True
