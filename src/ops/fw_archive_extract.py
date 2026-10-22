"""
fw_archive_extract.py — Firmware Archive Kholo (ZIP/TGZ → Scatter Folder).

Customer aksar firmware aik bare ZIP / TGZ archive me deta hai
jis ke andar scatter folder chhupa hota hai. Ye op us archive ko
tools/firmware-inbox/ se utha kar mehfooz tareeqe se
tools/firmware/<stem>/ me kholta hai aur scatter file dhoondh
kar batata hai — taake MTK Flash (scatter) op ya Platforms
workbench usi scatter ko istemal kar sake.

Khalis PC-side file op hai: koi device nahi chahiye (modes ()).

Imaandari:
  - Archive ke andar scatter na ho to saaf FAIL — OTA zip ya
    doosri qisam ki file ko scatter firmware keh kar aage nahi
    bhejte.
  - payload.bin wali zip ke liye alag op hai — yahan FAIL ke
    saath usi ki taraf rehnumai di jati hai.
  - Extract hamesha zip-slip / tar-slip protection ke saath
    hota hai (core.firmware_files.safe_extract_*).
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from core import firmware_files
from core.runner import TOOLS_DIR

OP = {
    "id": "fw_archive_extract",
    "category": "Utility",
    "name": "Firmware Archive Kholo (ZIP/TGZ → Scatter Folder)",
    "engine": "files",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "firmware-inbox"
OUT_BASE = TOOLS_DIR / "firmware"
ARCHIVE_SUFFIXES = (".zip", ".tgz", ".tar.gz")


def _is_archive(p: Path) -> bool:
    name = p.name.lower()
    return name.endswith(ARCHIVE_SUFFIXES)


def _newest(candidates):
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return candidates[0]


def run(ctx) -> bool:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = [p for p in firmware_files.inbox_files(INBOX_DIR)
             if _is_archive(p)]
    if not files:
        ctx.log("firmware-inbox me koi .zip / .tgz / .tar.gz file "
                "nahi mili.", "ERROR")
        ctx.log(f"Guide: customer ki firmware archive file is folder "
                f"me rakho: {INBOX_DIR} — phir ye op dobara chalao. "
                "Archive ke andar MTK scatter (.txt) wala poora "
                "firmware folder hona chahiye.", "WARN")
        return False

    archive = _newest(files)
    if len(files) > 1:
        ctx.log(f"firmware-inbox me {len(files)} archives mile — sab "
                f"se NAYI wali istemal ho rahi hai: {archive.name} "
                "(baqi ko wahan se hata do agar wo nahi chahiye).",
                "WARN")
    else:
        ctx.log(f"Archive mila: {archive}", "INFO")

    kind = firmware_files.detect_kind(archive)
    ctx.log(f"Archive ki qism: {kind}", "INFO")

    if kind == "payload-zip":
        ctx.log("Is ZIP ke andar payload.bin hai — ye OTA firmware "
                "hai, scatter wali nahi.", "ERROR")
        ctx.log("Guide: is file ke liye 'payload.bin Extract (OTA → "
                "Partition Images)' wala op chalao — wahi is ZIP se "
                "partition images nikale ga.", "WARN")
        return False
    if kind in ("zip-other", "tgz-other"):
        ctx.log("Archive khol kar dekha — andar koi scatter (.txt) "
                "file nahi mili.", "ERROR")
        ctx.log("Ye shayad OTA package hai ya doosri qisam ki file "
                "hai — scatter firmware nahi hai. Customer se us "
                "model ka poora stock firmware (scatter wala) mango, "
                "ya agar andar payload.bin hai to payload wala op "
                "istemal karo.", "WARN")
        return False
    if kind not in ("zip-scatter", "tgz-scatter"):
        ctx.log(f"Archive parha nahi ja saka ya pehchana nahi gaya "
                f"(qism: {kind}). File kharab / adhoori download ho "
                "sakti hai.", "ERROR")
        return False

    # Stem: .tar.gz ka poora suffix hatao, warna sirf last suffix
    stem = archive.name
    low = stem.lower()
    if low.endswith(".tar.gz"):
        stem = stem[:-7]
    elif low.endswith(".tgz"):
        stem = stem[:-4]
    elif low.endswith(".zip"):
        stem = stem[:-4]
    outdir = OUT_BASE / stem
    outdir.mkdir(parents=True, exist_ok=True)
    ctx.log(f"Extract ki manzil: {outdir}", "INFO")
    ctx.progress(20, "Archive khul raha hai...")

    extracted = []
    try:
        if kind == "zip-scatter":
            with zipfile.ZipFile(archive) as zf:
                extracted = firmware_files.safe_extract_zip(zf, outdir)
        else:
            with tarfile.open(archive, "r:*") as tf:
                extracted = firmware_files.safe_extract_tar(tf, outdir)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Archive extract nahi ho saka: {e}", "ERROR")
        return False

    if ctx.is_cancelled():
        return False

    ctx.log(f"{len(extracted)} files extract ho gayin.", "INFO")
    ctx.progress(75, "Scatter file dhoondhi ja rahi hai...")

    scatter = firmware_files.find_scatter(outdir)
    if scatter is None:
        ctx.log("Extract ho gaya lekin is folder me scatter (.txt) "
                "file nahi mili — archive andar se mukhtalif nikla.",
                "ERROR")
        ctx.log(f"Extracted folder: {outdir} — andar khud dekh lo; "
                "scatter na ho to ye firmware is tareeqe se flash "
                "nahi hoga.", "WARN")
        return False

    ctx.log(f"Scatter file mili: {scatter}", "OK")
    ctx.log("Note: ab MTK Flash (scatter) op ya Platforms workbench "
            "se ye scatter istemal hoga — flash se pehle tasdeeq "
            "karo ke firmware bilkul isi model ke liye hai, aur "
            "Backup op se pehle backup le lo.", "INFO")
    ctx.progress(95, "Archive khul gaya — scatter tayyar hai")
    return True
