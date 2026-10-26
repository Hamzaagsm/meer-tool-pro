"""
qc_noauth_loader_slot.py — No-Auth Loader Slot (Technician).

SERVER-REQUIRED research §4.2: Vivo/Oppo ke "No Auth" firehose
loaders aur Xiaomi ke patched no-auth loaders per-model binaries
hain — MEER inhen bundle NAHI kar sakta (provenance unclear).
Lekin technician apna loader de sakta hai — ye op us ke liye
slot hai (SPD FDL/PAC wala usool hi):

  1. Apne no-auth loader (.elf/.mbn) `tools/loaders-noauth/` me
     rakho (folder ka naam brand/chip bata de to behtar — masalan
     `Xiaomi-SM8550/prog_firehose.elf`).
  2. Ye op har file ki magic se tasdeeq karta hai (ELF/MBN —
     Qualcomm firehose hona lazmi), phir use
     `tools/loaders/qualcomm/NoAuth-<Brand>/` me copy karke
     local index me `no_auth: True` ke saath darj karta hai.
  3. Us ke baad Xiaomi No-Auth EDL op aur EDL ops is loader ko
     no-auth ke tor par pehchan kar istemal kar sakte hain —
     pehle `printgpt` se tasdeeq hoti hai ke loader waqai
     baghair auth ke chalta hai.

Imaandari: slot me dalna = "ye loader no-auth hai" ka technician
ka daawa darj karna hai, tasdeeq nahi. Asal tasdeeq hamesha EDL
`printgpt` se hoti hai — loader na chale to op wahan ruk jayega.
Ghalat loader (na-MTK DA, na-ELF/MBN) slot me nahi ata.

Device ki zaroorat nahi (modes ()).
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from core import firmware_files, loader_library
from core.runner import TOOLS_DIR

OP = {
    "id": "qc_noauth_loader_slot",
    "category": "Qualcomm",
    "name": "No-Auth Loader Slot (Technician — Vivo/Oppo/Xiaomi)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "loaders-noauth"
CANDIDATE_EXTS = (".elf", ".mbn")


def _candidates(inbox: Path):
    """(files, zips) — inbox ke loose files + subfolders (recursive)."""
    files, zips = [], []
    if not inbox.is_dir():
        return files, zips
    for p in sorted(inbox.iterdir()):
        if p.is_file() and p.suffix.lower() == ".zip":
            zips.append(p)
        elif p.is_file() and p.suffix.lower() in CANDIDATE_EXTS:
            files.append((p, None))
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in CANDIDATE_EXTS:
                    files.append((f, p.name))
    return files, zips


def _brand_for(path: Path, folder_hint):
    """Brand: folder hint → filename token → 'NoAuth' (generic)."""
    if folder_hint:
        brand, _ = loader_library.parse_filename_tokens(folder_hint)
        if brand:
            return brand
        cleaned = "".join(c for c in folder_hint
                          if c.isalnum() or c in "-_ ")
        if cleaned.strip():
            return cleaned.strip()
    brand, _chip = loader_library.parse_filename_tokens(path.name)
    return brand or "NoAuth"


def _key_for(path: Path, folder_hint):
    """Chip key: filename → folder hint → stem."""
    _brand, chip = loader_library.parse_filename_tokens(path.name)
    if chip:
        return chip
    if folder_hint:
        _brand, chip = loader_library.parse_filename_tokens(folder_hint)
        if chip:
            return chip
    return path.stem


def run(ctx) -> bool:
    tools_dir = TOOLS_DIR
    inbox = INBOX_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    files, zips = _candidates(inbox)

    tmp_dirs = []
    for z in zips:
        try:
            dest = Path(tempfile.mkdtemp(prefix="noauth-import-"))
            tmp_dirs.append(dest)
            with zipfile.ZipFile(z) as zf:
                extracted = firmware_files.safe_extract_zip(zf, dest)
            got = 0
            for f in extracted:
                if f.is_file() and f.suffix.lower() in CANDIDATE_EXTS:
                    hint = f.parent.name if f.parent != dest else None
                    files.append((f, hint))
                    got += 1
            ctx.log(f"ZIP {z.name}: {got} loader file(s) mileen.", "INFO")
        except Exception as e:  # noqa: BLE001
            ctx.log(f"ZIP {z.name} khul nahi saka: {e}", "ERROR")

    if not files:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        ctx.log("loaders-noauth me koi .elf/.mbn loader nahi mila.",
                "ERROR")
        ctx.log(f"Guide: no-auth loader (Vivo/Oppo/Xiaomi ka "
                f"patched/engineering firehose) is folder me rakho: "
                f"{inbox} — folder ka naam brand/chip bata de to "
                f"behtar (masalan Xiaomi-SM8550/). Phir ye op "
                f"dobara chalao.", "WARN")
        return False

    root = loader_library.library_root(tools_dir)
    registered = already = skipped = 0
    for src, hint in files:
        try:
            sha = loader_library.sha256_of(src)
            size = src.stat().st_size
        except Exception as e:  # noqa: BLE001
            ctx.log(f"{src.name}: parha nahi ja saka ({e}) — skip.",
                    "ERROR")
            skipped += 1
            continue
        if loader_library.detect_side(src) != "qualcomm":
            ctx.log(f"{src.name}: magic bytes se Qualcomm firehose "
                    "pehchan NAHI ayi (ELF/MBN nahi) — slot me "
                    "nahi ayega. Ghalat khane me dalna khatarnak "
                    "hai.", "WARN")
            skipped += 1
            continue
        brand = _brand_for(src, hint)
        folder = root / "qualcomm" / f"NoAuth-{brand}"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / src.name
        if dest.is_file() and loader_library.sha256_of(dest) == sha:
            ctx.log(f"{src.name}: no-auth slot me pehle se hai "
                    f"({dest}) — duplicate skip.", "INFO")
            already += 1
            continue
        if dest.is_file():
            stem, ext = src.stem, src.suffix
            n = 1
            while dest.is_file():
                suffix = "__imported" if n == 1 else f"__imported{n}"
                dest = folder / f"{stem}{suffix}{ext}"
                n += 1
        shutil.copy2(src, dest)
        rel = str(dest.relative_to(tools_dir))
        loader_library.record_local_entry({
            "type": loader_library.FIREHOSE,
            "brand": f"NoAuth-{brand}",
            "key": _key_for(src, hint), "path": rel,
            "size": size, "sha256": sha,
            "source": "technician-supplied no-auth loader (slot)",
            "no_auth": True,
        }, tools_dir)
        ctx.log(f"{src.name}: no-auth loader darj → {rel} "
                f"(brand: NoAuth-{brand}, key: {_key_for(src, hint)})",
                "OK")
        registered += 1

    for d in tmp_dirs:
        shutil.rmtree(d, ignore_errors=True)

    total = len(loader_library.noauth_entries(tools_dir))
    ctx.log(f"No-Auth slot mukammal: {registered} naye, {already} "
            f"pehle se thay, {skipped} skip hue. Slot me kul "
            f"{total} no-auth loader(s) darj hain.", "INFO")
    ctx.log("Yaad rahe: slot me dalna tasdeeq nahi — asal tasdeeq "
            "EDL `printgpt` se hoti hai (Xiaomi No-Auth EDL op "
            "pehle wahi karta hai).", "INFO")
    return (registered + already) > 0
