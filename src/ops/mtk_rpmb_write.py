"""
mtk_rpmb_write.py — MTK RPMB Write (MTKClient `da rpmb w`).

⚠️ DESTRUCTIVE: RPMB authenticated / anti-rollback area hai.
Is liye, IMEI gate ki hi discipline par:
  1. danger_gate SAB SE PEHLE — bhaari warning + GUI tasdeeq
     (neeche wale bar ki checkbox) ke baghair device par AIK
     bhi koshish nahi hoti; tasdeeq audit log me jati hai.
  2. BACKUP-FIRST: write se pehle usi range ka maujooda data
     parh kar backups/ me mehfooz hota hai — backup na bane
     to write hota hi nahi.
  3. Input file: tools/rpmb/ folder me SIRF AIK .bin (galat
     file khud nahi chunte — 0 ya zyada par guided FAIL).
  4. SUCCESS sirf dohre saboot par: DA ke jawab me "Done
     writing" ho AUR write ke baad usi range ki read-back
     karke bytes source se match hon. Sirf exit code ya sirf
     'Done' — koi aik akela kaafi nahi.

RPMB ki fitrat: write authenticated hota hai — device par
key programmed ho aur DA ke paas usi key ka rasta ho to hi
write hota hai; key mismatch par DA khud inkaar kar deta hai
aur ye op saaf FAIL deta hai. Ye is area ki asal hadd hai,
koi bypass daawa nahi.
"""

from datetime import datetime
from pathlib import Path

from core.danger_gate import danger_gate
from core import engines
from core.runner import BACKUPS_DIR, TOOLS_DIR
from ops.mtk_rpmb_read import (da_output_ok, engine_and_guard,
                               parse_range, range_args, run_capture)

OP = {
    "id": "mtk_rpmb_write",
    "category": "MTK",
    "name": "⚠ RPMB Write (DA) — KHATARNAAK",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
    "danger_write": True,
    "params": ("start_sector", "sectors"),
}

RPMB_INBOX = TOOLS_DIR / "rpmb"


def single_bin(ctx, folder):
    """Folder me bilkul AIK .bin ho to wahi, warna guided FAIL
    ke saath None (galat file khud kabhi nahi chunte)."""
    if not folder.is_dir():
        ctx.log(f"Input folder nahi mila: {folder} — pehle ye "
                "folder banao aur is me SIRF AIK .bin file rakho "
                "(jo RPMB me likhni hai).", "ERROR")
        return None
    bins = sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() == ".bin")
    if not bins:
        ctx.log(f"{folder} me koi .bin file nahi — likhne ke "
                "liye kuch nahi.", "ERROR")
        return None
    if len(bins) > 1:
        names = ", ".join(p.name for p in bins)
        ctx.log(f"{folder} me {len(bins)} .bin files hain: "
                f"{names} — galat file khud nahi chuni jayegi. "
                "Sirf wohi AIK file rakho jo is device ki RPMB "
                "ke liye hai, baqi hata do.", "ERROR")
        return None
    return bins[0]


