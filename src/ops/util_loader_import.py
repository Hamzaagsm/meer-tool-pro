"""
util_loader_import.py — Loaders Library Import.

User apne loaders (Loaders pack ke ilawa wale — masalan Hovatek se
download kiye hue per-model DA, ya kisi folder me pare purane
firehose) is op se library me andar karta hai:

  1. Files / folder / .zip ko `tools/loaders-inbox/` me rakho.
  2. Ye op har .bin/.elf/.mbn ko parakh-ta hai:
     - SHA-256 index se mile to **verified** — file apni asal
       index wali jagah (tools/loaders/mtk|qualcomm/<Brand>/) par
       jati hai.
     - Index me na ho to magic bytes se side tay hoti hai (MTK DA
       header / ELF / MBN) aur file brand folder me ja kar
       `tools/loaders-local-index.json` me darj ho jati hai —
       taake auto-select use bhi dhoondh sake.
     - Magic pehchan na aye to file import NAHI hoti (andaza laga
       kar galat khane me dalna khatarnak hai).
  3. Import kabhi kuch DELETE nahi karta aur mojooda file ko
     overwrite bhi nahi karta — naam takraye to nayi file
     `__imported` suffix ke saath jati hai.

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
    "id": "util_loader_import",
    "category": "Utility",
    "name": "Loaders Library Import (Folder / ZIP → Library)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "loaders-inbox"
CANDIDATE_EXTS = (".bin", ".elf", ".mbn")


def _candidates(inbox: Path):
    """(files, zips) — inbox ke loose files, subfolders (recursive)
    aur .zip archives ki fehrist. Har file ke saath us ka 'folder
    hint' (jis subfolder se ayi) bhi wapas ata hai."""
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


def _brand_for(path: Path, folder_hint, entries_index):
    """Brand folder tay karo: folder hint → filename token → 'Imported'."""
    if folder_hint:
        brand, _ = loader_library.parse_filename_tokens(folder_hint)
        if brand:
            return brand
        cleaned = "".join(c for c in folder_hint if c.isalnum() or c in "-_ ")
        if cleaned.strip():
            return cleaned.strip()
    brand, _chip = loader_library.parse_filename_tokens(path.name)
    return brand or "Imported"


def _key_for(path: Path):
    _brand, chip = loader_library.parse_filename_tokens(path.name)
    return chip or path.stem


def run(ctx) -> bool:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files, zips = _candidates(INBOX_DIR)

    tmp_dirs = []
    for z in zips:
        try:
            dest = Path(tempfile.mkdtemp(prefix="loader-import-"))
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
        ctx.log("loaders-inbox me koi loader file / folder / zip "
                "nahi mila.", "ERROR")
        ctx.log(f"Guide: jo loaders import karne hain (folder, loose "
                f".bin/.elf/.mbn files, ya .zip) is folder me rakho: "
                f"{INBOX_DIR} — phir ye op dobara chalao.", "WARN")
        return False

    index = loader_library.load_index()
    root = loader_library.library_root()
    imported = verified = already = local_new = skipped = 0

    for src, hint in files:
        try:
            sha = loader_library.sha256_of(src)
            size = src.stat().st_size
        except Exception as e:  # noqa: BLE001
            ctx.log(f"{src.name}: parha nahi ja saka ({e}) — skip.",
                    "ERROR")
            skipped += 1
            continue

        known = loader_library.find_by_hash(index, sha)
        if known is not None:
            dest = loader_library.entry_abspath(known)
            if dest.is_file():
                ctx.log(f"{src.name}: pehle se install hai "
                        f"({known['path']}) — duplicate skip.", "INFO")
                already += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            ctx.log(f"{src.name}: ✔ index-verified import → "
                    f"{known['path']}", "OK")
            imported += 1
            verified += 1
            continue

        side = loader_library.detect_side(src)
        if side is None:
            ctx.log(f"{src.name}: magic bytes se pehchan nahi ayi "
                    "(na MTK DA header, na ELF/MBN) — import NAHI "
                    "hua. Ghalat khane me dalna khatarnak hai.",
                    "WARN")
            skipped += 1
            continue
        brand = _brand_for(src, hint, index)
        sub = "mtk" if side == "mtk" else "qualcomm"
        folder = root / sub / brand
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / src.name
        if dest.is_file():
            if loader_library.sha256_of(dest) == sha:
                ctx.log(f"{src.name}: library me pehle se hai "
                        f"({dest}) — duplicate skip.", "INFO")
                already += 1
                continue
            stem, ext = src.stem, src.suffix
            n = 1
            while dest.is_file():
                suffix = "__imported" if n == 1 else f"__imported{n}"
                dest = folder / f"{stem}{suffix}{ext}"
                n += 1
        shutil.copy2(src, dest)
        rel = str(dest.relative_to(TOOLS_DIR))
        loader_library.record_local_entry({
            "type": loader_library.MTK if side == "mtk"
                    else loader_library.FIREHOSE,
            "brand": brand, "key": _key_for(src), "path": rel,
            "size": size, "sha256": sha,
        })
        ctx.log(f"{src.name}: naya loader darj → {rel} "
                f"(brand: {brand}, key: {_key_for(src)}; local index "
                "me record ho gaya)", "OK")
        imported += 1
        local_new += 1

    for d in tmp_dirs:
        shutil.rmtree(d, ignore_errors=True)

    st = loader_library.library_state()
    ctx.log(f"Import mukammal: {imported} naye "
            f"(index-verified {verified}, local-darj {local_new}), "
            f"{already} pehle se thay, {skipped} skip hue. Library "
            f"me ab {st['installed_count']}/{st['index_count']} "
            "loaders install hain.", "INFO")
    return (imported + already) > 0
