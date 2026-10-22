"""
fw_ofp_extract.py — OFP / OZIP Extract (Oppo / Realme / OnePlus).

Oppo / Realme / OnePlus ki firmware .ofp (encrypted stock) ya
.ozip (encrypted OTA zip) shakal me aati hai. Ye op mashhoor
open-source bkerler/oppo_decrypt scripts se use decrypt karke
asal partition images nikalta hai — flashing phir maujooda
QC EDL / MTK ops se hoti hai.

Khalis PC-side file op hai: koi device nahi chahiye (modes ()).

Vendored scripts (engines/oppo_decrypt/) ke asal argv usool
jo is op ne apnaye hain — asal vendored files parh kar verify
kiye gaye (2026-10-22, parallel vendoring ke baad):
  - Asal vendored naam ofp_qc_decrypt.py / ofp_mtk_decrypt.py
    hain (kuch packages me yehi scripts ofp_qc_extract.py /
    ofp_mtk_extract.py naam se aate hain — op dono naam
    dhoondhta hai). Dono ka argv aik jaisa hai:
        python <script> <file.ofp> <output_dir>
    (ofp_qc_decrypt.py: `if len(sys.argv)<3` guard, Usage
     "./ofp_qc_extract.py [Filename.ofp] [Directory to extract
     files to]", filename=sys.argv[1], outdir=sys.argv[2],
     outdir na ho to khud banata hai. ofp_mtk_decrypt.py:
     `if len(sys.argv) != 3` guard, Usage "<filename>
     <directory to extract>", wahi argv[1]/argv[2]. Images
     seedha usi output folder me banti hain.)
  - ozipdecrypt.py is vendored package me MAUJOOD NAHI hai
    (package sirf OFP/OPS ke liye hai). Agar kabhi alag se
    vendor ho jaye to upstream convention ye hai:
        python ozipdecrypt.py <file.ozip>
    (SIRF argv[1]=input .ozip, koi output arg nahi — script
     decrypted .zip input ke PAAS / apne folder (cwd) me
     banata hai. Is liye ye op pehle snapshot leta hai, phir
     nayi bani .zip dhoondh kar use apne output folder me
     safe-extract karta hai. Agar vendored copy kabhi 2-arg
     wali ho — script ke andar argv[2] ka istemal nazar aye
     — to ye op khud 2-arg andaaz apna leta hai. Script na
     ho to .ozip par saaf guided FAIL milta hai.)
Script ka cwd hamesha us ka apna folder rakha jata hai taake
us ke relative hisse (keys waghera) sahi milen.

Imaandari:
  - Scripts ya Python na mile to guided FAIL — koi nakli
    extract nahi.
  - SUCCESS sirf tab jab output folder me kam az kam 1 asal
    image (.img/.bin) asal me maujood ho.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from core import engines, firmware_files
from core.runner import ENGINES_DIR, TOOLS_DIR

OP = {
    "id": "fw_ofp_extract",
    "category": "Utility",
    "name": "OFP / OZIP Extract (Oppo / Realme / OnePlus)",
    "engine": "oppo_decrypt",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "firmware-inbox"
OUT_BASE = TOOLS_DIR / "firmware-ofp"
ENGINE_DIR = ENGINES_DIR / "oppo_decrypt"
# Asal vendored naam *_decrypt.py hain; *_extract.py naam wali
# copies bhi qabool hain (package ke mukhtalif version).
QC_SCRIPTS = ("ofp_qc_extract.py", "ofp_qc_decrypt.py")
MTK_SCRIPTS = ("ofp_mtk_extract.py", "ofp_mtk_decrypt.py")
OZIP_SCRIPTS = ("ozipdecrypt.py", "ozip_decrypt.py")
IMAGE_SUFFIXES = (".img", ".bin")


def _find_script(names):
    for name in names:
        cand = ENGINE_DIR / name
        if cand.is_file():
            return cand
    return None


def _newest(candidates):
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return candidates[0]


def _images_in(folder: Path):
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*")
                  if p.is_file()
                  and p.suffix.lower() in IMAGE_SUFFIXES)


def _log_image_summary(ctx, images) -> int:
    total = 0
    for p in images:
        try:
            total += p.stat().st_size
        except Exception:  # noqa: BLE001
            pass
    ctx.log(f"{len(images)} image files mileen, kul size "
            f"{total:,} bytes:", "INFO")
    for p in images:
        try:
            size = p.stat().st_size
        except Exception:  # noqa: BLE001
            size = 0
        ctx.log(f"  {p.name}  ({size:,} bytes)", "DATA")
    return total


def _script_wants_two_args(script: Path) -> bool:
    """Vendored script ke source me argv[2] / dusra positional hai?"""
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return False
    return ("argv[2]" in text or "sys.argv[2]" in text
            or "<output" in text.lower() or "[output" in text.lower())


def _snapshot(folder: Path):
    """folder ke .img/.bin/.zip files ka {path: (mtime, size)} snapshot."""
    snap = {}
    if folder.is_dir():
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES + (".zip",):
                try:
                    st = p.stat()
                    snap[str(p)] = (st.st_mtime, st.st_size)
                except Exception:  # noqa: BLE001
                    pass
    return snap


def _new_files(before, folder: Path, suffixes):
    after = _snapshot(folder)
    out = []
    for key, val in after.items():
        if before.get(key) != val and Path(key).suffix.lower() in suffixes:
            out.append(Path(key))
    return sorted(out)


def _chipset_hint(name: str):
    low = name.lower()
    if any(tok in low for tok in ("snapdragon", "qualcomm", "sdm")) \
            or re.search(r"(?<![a-z])qc(?![a-z])", low):
        return "qc"
    if "mtk" in low or re.search(r"(?<![a-z])mt\d", low) \
            or re.search(r"(?<![a-z])mt(?![a-z])", low):
        return "mtk"
    return None


def _run_ofp(ctx, py, script: Path, src: Path, outdir: Path) -> int:
    ctx.log(f"Koshish: {script.name} se extract ho raha hai...", "INFO")
    return ctx.stream(py + [str(script), str(src), str(outdir)],
                      timeout=3600, cwd=str(script.parent))


def _finish(ctx, outdir: Path) -> bool:
    images = _images_in(outdir)
    if not images:
        ctx.log("Output folder me koi image (.img/.bin) nahi bani — "
                "extract nakam raha. Upar engine ke log me asal wajah "
                "dekho (ghalat chipset wala script, kharab file, ya "
                "script ki dependency — pycryptodome waghera — ki "
                "kami ho sakti hai).", "ERROR")
        return False
    _log_image_summary(ctx, images)
    ctx.log(f"Extract tayyar: {outdir}", "OK")
    ctx.log("Note: extract ke baad flashing maujooda QC EDL / MTK "
            "ops se hogi — OFP ke andar ki ye images hi asal "
            "firmware hain.", "INFO")
    ctx.progress(95, "OFP / OZIP extract mukammal")
    return True


def _run_ozip(ctx, py, script: Path, src: Path, outdir: Path) -> bool:
    # Decrypted zip script_dir (cwd) ya input ke paas banti hai —
    # dono jaghon ka pehle snapshot lo.
    watch_dirs = []
    for d in (script.parent, src.parent, outdir):
        if d not in watch_dirs:
            watch_dirs.append(d)
    before = {d: _snapshot(d) for d in watch_dirs}

    if _script_wants_two_args(script):
        ctx.log("Vendored ozipdecrypt.py 2-arg wali hai — output "
                "folder saath bheja ja raha hai.", "INFO")
        code = ctx.stream(py + [str(script), str(src), str(outdir)],
                          timeout=3600, cwd=str(script.parent))
    else:
        ctx.log("ozipdecrypt.py chal raha hai (sirf input arg — "
                "decrypted .zip input ke paas / script folder me "
                "banegi, wahan se utha li jayegi).", "INFO")
        code = ctx.stream(py + [str(script), str(src)],
                          timeout=3600, cwd=str(script.parent))
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"ozipdecrypt.py exit code {code} ke saath band hua.",
                "WARN")

    # 1) Agar images seedha outdir me aa gayin hon to wahi kaafi hai
    if _images_in(outdir):
        return _finish(ctx, outdir)

    # 2) Nayi bani decrypted .zip dhoondo aur safe-extract karo
    new_zips = []
    for d in watch_dirs:
        if d == outdir:
            continue
        new_zips.extend(_new_files(before[d], d, (".zip",)))
    # Naam se andaza wali jagah bhi check karo (mtime snapshot se reh gayi ho)
    guess = src.with_suffix(".zip")
    if guess.is_file() and guess not in new_zips:
        new_zips.append(guess)
    for zpath in new_zips:
        ctx.log(f"Decrypted ZIP mili: {zpath} — ab khul rahi hai.",
                "INFO")
        try:
            with zipfile.ZipFile(zpath) as zf:
                got = firmware_files.safe_extract_zip(zf, outdir)
            ctx.log(f"{len(got)} files decrypted ZIP se nikal aayin.",
                    "INFO")
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Decrypted ZIP khul nahi saki: {e}", "WARN")
        if _images_in(outdir):
            break

    # 3) Agar images kisi watched folder me seedha ban gayin hon to copy karo
    if not _images_in(outdir):
        for d in watch_dirs:
            if d == outdir:
                continue
            for img in _new_files(before[d], d, IMAGE_SUFFIXES):
                try:
                    target = outdir / img.name
                    if not target.exists():
                        shutil.copy2(img, target)
                        ctx.log(f"Image copy ho gayi: {img.name}", "INFO")
                except Exception:  # noqa: BLE001
                    pass
    return _finish(ctx, outdir)


def run(ctx) -> bool:
    # --- Engine scripts -------------------------------------------------
    qc = _find_script(QC_SCRIPTS)
    mtk = _find_script(MTK_SCRIPTS)
    ozip = _find_script(OZIP_SCRIPTS)
    if not ENGINE_DIR.is_dir() or not any((qc, mtk, ozip)):
        ctx.log("oppo_decrypt engine nahi mila — engines/oppo_decrypt/ "
                "folder maujood nahi ya us ke scripts (ofp_qc_decrypt.py / "
                "ofp_qc_extract.py, ofp_mtk_decrypt.py / "
                "ofp_mtk_extract.py, ozipdecrypt.py) ghayab hain.", "ERROR")
        ctx.log("Guide: engines package (MEERToolPro-Engines.zip) dobara "
                "download karke app ke saath extract karo taake "
                "engines/oppo_decrypt/ poora aa jaye. Engine ke baghair "
                "OFP/OZIP khul hi nahi sakta — ye nakami nahi, setup ki "
                "kami hai.", "WARN")
        return False

    # --- Python ---------------------------------------------------------
    py = engines.find_python()
    if py is None:
        for line in engines.python_missing_hint("oppo_decrypt"):
            ctx.log(line, "WARN")
        return False

    # --- Input ----------------------------------------------------------
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = [p for p in firmware_files.inbox_files(INBOX_DIR)
             if p.suffix.lower() in (".ofp", ".ozip")]
    if not files:
        ctx.log("firmware-inbox me koi .ofp ya .ozip file nahi mili.",
                "ERROR")
        ctx.log(f"Guide: Oppo / Realme / OnePlus ki firmware file "
                f"(.ofp ya .ozip) is folder me rakho: {INBOX_DIR} — "
                "phir ye op dobara chalao.", "WARN")
        return False
    src = _newest(files)
    if len(files) > 1:
        ctx.log(f"firmware-inbox me {len(files)} OFP/OZIP files mileen "
                f"— sab se NAYI wali istemal ho rahi hai: {src.name}",
                "WARN")
    else:
        ctx.log(f"File mili: {src}", "INFO")

    outdir = OUT_BASE / src.stem
    outdir.mkdir(parents=True, exist_ok=True)
    ctx.log(f"Output folder: {outdir}", "INFO")
    ctx.progress(10, "Decrypt / extract shuru ho raha hai...")

    # --- OZIP -----------------------------------------------------------
    if src.suffix.lower() == ".ozip":
        if ozip is None:
            ctx.log("ozipdecrypt.py engine folder me nahi mila — "
                    "vendored oppo_decrypt package me OZIP wala script "
                    "shamil hi nahi hai (ye package sirf OFP/OPS ke "
                    "liye hai).", "ERROR")
            ctx.log("Guide: ozipdecrypt.py (bkerler) ko alag se "
                    "engines/oppo_decrypt/ folder me rakho, tab hi "
                    ".ozip khulegi. Tab tak ye file nahi khul sakti "
                    "— ye nakami nahi, engine ki kami hai.", "WARN")
            return False
        return _run_ozip(ctx, py, ozip, src, outdir)

    # --- OFP ------------------------------------------------------------
    available = []
    if qc is not None:
        available.append(("qc", qc))
    if mtk is not None:
        available.append(("mtk", mtk))
    if not available:
        ctx.log("OFP ke dono scripts (ofp_qc_decrypt.py / "
                "ofp_mtk_decrypt.py) engine folder me nahi mile.", "ERROR")
        ctx.log("Guide: engines package dobara extract karo.", "WARN")
        return False

    hint = _chipset_hint(src.name)
    if hint:
        ctx.log(f"File ke naam se chipset ka hint mila: "
                f"{'Qualcomm' if hint == 'qc' else 'MediaTek'} — pehle "
                "usi ka script chalega.", "INFO")
        ordered = sorted(available, key=lambda t: 0 if t[0] == hint else 1)
    else:
        ctx.log("File ke naam me chipset ka hint nahi — pehle QC script, "
                "nakami par MTK script try hoga (dono koshishen log me "
                "nazar ayengi).", "INFO")
        ordered = sorted(available, key=lambda t: 0 if t[0] == "qc" else 1)

    for idx, (label, script) in enumerate(ordered):
        if idx > 0:
            ctx.log(f"Pichla script kaam nahi aaya — ab {script.name} "
                    "try ho raha hai...", "WARN")
        code = _run_ofp(ctx, py, script, src, outdir)
        if ctx.is_cancelled():
            return False
        images = _images_in(outdir)
        if images:
            if code != 0:
                ctx.log(f"{script.name} exit code {code} ke saath band "
                        "hua lekin images ban gayin hain — unhi ki "
                        "bunyad par natija diya ja raha hai.", "WARN")
            return _finish(ctx, outdir)
        ctx.log(f"{script.name} se koi image nahi bani (exit code "
                f"{code}).", "WARN")

    return _finish(ctx, outdir)
