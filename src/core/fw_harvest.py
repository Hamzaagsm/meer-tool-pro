"""
fw_harvest.py — Firmware → Loader Auto-Harvest.

User factory firmware file de (.zip / .tgz / .tar.gz / .ofp /
.ozip / .pac — round-5 ke front-door extractors wali hi shaklen)
to ye module us ke andar se loader-class files nikaal kar
Loaders Library me darj karta hai:

  candidates : preloader*.bin · lk*.img/bin · DA *.bin ·
               firehose *.mbn/*.elf · PAC ke FDL1/FDL2
  tasdeeq    : firehose / MTK DA — loader_library ke MAGIC
               rules (detect_side) se; FDL — PAC ke item
               table ki FileID se (signed stock PAC hi is ki
               bunyad hai, core/spd_fdl wala hi usool); FDL
               loose file / preloader / lk — NAAM se (in ke
               liye byte-magic ka koi pakka rule maujood nahi;
               log me ye baat saaf likhi jati hai).
  darj       : loader_library ke import raste se hi — pehle
               hash se index match (verified canonical jagah),
               warna local index me provenance ke saath:
               source = "harvested from <firmware file>".
  khane      : mtk-da → loaders/mtk/, firehose →
               loaders/qualcomm/, fdl → loaders/unisoc/,
               preloader → loaders/preloader/, lk → loaders/lk/
               (aakhri do sirf record hain — auto-select inhe
               kabhi DA/firehose nahi samajhta).

Jo file candidate lage lekin tasdeeq na ho, wo register NAHI
hoti — wajah ke saath rejected fehrist me jati hai. Kuch na
mile to natija imaandar khaali hai (op guided FAIL deta hai).
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from core import firmware_files, loader_library
from core.runner import TOOLS_DIR

SUPPORTED_SUFFIXES = (".zip", ".tgz", ".tar.gz", ".ofp", ".ozip",
                      ".pac")
# Is size se bari file partition image hoti hai, loader nahi —
# PAC ke andar aisi entries extract hi nahi hotin (waqt/bandwidth
# ki hifazat); zip/tgz me wo scan se bahir rehti hain.
MAX_CANDIDATE_BYTES = 64 * 1024 * 1024

_SUBDIR = {loader_library.MTK: "mtk",
           loader_library.FIREHOSE: "qualcomm",
           loader_library.FDL: "unisoc",
           loader_library.PRELOADER: "preloader",
           loader_library.LK: "lk"}


def is_supported(path) -> bool:
    name = Path(path).name.lower()
    return any(name.endswith(s) for s in SUPPORTED_SUFFIXES)


def find_input(inbox):
    """Inbox ki sab se nayi supported firmware file ya None."""
    files = [p for p in firmware_files.inbox_files(inbox)
             if is_supported(p)]
    if not files:
        return None
    try:
        return max(files, key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return files[0]


# ---------------------------------------------------------------------------
# Naam se candidate pehchan
# ---------------------------------------------------------------------------
def _name_kind(path: Path):
    """Sirf NAAM se candidate ki qism ya None."""
    name = path.name.lower()
    stem = name
    for suf in (".bin", ".img", ".mbn", ".elf"):
        if stem.endswith(suf):
            stem = stem[:-len(suf)]
            break
    if "fdl1" in name or "fdl2" in name:
        return loader_library.FDL
    if name.startswith("preloader") and name.endswith(".bin"):
        return loader_library.PRELOADER
    if stem == "lk" or stem == "lk2" or stem.startswith("lk_") \
            or stem.startswith("lk-"):
        return loader_library.LK
    if name.endswith((".mbn", ".elf")) and (
            "firehose" in name or "prog_" in name
            or name.startswith("prog-") or "fhloader" in name
            or "fh_loader" in name):
        return loader_library.FIREHOSE
    if name.endswith(".bin") and (
            "download_agent" in name or "mtk_da" in name
            or "allinone_da" in name.replace("-", "_")
            or name.startswith("da_") or name.endswith("_da.bin")
            or name == "da.bin" or "da_swsec" in name
            or "auth_sv5" in name):
        return loader_library.MTK
    return None


def classify(path: Path, pac_file_id=None):
    """(kind, how) ya (None, wajah).

    how: "magic" (loader_library byte rules) · "pac-table"
    (PAC FileID) · "name" (sirf naam — log me saaf likha jata
    hai ke byte-magic tasdeeq in classes ke liye nahi hai).
    """
    fid = str(pac_file_id or "").strip().upper()
    if fid in ("FDL", "FDL1", "FDL2"):
        return loader_library.FDL, "pac-table"
    kind = _name_kind(path)
    if kind is None:
        return None, "naam se loader pehchan nahi (candidate nahi)"
    if kind == loader_library.FIREHOSE:
        if loader_library.detect_side(path) == "qualcomm":
            return kind, "magic"
        return None, ("naam firehose jaisa hai lekin magic bytes "
                      "se Qualcomm (ELF/MBN) pehchan NAHI ayi — "
                      "register nahi hoga")
    if kind == loader_library.MTK:
        if loader_library.detect_side(path) == "mtk":
            return kind, "magic"
        return None, ("naam DA jaisa hai lekin magic bytes se MTK "
                      "DA pehchan NAHI ayi — register nahi hoga")
    # FDL (loose) / preloader / lk — naam hi tasdeeq hai
    return kind, "name"


# ---------------------------------------------------------------------------
# Extraction — round-5 front door ke hi raste
# ---------------------------------------------------------------------------
def _extract_archive(ctx, src: Path, work: Path):
    """zip/tgz ko work me safe-extract; payload.bin mile to
    dumper se us ki images bhi nikaal kar fehrist me joro.
    Return: scan ke liye file paths [(Path, pac_file_id|None)]."""
    out = []
    low = src.name.lower()
    try:
        if low.endswith(".zip"):
            with zipfile.ZipFile(src) as zf:
                files = firmware_files.safe_extract_zip(zf, work)
        else:
            with tarfile.open(src, "r:*") as tf:
                files = firmware_files.safe_extract_tar(tf, work)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Archive khul nahi saka: {e}", "ERROR")
        return out
    out.extend((p, None) for p in files)
    ctx.log(f"Archive se {len(files)} files nikli — ab payload "
            "aur loader candidates dekhe ja rahe hain.", "INFO")

    payloads = [p for p in files
                if p.name.lower() == "payload.bin"]
    for payload in payloads:
        imgs = _dump_payload(ctx, payload, work / "payload-out")
        out.extend((p, None) for p in imgs)
    return out


def _dump_payload(ctx, payload: Path, outdir: Path):
    """payload-dumper-go se partition images (fw_payload_extract
    wala hi engine + argv). Binary na mile to khaali + note."""
    try:
        from ops.fw_payload_extract import _find_dumper
        binary = _find_dumper()
    except Exception:  # noqa: BLE001
        binary = None
    if binary is None:
        ctx.log("payload.bin mili lekin payload-dumper-go engine "
                "nahi mila — payload ke andar ke loaders (masalan "
                "lk.img) is dafa harvest NAHI honge. Engines "
                "package dobara extract karo to ye rasta khul "
                "jayega.", "WARN")
        return []
    outdir.mkdir(parents=True, exist_ok=True)
    ctx.log("payload.bin khul raha hai (payload-dumper-go)...",
            "INFO")
    code = ctx.stream([str(binary), "-o", str(outdir),
                       str(payload)], timeout=3600)
    if code != 0:
        ctx.log(f"payload-dumper-go exit code {code} ke saath "
                "band hua — payload images harvest nahi huin.",
                "WARN")
        return []
    imgs = sorted(p for p in outdir.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".img")
    ctx.log(f"payload.bin se {len(imgs)} partition images nikli.",
            "INFO")
    return imgs


def _extract_pac(ctx, src: Path, work: Path):
    """PAC item table se candidate entries nikaalo (spd_fdl ke
    hi helpers). Bari partition images skip hoti hain."""
    from core import spd_fdl
    try:
        entries = spd_fdl._pac_entries(src)
    except (ValueError, OSError) as e:
        ctx.log(f"PAC parha nahi ja saka: {e}", "ERROR")
        return []
    out = []
    skipped_big = 0
    for ent in entries:
        fname = ent["file_name"] or ent["file_id"] or "entry"
        kind_hint = _name_kind(Path(fname))
        fid = (ent["file_id"] or "").strip().upper()
        candidateish = kind_hint is not None or fid in (
            "FDL", "FDL1", "FDL2")
        if not candidateish and \
                ent["file_size"] > MAX_CANDIDATE_BYTES:
            skipped_big += 1
            continue
        if not candidateish and ent["file_size"] == 0:
            continue
        dest = work / "pac" / Path(fname).name
        try:
            spd_fdl._extract_entry(src, ent, dest)
        except (ValueError, OSError) as e:
            ctx.log(f"PAC entry {fname} nahi nikli: {e}", "WARN")
            continue
        out.append((dest, ent["file_id"]))
    if skipped_big:
        ctx.log(f"PAC ki {skipped_big} bari partition entries "
                "skip huin (loader nahi hoti).", "INFO")
    ctx.log(f"PAC se {len(out)} entries nikli — candidates "
            "dekhe ja rahe hain.", "INFO")
    return out


def _extract_ofp(ctx, src: Path, work: Path):
    """OFP/OZIP — ops.fw_ofp_extract ke vendored-script raste."""
    from core import engines
    from ops import fw_ofp_extract as ofp

    qc = ofp._find_script(ofp.QC_SCRIPTS)
    mtk = ofp._find_script(ofp.MTK_SCRIPTS)
    ozip = ofp._find_script(ofp.OZIP_SCRIPTS)
    if not any((qc, mtk, ozip)):
        ctx.log("oppo_decrypt engine/scripts nahi mile — OFP "
                "harvest ke liye engines package chahiye.",
                "ERROR")
        return []
    py = engines.find_python()
    if py is None:
        for line in engines.python_missing_hint("oppo_decrypt"):
            ctx.log(line, "WARN")
        return []
    outdir = work / "ofp-out"
    outdir.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".ozip":
        if ozip is None:
            ctx.log("ozipdecrypt.py vendored package me nahi — "
                    ".ozip harvest nahi ho sakti.", "ERROR")
            return []
        ofp._run_ozip(ctx, py, ozip, src, outdir)
    else:
        available = [(lbl, s) for lbl, s in
                     (("qc", qc), ("mtk", mtk)) if s is not None]
        if not available:
            ctx.log("OFP ke decrypt scripts nahi mile.", "ERROR")
            return []
        hint = ofp._chipset_hint(src.name)
        ordered = sorted(
            available,
            key=lambda t: 0 if t[0] == hint else 1) \
            if hint else available
        for _lbl, script in ordered:
            ofp._run_ofp(ctx, py, script, src, outdir)
            if ofp._images_in(outdir):
                break
    imgs = ofp._images_in(outdir)
    ctx.log(f"OFP/OZIP se {len(imgs)} images nikli — candidates "
            "dekhe ja rahe hain.", "INFO")
    return [(p, None) for p in imgs]


# ---------------------------------------------------------------------------
# Registration — loader_library ka import rasta hi
# ---------------------------------------------------------------------------
def _brand_for(src: Path, work: Path, firmware_name: str) -> str:
    brand, _chip = loader_library.parse_filename_tokens(firmware_name)
    if brand:
        return brand
    try:
        rel = src.relative_to(work)
        if len(rel.parts) > 1:
            brand, _chip = loader_library.parse_filename_tokens(
                rel.parts[0])
            if brand:
                return brand
            cleaned = "".join(c for c in rel.parts[0]
                              if c.isalnum() or c in "-_ ")
            if cleaned.strip():
                return cleaned.strip()
    except Exception:  # noqa: BLE001
        pass
    brand, _chip = loader_library.parse_filename_tokens(src.name)
    return brand or "Harvested"


def _key_for(src: Path, firmware_name: str) -> str:
    _b, chip = loader_library.parse_filename_tokens(src.name)
    if chip:
        return chip
    _b, chip = loader_library.parse_filename_tokens(firmware_name)
    return chip or src.stem


def _register(ctx, cand: Path, kind, how, brand, firmware_name,
              index, tools_dir):
    """(status, detail) — status: "verified" | "local" |
    "already" | "error". Import op wala hi bartao: kuch delete
    nahi, overwrite nahi (takrao par __imported suffix)."""
    tools = Path(tools_dir) if tools_dir is not None else TOOLS_DIR
    try:
        sha = loader_library.sha256_of(cand)
        size = cand.stat().st_size
    except Exception as e:  # noqa: BLE001
        return "error", f"parha nahi ja saka ({e})"

    known = loader_library.find_by_hash(index, sha)
    if known is not None and known.get("type") == kind:
        dest = loader_library.entry_abspath(known, tools_dir)
        if dest.is_file():
            return "already", known["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cand, dest)
        return "verified", known["path"]

    root = loader_library.library_root(tools_dir)
    folder = root / _SUBDIR[kind] / brand
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / cand.name
    if dest.is_file():
        if loader_library.sha256_of(dest) == sha:
            return "already", str(dest.relative_to(tools))
        stem, ext = cand.stem, cand.suffix
        n = 1
        while dest.is_file():
            suffix = "__imported" if n == 1 else f"__imported{n}"
            dest = folder / f"{stem}{suffix}{ext}"
            n += 1
    shutil.copy2(cand, dest)
    rel = str(dest.relative_to(tools))
    loader_library.record_local_entry({
        "type": kind, "brand": brand,
        "key": _key_for(cand, firmware_name), "path": rel,
        "size": size, "sha256": sha,
        "source": f"harvested from {firmware_name}",
    }, tools_dir)
    return "local", rel


# ---------------------------------------------------------------------------
# Asal harvest
# ---------------------------------------------------------------------------
def harvest(ctx, src, tools_dir=None):
    """Firmware file se loaders harvest karo.

    Return dict:
      {firmware, registered: [{name, kind, how, dest, status}],
       already: [name], rejected: [{name, reason}],
       candidates: int}
    Log tamam ctx par jata hai. Temp folder hamesha saaf hota
    hai; library ke ilawa kahin kuch nahi likha jata.
    """
    src = Path(src)
    result = {"firmware": src.name, "registered": [],
              "already": [], "rejected": [], "candidates": 0}
    work = Path(tempfile.mkdtemp(prefix="meer-harvest-"))
    try:
        low = src.name.lower()
        if low.endswith((".zip", ".tgz", ".tar.gz")):
            files = _extract_archive(ctx, src, work)
        elif low.endswith(".pac"):
            files = _extract_pac(ctx, src, work)
        elif low.endswith((".ofp", ".ozip")):
            files = _extract_ofp(ctx, src, work)
        else:
            ctx.log(f"Ye firmware shakal support nahi hoti: "
                    f"{src.name}", "ERROR")
            return result

        index = loader_library.load_index(tools_dir)
        brand = _brand_for(src, work, src.name)
        seen_reject_names = set()
        for cand, pac_id in files:
            if ctx.is_cancelled():
                break
            try:
                if cand.stat().st_size > MAX_CANDIDATE_BYTES:
                    continue
            except Exception:  # noqa: BLE001
                continue
            kind, how = classify(cand, pac_id)
            if kind is None:
                # Sirf wo rejects log karo jo candidate LAGTE
                # thay (warna har partition image ka shor hoga):
                # .mbn/.elf/.bin jinke naam loader-ish hain.
                probe_kind = _name_kind(cand)
                if probe_kind is not None and \
                        cand.name not in seen_reject_names:
                    seen_reject_names.add(cand.name)
                    result["rejected"].append(
                        {"name": cand.name, "reason": how})
                continue
            result["candidates"] += 1
            status, detail = _register(
                ctx, cand, kind, how, brand, src.name, index,
                tools_dir)
            if status == "already":
                result["already"].append(cand.name)
                ctx.log(f"{cand.name}: pehle se library me hai "
                        f"({detail}) — duplicate skip.", "INFO")
            elif status == "error":
                result["rejected"].append(
                    {"name": cand.name, "reason": detail})
            else:
                result["registered"].append(
                    {"name": cand.name, "kind": kind, "how": how,
                     "dest": detail, "status": status})
                tag = "✔ index-verified" if status == "verified" \
                    else "local index me darj"
                ctx.log(f"{cand.name}: {kind} ke tor par register "
                        f"→ {detail} ({tag}; tasdeeq: {how})",
                        "OK")
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def log_summary(ctx, result) -> None:
    """Aakhri fehrist — kya mila, kya register hua, kya reject."""
    reg = result["registered"]
    ctx.log(f"Harvest mukammal — firmware: {result['firmware']}",
            "INFO")
    ctx.log(f"Candidates mile: {result['candidates']} · register "
            f"hue: {len(reg)} · pehle se thay: "
            f"{len(result['already'])} · reject: "
            f"{len(result['rejected'])}", "INFO")
    for r in result["rejected"]:
        ctx.log(f"REJECT {r['name']}: {r['reason']}", "WARN")
    if reg:
        fdl = [r for r in reg if r["kind"] == loader_library.FDL]
        if fdl:
            ctx.log("FDL loaders Unisoc ke FDL khane "
                    "(loaders/unisoc/) me darj hue — SPD ops "
                    "inhi ko istemal kar sakenge.", "INFO")
        named = [r for r in reg if r["how"] == "name"]
        if named:
            ctx.log("Note: preloader/lk (aur loose FDL) ki "
                    "tasdeeq NAAM se hai — in ke liye byte-magic "
                    "ka pakka rule maujood nahi; ye alag khano "
                    "me sirf record hain, auto-select inhe DA/"
                    "firehose nahi samajhta.", "WARN")