def run(ctx) -> bool:
    # GATE SAB SE PEHLE — tasdeeq ke baghair zero koshish.
    if not danger_gate(ctx, "RPMB WRITE"):
        return False
    cmd, cwd = engine_and_guard(ctx)
    if cmd is None:
        return False
    sector, sectors, err = parse_range(getattr(ctx, "params", {}))
    if err:
        ctx.log(err, "ERROR")
        return False
    src = single_bin(ctx, RPMB_INBOX)
    if src is None:
        return False
    size = src.stat().st_size
    if size == 0:
        ctx.log(f"Input file khali hai: {src}", "ERROR")
        return False
    file_sectors = size // 256
    if file_sectors == 0:
        ctx.log(f"Input file {size} bytes hai — aik RPMB sector "
                "(256 bytes) se bhi chhoti, likhne ko kuch nahi.",
                "ERROR")
        return False
    if size % 256:
        ctx.log(f"Note: file ka size {size} bytes hai — aakhri "
                f"{size % 256} bytes (mukammal sector nahi) write "
                "nahi honge; MTKClient sirf mukammal sectors "
                "likhta hai.", "WARN")
    write_sectors = sectors if sectors is not None else file_sectors
    if write_sectors > file_sectors:
        ctx.log(f"PARAMS me {write_sectors} sectors mange gaye "
                f"lekin file me sirf {file_sectors} sectors ka "
                "data hai — file se aage write nahi ho sakta.",
                "ERROR")
        return False
    extra = engines.mtk_extra_args()
    ctx.log(f"File: {src} ({size} bytes)", "INFO")
    ctx.log(f"Write range: sector {sector} se {write_sectors} "
            f"sectors ({write_sectors * 256} bytes).", "INFO")
    ctx.log("RPMB note: ye authenticated area hai — write sirf "
            "tab hoga jab device/DA ka key rasta milega; key "
            "mismatch par DA inkaar karega aur ye op FAIL "
            "ayega. Anti-rollback / secure data kharab ho to "
            "kuch secure features mustaqil kharab ho sakte "
            "hain — ye warning dobara parh lo.", "WARN")

    # --- Backup-first: pehle maujooda data parh kar mehfooz ---
    bdir = BACKUPS_DIR / ("rpmb-write-" +
                          datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        bdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False
    backup = bdir / "rpmb-before-write.bin"
    ctx.progress(15, "Write se pehle backup parha ja raha hai...")
    bcode, btext = run_capture(
        ctx, cmd + ["da", "rpmb", "r", str(backup)] +
        range_args(sector, write_sectors) + extra,
        cwd=cwd, timeout=600)
    if ctx.is_cancelled():
        return False
    if (bcode in (-1, -2) or not da_output_ok(btext, "r")
            or not backup.is_file()
            or backup.stat().st_size != write_sectors * 256):
        ctx.log("BACKUP NAHI BAN SAKA — backup-first usool ki "
                "wajah se write ROK di gayi hai. Pehle wajah "
                "theek karo (DA mode / cable / RPMB dastiyabi), "
                "phir dobara koshish karo.", "ERROR")
        return False
    ctx.log(f"Backup tayyar (write se pehle ki halat): {backup}",
            "DATA")

    ctx.progress(35, "RPMB write ho raha hai (DA)...")
    code, text = run_capture(
        ctx, cmd + ["da", "rpmb", "w", str(src)] +
        range_args(sector, write_sectors) + extra,
        cwd=cwd, timeout=600)
    if ctx.is_cancelled():
        return False
    if code in (-1, -2) or not da_output_ok(text, "w"):
        ctx.log("DA ke jawab me 'Done writing' wala saboot NAHI "
                "mila — SUCCESS nahi diya ja raha. Wajah upar ke "
                "log me hai (key/auth inkaar, DA mode, cable).",
                "ERROR")
        return False
    ctx.log("DA ne 'Done writing' kaha — ab read-back se asal "
            "tasdeeq ho rahi hai...", "INFO")

    # Read-back verify — wohi range dobara parh kar bytes mila lo
    back = bdir / "readback.bin"
    ctx.progress(65, "Read-back verify ho raha hai...")
    code, text = run_capture(
        ctx, cmd + ["da", "rpmb", "r", str(back)] +
        range_args(sector, write_sectors) + extra,
        cwd=cwd, timeout=600)
    if ctx.is_cancelled():
        return False
    expected = src.read_bytes()[:write_sectors * 256]
    ok = (code not in (-1, -2) and da_output_ok(text, "r")
          and back.is_file()
          and back.stat().st_size == write_sectors * 256
          and back.read_bytes() == expected)
    if not ok:
        ctx.log("READ-BACK MATCH NAHI HUA — DA ne write ka kaha "
                "lekin device se wapas parha hua data source se "
                "nahi milta. Natija MASHKOOK hai; SUCCESS nahi "
                "diya ja raha. Device ko is halat me istemal / "
                "agla servicing step ehtiyat se karo.", "ERROR")
        return False
    try:
        back.unlink()  # verify file saaf; backup wali rehti hai
    except Exception:  # noqa: BLE001
        pass
    ctx.log(f"Backup (write se pehle ki halat) mehfooz hai: "
            f"{backup}", "INFO")
    ctx.log("Read-back verify PASS — likha hua data device se "
            "wapas parh kar byte-to-byte match hua.", "OK")
    ctx.log("RPMB write mukammal — 'Done writing' + read-back "
            "match, dono saboot ke saath.", "OK")
    ctx.progress(95, "RPMB write mukammal (verify shuda)")
    return True
