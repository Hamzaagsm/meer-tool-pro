"""
qc_sector_write.py — Qualcomm EDL Raw Sector Write (edl `ws`).

⚠️ DESTRUCTIVE: raw sector write galat jagah par ho to GPT /
boot / modem — kuch bhi mustaqil kharab ho sakta hai. Is liye:
  1. danger_gate SAB SE PEHLE (IMEI-gate wali hi discipline:
     bhaari warning + GUI tasdeeq + audit line). Baghair
     tasdeeq device par AIK bhi koshish nahi.
  2. BACKUP-FIRST: write se pehle usi range ke maujooda
     sectors parh kar backups/ me mehfooz hote hain — backup
     na bane to write hota hi nahi.
  3. Input: tools/sector-inbox/ me SIRF AIK .bin (galat file
     khud nahi chunte).
  4. Loader lazmi (brand-signed firehose); na ho to guided FAIL.
  5. SUCCESS sirf dohre saboot par: `ws` exit 0 AUR usi range
     ki read-back (`rs`) ke pehle bytes source file se
     byte-to-byte match. Sector size PARAMS se na diya ho to
     read-back 4096 phir 512 par try hoti hai — jo match kare.

Likhai hamesha PARAMS bar ke LUN + Start Sector se shuru
hoti hai; file jitni bari hai utne hi sectors aage jate hain.
"""

from datetime import datetime

from core.danger_gate import danger_gate
from core import engines
from core.runner import BACKUPS_DIR, TOOLS_DIR
from ops.qc_sector_read import (parse_sector_params,
                                resolve_edl)

OP = {
    "id": "qc_sector_write",
    "category": "Qualcomm",
    "name": "⚠ Raw Sector Write (EDL ws) — KHATARNAAK",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
    "danger_write": True,
    "params": ("lun", "start_sector", "sector_size"),
}

SECTOR_INBOX = TOOLS_DIR / "sector-inbox"


def _single_bin(ctx, folder):
    """Folder me bilkul AIK .bin — warna guided FAIL + None."""
    if not folder.is_dir():
        ctx.log(f"Input folder nahi mila: {folder} — pehle ye "
                "folder banao aur is me SIRF AIK .bin file rakho "
                "(jo sectors me likhni hai).", "ERROR")
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
                "Sirf wohi AIK file rakho jo is device/range ke "
                "liye hai, baqi hata do.", "ERROR")
        return None
    return bins[0]


def _sectors_for(size, ssize):
    return -(-size // ssize)  # ceil


def run(ctx) -> bool:
    # GATE SAB SE PEHLE — tasdeeq ke baghair zero koshish.
    if not danger_gate(ctx, "RAW SECTOR WRITE (EDL)"):
        return False
    loader = resolve_edl(ctx)
    if loader is None:
        return False
    p, err = parse_sector_params(getattr(ctx, "params", {}))
    if err:
        ctx.log(err, "ERROR")
        return False
    src = _single_bin(ctx, SECTOR_INBOX)
    if src is None:
        return False
    size = src.stat().st_size
    if size == 0:
        ctx.log(f"Input file khali hai: {src}", "ERROR")
        return False
    cmd, cwd = engines.find_edl()
    ctx.log(f"File: {src} ({size} bytes)", "INFO")
    ctx.log(f"Write jagah: LUN {p['lun']}, sector "
            f"{p['start_sector']} se aage (file ke size ke "
            "hisaab se sectors).", "INFO")
    candidates = ([p["sector_size"]] if p["sector_size"]
                  else [4096, 512])
    outdir = BACKUPS_DIR / ("qc-sector-write-" +
                            datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False

    # --- Backup-first: pehle maujooda sectors parh kar mehfooz ---
    backup_ss = None
    backup_file = None
    for ss in candidates:
        count = _sectors_for(size, ss)
        bfile = outdir / f"before-write-ss{ss}.bin"
        rargs = ["rs", str(p["start_sector"]), str(count),
                 str(bfile), f"--lun={p['lun']}",
                 f"--loader={loader}", f"--sectorsize={ss}"]
        ctx.progress(15, f"Backup read (sector size {ss})...")
        rcode = ctx.stream(cmd + rargs, cwd=cwd, timeout=600)
        if ctx.is_cancelled():
            return False
        if (rcode == 0 and bfile.is_file()
                and bfile.stat().st_size == count * ss):
            backup_ss, backup_file = ss, bfile
            break
        ctx.log(f"Sector size {ss} par backup read nahi ho "
                "saka — " + ("agla size try ho raha hai..."
                              if ss != candidates[-1] else
                              "koi aur size baqi nahi."), "WARN")
    if backup_ss is None:
        ctx.log("BACKUP NAHI BAN SAKA — backup-first usool ki "
                "wajah se write ROK di gayi hai. Pehle wajah "
                "theek karo (loader / connection / range), phir "
                "dobara koshish karo.", "ERROR")
        return False
    ctx.log(f"Backup tayyar (write se pehle ki halat, sector "
            f"size {backup_ss}): {backup_file}", "DATA")

    # --- Asal write ---
    args = ["ws", str(p["start_sector"]), str(src),
            f"--lun={p['lun']}", f"--loader={loader}"]
    if p["sector_size"]:
        args.append(f"--sectorsize={p['sector_size']}")
    ctx.progress(35, "Raw sectors likhe ja rahe hain (EDL)...")
    code = ctx.stream(cmd + args, cwd=cwd, timeout=900)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"edl ws nakam (exit {code}) — upar ke log me "
                f"wajah hai (loader / connection / range). "
                f"Backup mehfooz hai: {backup_file}", "ERROR")
        return False
    ctx.log("edl ne write complete kaha — ab read-back se asal "
            "tasdeeq ho rahi hai...", "INFO")

    # Read-back verify — source ke pehle bytes match lazmi;
    # pehle backup wala sector size, phir dusra candidate.
    src_bytes = src.read_bytes()
    order = [backup_ss] + [s for s in candidates if s != backup_ss]
    matched_ss = None
    for ss in order:
        count = _sectors_for(size, ss)
        back = outdir / f"readback-{ss}.bin"
        rargs = ["rs", str(p["start_sector"]), str(count),
                 str(back), f"--lun={p['lun']}",
                 f"--loader={loader}", f"--sectorsize={ss}"]
        ctx.progress(65, f"Read-back verify (sector size {ss})...")
        rcode = ctx.stream(cmd + rargs, cwd=cwd, timeout=600)
        if ctx.is_cancelled():
            return False
        if (rcode == 0 and back.is_file()
                and back.stat().st_size == count * ss
                and back.read_bytes()[:size] == src_bytes):
            matched_ss = ss
            break
        ctx.log(f"Sector size {ss} par read-back match nahi "
                "hua — " + ("agla size try ho raha hai..."
                             if ss != order[-1] else
                             "koi aur size baqi nahi."), "WARN")
    if matched_ss is None:
        ctx.log("READ-BACK MATCH NAHI HUA — write ke baad device "
                "se wapas parha hua data source se nahi milta. "
                "Natija MASHKOOK hai; SUCCESS nahi diya ja raha.",
                "ERROR")
        return False
    ctx.log(f"Read-back verify PASS (sector size {matched_ss}) "
            "— likha hua data byte-to-byte match hua.", "OK")
    ctx.log("Raw sector write mukammal — exit code + read-back "
            "match, dono saboot ke saath.", "OK")
    ctx.progress(95, "Raw sector write mukammal (verify shuda)")
    return True
