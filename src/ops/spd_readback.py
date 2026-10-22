"""
spd_readback.py — Unisoc FULL readback (tamam partitions → PAC-ready folder).

spd_cert_backup ka bara bhai: sirf prodnv nahi, partition_list ki
HAR partition aik-aik karke parhi jati hai aur backups/spd-<ts>/
folder me <partition>.bin ban kar ati hai. Folder me session ke
apne FDL1/FDL2 bhi fdl1.bin / fdl2.bin ke naam se copy hote hain —
yehi shart core/pac_builder.validate_readback ki hai (use
fdl1.bin chahiye hota hai), taake PAC Builder op is folder se
seedha .pac bana sake.

Do sessions lagte hain (spd_dump ki sakhtayi: read_part ko size
pehle se chahiye hota hai):
  Session A: partition_list — har partition ka asal size.
  Session B: tamam read_part commands AIK hi FDL session me
             chained (spd_reset wali proven tartib: partition_list
             + erase commands bhi aik hi session me chalte hain) —
             har partition dobara download-mode lagane ki zaroorat
             nahi.
Dono ke darmiyan phone dobara download mode me lagana hota hai —
log me wazeh hidayat ati hai aur tool wait karta hai.

Imaandari: SUCCESS sirf tab jab HAR file ka size partition_list
wale size se byte-to-byte match kare. Koi aik bhi file kam/zyada
ya ghayab ho to FAIL hai — jo files ban gayin wo folder me reh
jati hain (dobara koshish par kaam ayengi), lekin adhoore dump
ko full readback NAHI kaha jayega.
"""

import shutil
from datetime import datetime

from core import spd_fdl
from core.runner import BACKUPS_DIR

OP = {
    "id": "spd_readback",
    "category": "SPD / Unisoc",
    "name": "Full Readback / Dump (All Partitions → PAC-ready folder)",
    "engine": "spd_dump",
    "modes": ("SPD",),
    "server_required": False,
}


def run(ctx) -> bool:
    if not spd_fdl.spd_guard(ctx):
        return False
    session = spd_fdl.prepare_fdl(ctx)
    if session is None:
        return False

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BACKUPS_DIR / f"spd-{stamp}"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Readback folder nahi ban saka: {e}", "ERROR")
        return False
    plist = outdir / "partitions.xml"

    # --- Session A: partition list se tamam partitions ke sizes
    ctx.log("Session A: partition list parhi ja rahi hai (har "
            "partition ka asal size maloom karne ke liye)...", "INFO")
    ctx.progress(10, "Session A: partition list...")
    cmd = spd_fdl.session_args(session, ["partition_list", str(plist),
                                         "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0 or not plist.is_file():
        ctx.log(f"Partition list nahi ban saki (exit code {code}) — "
                "baghair asal sizes ke readback andaze se NAHI hoga. "
                "FDL/driver ki wajah upar ki lines me dekho.", "ERROR")
        return False
    try:
        parts = spd_fdl.parse_partition_xml(
            plist.read_text(encoding="utf-8", errors="ignore"))
    except OSError as e:
        ctx.log(f"Partition list parhi nahi ja saki: {e}", "ERROR")
        return False
    if not parts:
        ctx.log("Partition list khali hai — aik bhi partition ka "
                "saaf size nahi mila. Is model par full readback is "
                "raste se mehfooz nahi. Readback NAHI banaya gaya.",
                "ERROR")
        return False

    total = sum(parts.values())
    ctx.log(f"{len(parts)} partitions mile, kul size "
            f"{total:,} bytes ({total / (1024 * 1024):.1f} MB):",
            "INFO")
    for name, size in parts.items():
        ctx.log(f"  {name:20s} {size:,} bytes", "DATA")
    if "userdata" in parts:
        usize = parts["userdata"]
        ctx.log(f"KHABARDAR: userdata partition {usize:,} bytes "
                f"({usize / (1024 * 1024 * 1024):.2f} GB) hai — "
                "FULL readback me ye bhi poora parha jayega, is "
                "liye waqt bhi zyada lagega aur PC par itni khali "
                "jagah bhi lazmi hai. Cable bilkul mat hatana.",
                "WARN")
    ctx.log("Poora dump lamba chal sakta hai — phone ki battery "
            "aur PC ki khali jagah check kar lo.", "WARN")

    # --- FDL copy: PAC Builder ko is folder me fdl1.bin chahiye
    for key, dest_name in (("fdl1", "fdl1.bin"), ("fdl2", "fdl2.bin")):
        src = session[key]
        dest = outdir / dest_name
        try:
            shutil.copy2(src, dest)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"{dest_name} copy nahi ho saka ({src} se): {e} "
                    "— baghair FDL ke ye folder PAC-ready nahi "
                    "mana jayega.", "ERROR")
            return False
        if not dest.is_file() or \
                dest.stat().st_size != src.stat().st_size:
            ctx.log(f"{dest_name} copy na-mukammal hai (size match "
                    "nahi) — folder PAC-ready nahi mana jayega.",
                    "ERROR")
            return False
        ctx.log(f"{dest_name} folder me copy ho gaya "
                f"({dest.stat().st_size} bytes).", "INFO")

    # --- Session B: tamam partitions aik hi FDL session me chained
    ctx.log("Session A mukammal. **Ab phone ko dobara download "
            "mode me lagao** (band karke Volume dabaye hue cable) — "
            "tool 120 seconds wait karega, phir tamam partitions "
            "aik hi session me parhi jayengi.", "WARN")
    ctx.progress(30, "Session B: full readback (dobara download mode me lagao)...")
    commands = []
    for name, size in parts.items():
        outfile = outdir / f"{name}.bin"
        commands += ["read_part", name, "0", str(size), str(outfile)]
    commands += ["power_off"]
    cmd = spd_fdl.session_args(session, commands)
    code = spd_fdl.stream_yes(ctx, cmd, timeout=7200)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Readback session exit code {code} ke saath band "
                "hua — asal faisla files ki tasdeeq se hoga; jo "
                "file size se match na kare wo FAIL gini jayegi.",
                "WARN")

    # --- Tasdeeq: HAR file ka size partition_list se match lazmi
    failed = []
    for name, size in parts.items():
        f = outdir / f"{name}.bin"
        if not f.is_file():
            failed.append(f"{name} (file bani hi nahi)")
        elif f.stat().st_size != size:
            failed.append(
                f"{name} (size {f.stat().st_size} != {size})")
    if failed:
        ctx.log("Readback FAIL — ye partitions durust nahi parhi "
                f"gain: {'; '.join(failed)}", "ERROR")
        ctx.log(f"Note: jo files ban gayin hain wo folder me reh "
                f"jayengi ({outdir}) — dobara koshish par waqt "
                "bach sakta hai, lekin is halat me ye folder "
                "mukammal readback NAHI hai aur PAC is se mat "
                "banao.", "WARN")
        return False

    ctx.log(f"Full readback mukammal: {len(parts)} partitions, "
            f"kul {total:,} bytes — folder: {outdir}", "OK")
    ctx.log("Ab PAC Builder op is folder se .pac bana sakta hai "
            "(folder me fdl1.bin/fdl2.bin + tamam partition images "
            "mojood hain).", "OK")
    ctx.progress(95, "Full readback mukammal")
    return True
