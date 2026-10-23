"""
util_dump_analyser.py — Dump Analyser (offline GPT / file pehchan).

PAID-TOOLS-TEARDOWN ka item (Infinity ke free DumpTool wali
soch, [PUBLIC-METHOD]): dukaan par aksar koi dump file aati hai
— pata hona chahiye ke ye kis phone ki hai, andar kaun si
partitions hain, aur ye asal me hai kya. Ye op WAHI batata hai.

Khalis PC-side op: koi device nahi, koi write nahi. Input
tools/firmware-inbox ki sab se nayi file (payload op wala hi
tareeqa). Bari dump (GBs) par bhi poori file memory me NAHI
ladi jati — sirf header + entries wale hisse seek karke parhe
jate hain (stdlib struct).

Natija:
  - GPT (EFI PART) mile to poori partition table: naam,
    first/last LBA, size — SUCCESS.
  - GPT na mile to saaf "GPT nahi mila" + file size + pehle
    bytes se pehchan (sparse image / PAC / ZIP / ELF / scatter
    text) — FAIL (nakli success nahi; pehchan log me hoti hai).
"""

from __future__ import annotations

import struct
from pathlib import Path

from core import firmware_files
from core.runner import TOOLS_DIR

OP = {
    "id": "util_dump_analyser",
    "category": "Utility",
    "name": "Dump Analyser (GPT / file pehchan)",
    "engine": "python-stdlib",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "firmware-inbox"

_SECTORS = (512, 4096)
_MAX_ENTRIES = 1024
_MAX_ENTRY_BYTES = 4 * 1024 * 1024


def _human(n):
    """Bytes -> parhne ke qabil size (1536 -> '1.5 KB')."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def find_gpt(read_at):
    """GPT header dhoondho — (sector_size, header_dict) ya None.

    read_at(offset, length) -> bytes. Aam jagahen: LBA1 par
    sector 512 / 4096; dump agar seedha header (LBA1) se shuru
    ho to offset 0 bhi qabool hai (gpt_parse wala hi usool).
    header_dict: entries_lba, num_entries, entry_size, hdr_off.
    """
    for sector in _SECTORS:
        hdr = read_at(sector, 92)
        if len(hdr) >= 92 and hdr[:8] == b"EFI PART":
            return sector, _header_fields(hdr, sector)
    hdr = read_at(0, 92)
    if len(hdr) >= 92 and hdr[:8] == b"EFI PART":
        return 512, _header_fields(hdr, 0)
    return None


def _header_fields(hdr, hdr_off):
    return {
        "entries_lba": struct.unpack_from("<Q", hdr, 72)[0],
        "num_entries": struct.unpack_from("<I", hdr, 80)[0],
        "entry_size": struct.unpack_from("<I", hdr, 84)[0],
        "hdr_off": hdr_off,
    }


def parse_entries(read_at, sector, header):
    """Partition entries -> [{name, first, last}] ya ValueError."""
    entry_size = header["entry_size"]
    num = header["num_entries"]
    if entry_size < 128 or entry_size > 4096:
        raise ValueError(f"GPT entry size ghair-mamooli hai: "
                         f"{entry_size}")
    if num == 0 or num > _MAX_ENTRIES:
        raise ValueError(f"GPT entries ki tadaad ghair-mamooli "
                         f"hai: {num}")
    if header["hdr_off"] > 0:
        base = header["entries_lba"] * sector
    else:
        base = max(header["entries_lba"] - 1, 1) * sector
    total = min(num * entry_size, _MAX_ENTRY_BYTES)
    blob = read_at(base, total)
    parts = []
    for i in range(num):
        off = i * entry_size
        if off + entry_size > len(blob):
            break
        entry = blob[off:off + entry_size]
        if entry[0:16] == b"\x00" * 16:
            continue  # khali entry
        first = struct.unpack_from("<Q", entry, 32)[0]
        last = struct.unpack_from("<Q", entry, 40)[0]
        raw = entry[56:128]
        name = raw.decode("utf-16-le", errors="ignore")
        name = name.split("\x00")[0].strip() or "(naam nahi)"
        parts.append({"name": name, "first": first, "last": last})
    if not parts:
        raise ValueError("GPT parha gaya lekin koi partition "
                         "entry nahi mili — dump na-mukammal lagta "
                         "hai.")
    return parts


def identify_file(head):
    """Pehle bytes se file ki pehchan — line ya None (unknown)."""
    if head[:4] == b"\x3a\xff\x26\xed":
        return ("Android sparse image hai (magic 0xED26FF3A) — "
                "ye raw dump nahi; GPT is ke andar unsparse hone "
                "ke baad milega.")
    if head[:8] == b"B\x00P\x00_\x00R\x00":
        return ("Unisoc PAC file hai (BP_R version header) — "
                "ye firmware package hai, raw dump nahi. PAC "
                "wale ops is par chalte hain.")
    if head[:4] == b"\x7fELF":
        return ("ELF binary hai — partition dump nahi lagta.")
    if head[:4] == b"PK\x03\x04":
        return ("ZIP package hai — pehle extract karo, phir "
                "andar ki image/dump par ye op chalao.")
    sample = head[:512]
    if sample:
        printable = sum(1 for b in sample
                        if b in (9, 10, 13) or 32 <= b < 127)
        if printable / len(sample) > 0.95:
            return ("Text file lagti hai — MTK scatter ho sakti "
                    "hai (scatter-based package ka hissa). "
                    "Scatter se partition table nahi banta; "
                    "asal dump .bin/.img file hoti hai.")
    return None


def _newest_input(ctx):
    files = [p for p in firmware_files.inbox_files(INBOX_DIR)
             if p.is_file()]
    if not files:
        return None
    try:
        files.sort(key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        pass
    if len(files) > 1:
        ctx.log(f"firmware-inbox me {len(files)} files hain — "
                f"sab se NAYI wali analyse ho rahi hai: "
                f"{files[-1].name}", "WARN")
    return files[-1]


def run(ctx) -> bool:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    src = _newest_input(ctx)
    if src is None:
        ctx.log("firmware-inbox me koi file nahi mili.", "ERROR")
        ctx.log(f"Guide: jo dump/image check karni hai wo is "
                f"folder me rakho: {INBOX_DIR} — phir ye op "
                "dobara chalao.", "WARN")
        return False

    try:
        size = src.stat().st_size
        fh = src.open("rb")
    except Exception as e:  # noqa: BLE001
        ctx.log(f"File khul nahi saki: {e}", "ERROR")
        return False

    with fh:
        def read_at(off, n):
            try:
                fh.seek(off)
                return fh.read(n)
            except Exception:  # noqa: BLE001
                return b""

        ctx.log(f"File: {src.name} ({size:,} bytes — "
                f"{_human(size)})", "INFO")
        ctx.progress(20, "GPT dhoondha ja raha hai...")

        head = read_at(0, 512)
        if len(head) >= 512 and head[510:512] == b"\x55\xaa" \
                and head[446 + 4] == 0xEE:
            ctx.log("Protective MBR: hai (type 0xEE) — GPT wali "
                    "disk image ki nishani.", "INFO")

        found = find_gpt(read_at)
        if found is None:
            ctx.log("GPT nahi mila — is file me 'EFI PART' wala "
                    "partition table maujood nahi hai.", "ERROR")
            ident = identify_file(read_at(0, 4096))
            if ident:
                ctx.log(f"Pehchan: {ident}", "INFO")
            else:
                magic = read_at(0, 16).hex(" ")
                ctx.log(f"Pehchan: pehle bytes se qism confirm "
                        f"nahi hui (magic: {magic}). File kharab, "
                        "encrypted, ya kisi khaas format me ho "
                        "sakti hai.", "WARN")
            return False

        sector, header = found
        try:
            parts = parse_entries(read_at, sector, header)
        except ValueError as e:
            ctx.log(f"GPT header mila lekin table parha nahi "
                    f"gaya: {e}", "ERROR")
            return False

        ctx.progress(60, "Partition table tayyar hai")
        ctx.log(f"GPT mila — sector size {sector}, "
                f"{len(parts)} partitions:", "OK")
        ctx.log(f"{'#':>3}  {'Partition':<20} {'First LBA':>12} "
                f"{'Last LBA':>12}  {'Size':>10}", "DATA")
        for i, p in enumerate(parts, 1):
            count = max(p["last"] - p["first"] + 1, 0)
            ctx.log(f"{i:>3}  {p['name']:<20} {p['first']:>12} "
                    f"{p['last']:>12}  {_human(count * sector):>10}",
                    "DATA")
        ctx.log("Note: ye sirf parhai (analysis) hai — file me "
                "koi tabdeeli nahi hui.", "INFO")
        ctx.progress(95, "Dump analysis mukammal")
        return True
