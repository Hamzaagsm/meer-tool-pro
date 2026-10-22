"""
mtk_rpmb_erase.py — MTK RPMB Erase (MTKClient `da rpmb e`).

⚠️ SAB SE DESTRUCTIVE RPMB amal — is liye do hifazati seedhiyan:
  1. danger_gate SAB SE PEHLE — bhaari warning + GUI tasdeeq
     ke baghair device par AIK bhi koshish nahi; tasdeeq
     audit log me jati hai.
  2. ERASE SE PEHLE BACKUP LAZMI: pehle wahi range parh kar
     backups/ me mehfooz hoti hai. Backup na bane to erase
     hota hi nahi — bina backup ke tabahi ka button nahi.
     (Full erase par backup se hi total sectors gin kar erase
     range tay hoti hai — MTKClient ka sectors khali wala
     rasta full-erase par bharosa-mand nahi, is liye range
     hamesha explicit di jati hai.)

SUCCESS sirf dohre saboot par: DA ka "Done erasing rpmb"
jawab AUR erase ke baad usi range ki read-back jo poori
0x00 (zero) ho. Aik bhi saboot ghayab = FAIL, nakli success
kabhi nahi.
"""

from datetime import datetime

from core.danger_gate import danger_gate
from core import engines
from core.runner import BACKUPS_DIR
from ops.mtk_rpmb_read import (da_output_ok, engine_and_guard,
                               parse_range, range_args, run_capture)

OP = {
    "id": "mtk_rpmb_erase",
    "category": "MTK",
    "name": "⚠ RPMB Erase (DA) — KHATARNAAK",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
    "danger_write": True,
    "params": ("start_sector", "sectors"),
}


def _read_range(ctx, cmd, cwd, extra, sector, sectors, outfile):
    """Aik range parho — (bytes_written:int|None). Tasdeeq
    (Done marker + file + size) yahin hoti hai."""
    code, text = run_capture(
        ctx, cmd + ["da", "rpmb", "r", str(outfile)] +
        range_args(sector, sectors) + extra,
        cwd=cwd, timeout=600)
    if ctx.is_cancelled() or code in (-1, -2):
        return None
    if not da_output_ok(text, "r") or not outfile.is_file():
        return None
    size = outfile.stat().st_size
    if size == 0 or size % 256 != 0:
        return None
    if sectors is not None and size != sectors * 256:
        return None
    return size


def run(ctx) -> bool:
    # GATE SAB SE PEHLE — tasdeeq ke baghair zero koshish.
    if not danger_gate(ctx, "RPMB ERASE"):
        return False
    cmd, cwd = engine_and_guard(ctx)
    if cmd is None:
        return False
    sector, sectors, err = parse_range(getattr(ctx, "params", {}))
    if err:
        ctx.log(err, "ERROR")
        return False
    extra = engines.mtk_extra_args()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BACKUPS_DIR / f"rpmb-erase-{ts}"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False

    # --- Seedhi 2: pehle BACKUP (erase range ki asal parhai) ---
    ctx.progress(15, "Erase se pehle backup parha ja raha hai...")
    backup = outdir / "rpmb-before-erase.bin"
    if sectors is None:
        ctx.log("PARAMS me Sectors khali hai — is ka matlab hai "
                "POORI RPMB erase hogi. Backup bhi poori RPMB ka "
                "banega aur usi se total size tay hoga.", "WARN")
    got = _read_range(ctx, cmd, cwd, extra, sector, sectors, backup)
    if ctx.is_cancelled():
        return False
    if got is None:
        ctx.log("BACKUP NAHI BAN SAKA — is liye erase ROK diya "
                "gaya hai. Bina backup ke RPMB erase karna "
                "ghalti hoti; pehle wajah theek karo (DA mode / "
                "cable / RPMB dastiyabi) phir dobara koshish "
                "karo.", "ERROR")
        return False
    total_sectors = got // 256
    erase_sectors = sectors if sectors is not None else total_sectors
    ctx.log(f"Backup tayyar: {got} bytes — {backup} (ye file "
            "erase ke baad bhi mehfooz rahegi).", "DATA")
    ctx.log(f"Erase range: sector {sector} se {erase_sectors} "
            f"sectors ({erase_sectors * 256} bytes).", "INFO")
    ctx.log("Aakhri warning: is ke baad is range ka data DA ke "
            "zariye hi wapas aa sakta hai (backup file se RPMB "
            "Write op) — aur wo bhi key/auth halat par mabni "
            "hai. Tasdeeq pehle hi di ja chuki hai.", "WARN")

    # --- Asal erase (range hamesha explicit) ---
    ctx.progress(45, "RPMB erase ho raha hai (DA)...")
    code, text = run_capture(
        ctx, cmd + ["da", "rpmb", "e"] +
        range_args(sector, erase_sectors) + extra,
        cwd=cwd, timeout=600)
    if ctx.is_cancelled():
        return False
    if code in (-1, -2) or not da_output_ok(text, "e"):
        ctx.log("DA ke jawab me 'Done erasing rpmb' wala saboot "
                "NAHI mila — SUCCESS nahi diya ja raha. Backup "
                f"mehfooz hai: {backup}", "ERROR")
        return False
    ctx.log("DA ne 'Done erasing' kaha — ab read-back se asal "
            "tasdeeq (poori range zero honi chahiye)...", "INFO")

    # --- Read-back verify: poori range 0x00 ---
    back = outdir / "verify-readback.bin"
    ctx.progress(70, "Erase verify ho raha hai...")
    got2 = _read_range(ctx, cmd, cwd, extra, sector,
                       erase_sectors, back)
    if ctx.is_cancelled():
        return False
    ok = (got2 == erase_sectors * 256
          and back.is_file()
          and all(b == 0 for b in back.read_bytes()))
    if not ok:
        ctx.log("READ-BACK VERIFY FAIL — erase ke baad range "
                "poori zero nahi mili (ya parhai nahi gayi). "
                "Natija MASHKOOK hai; SUCCESS nahi diya ja raha. "
                f"Backup mehfooz hai: {backup}", "ERROR")
        return False
    try:
        back.unlink()
    except Exception:  # noqa: BLE001
        pass
    ctx.log("Read-back verify PASS — poori erase range zero "
            "(0x00) mili.", "OK")
    ctx.log("RPMB erase mukammal — 'Done erasing' + zero "
            "read-back, dono saboot ke saath. Backup: "
            f"{backup}", "OK")
    ctx.progress(95, "RPMB erase mukammal (verify shuda)")
    return True
