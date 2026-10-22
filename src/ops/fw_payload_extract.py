"""
fw_payload_extract.py — payload.bin Extract (OTA → Partition Images).

Android OTA packages ke andar payload.bin hota hai jis me tamam
partition images (boot, system, vendor waghera) packed hoti hain.
Ye op mashhoor open-source payload-dumper-go se use khol kar
asal .img files nikalta hai — phir wo images maujooda flash ops
se istemal ho sakti hain.

Khalis PC-side file op hai: koi device nahi chahiye (modes ()).

Input do shakal me qabool hai:
  1. seedhi payload.bin firmware-inbox me
  2. OTA .zip firmware-inbox me jis ke andar payload.bin ho
     (pehle sirf payload.bin member temp folder me safe-extract
     hota hai — poori zip nahi khulti)

Binary: engines/payload_dumper/ ke andar payload-dumper-go
(.exe ya bina extension wala executable naam).

Imaandari:
  - Binary ya input na mile to guided FAIL.
  - SUCCESS sirf tab jab output me kam az kam 1 asal .img
    file bani ho — dumper ke exit code par andha bharosa nahi.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from core import firmware_files
from core.runner import ENGINES_DIR, TOOLS_DIR

OP = {
    "id": "fw_payload_extract",
    "category": "Utility",
    "name": "payload.bin Extract (OTA → Partition Images)",
    "engine": "payload-dumper-go",
    "modes": (),
    "server_required": False,
}

INBOX_DIR = TOOLS_DIR / "firmware-inbox"
OUT_BASE = TOOLS_DIR / "firmware-payload"
DUMPER_DIR = ENGINES_DIR / "payload_dumper"


def _find_dumper():
    """payload-dumper-go binary ka Path ya None.

    Tartib: *.exe glob pehle, phir bina extension wala
    payload-dumper-go* naam wala executable.
    """
    if not DUMPER_DIR.is_dir():
        return None
    exes = sorted(p for p in DUMPER_DIR.glob("*.exe") if p.is_file())
    if exes:
        return exes[0]
    named = sorted(
        (p for p in DUMPER_DIR.glob("payload-dumper-go*")
         if p.is_file() and p.suffix.lower() != ".exe"),
        key=lambda p: p.name.lower(),
    )
    if named:
        return named[0]
    # Aakhri koshish: koi bhi file jiske naam me payload + dumper ho
    any_named = sorted(
        (p for p in DUMPER_DIR.iterdir()
         if p.is_file() and "payload" in p.name.lower()
         and "dumper" in p.name.lower()),
        key=lambda p: p.name.lower(),
    )
    return any_named[0] if any_named else None


def _newest(candidates):
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return candidates[0]


def _find_input(ctx):
    """(payload_path, stem, temp_dir_or_None) ya (None, None, None).

    Seedhi payload.bin ko tarjeeh; warna payload-zip me se
    payload.bin temp folder me nikaal kar.
    """
    files = firmware_files.inbox_files(INBOX_DIR)
    direct = [p for p in files if p.name.lower() == "payload.bin"]
    if direct:
        src = _newest(direct)
        ctx.log(f"payload.bin mili: {src}", "INFO")
        return src, "payload", None

    zips = [p for p in files if p.suffix.lower() == ".zip"]
    payload_zips = []
    for z in zips:
        if firmware_files.detect_kind(z) == "payload-zip":
            payload_zips.append(z)
    if not payload_zips:
        return None, None, None

    src_zip = _newest(payload_zips)
    if len(payload_zips) > 1:
        ctx.log(f"firmware-inbox me {len(payload_zips)} payload-ZIP "
                f"mileen — sab se NAYI wali istemal ho rahi hai: "
                f"{src_zip.name}", "WARN")
    else:
        ctx.log(f"OTA ZIP mili: {src_zip}", "INFO")

    tmp = Path(tempfile.mkdtemp(prefix="meer-payload-"))
    try:
        with zipfile.ZipFile(src_zip) as zf:
            member = None
            for name in zf.namelist():
                low = name.replace("\\", "/").lower()
                if low == "payload.bin" or low.endswith("/payload.bin"):
                    member = name
                    break
            if member is None:
                ctx.log("ZIP ke andar payload.bin nahi mila — "
                        "detect aur asal list me farq hai, file dobara "
                        "check karo.", "ERROR")
                return None, None, None
            # Sirf payload.bin member — safe tareeqe se
            target = tmp / "payload.bin"
            target.write_bytes(zf.read(member))
        ctx.log(f"payload.bin ZIP se temp folder me nikal aayi: "
                f"{target} ({target.stat().st_size:,} bytes)", "INFO")
        return target, src_zip.stem, tmp
    except Exception as e:  # noqa: BLE001
        ctx.log(f"OTA ZIP se payload.bin nahi nikal saki: {e}", "ERROR")
        return None, None, None


def run(ctx) -> bool:
    # --- Binary ---------------------------------------------------------
    binary = _find_dumper()
    if binary is None:
        ctx.log("payload-dumper-go binary nahi mila — "
                "engines/payload_dumper/ folder maujood nahi ya us "
                "me koi executable nahi hai.", "ERROR")
        ctx.log("Guide: engines package (MEERToolPro-Engines.zip) "
                "dobara download karke app ke saath extract karo "
                "taake engines/payload_dumper/ me payload-dumper-go "
                "aa jaye. Binary ke baghair payload.bin khul hi "
                "nahi sakta — ye nakami nahi, setup ki kami hai.",
                "WARN")
        return False
    ctx.log(f"payload-dumper-go mila: {binary}", "INFO")

    # --- Input ----------------------------------------------------------
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    payload, stem, tmp = _find_input(ctx)
    if payload is None:
        ctx.log("firmware-inbox me payload.bin ya payload wali OTA "
                "ZIP nahi mili.", "ERROR")
        ctx.log(f"Guide: OTA zip ya seedhi payload.bin file is "
                f"folder me rakho: {INBOX_DIR} — phir ye op dobara "
                "chalao. Dhyaan do: ye FULL OTA hona chahiye, "
                "incremental OTA se saari partition images nahi "
                "nikalti.", "WARN")
        return False

    outdir = OUT_BASE / (stem or "payload")
    outdir.mkdir(parents=True, exist_ok=True)
    ctx.log(f"Output folder: {outdir}", "INFO")
    ctx.progress(15, "payload.bin khul raha hai — bara OTA ho to "
                      "waqt lag sakta hai...")

    # payload-dumper-go CLI: payload-dumper-go -o <outdir> <payload.bin>
    code = ctx.stream([str(binary), "-o", str(outdir), str(payload)],
                      timeout=3600)
    if ctx.is_cancelled():
        return False
    if tmp is not None:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
    if code != 0:
        ctx.log(f"payload-dumper-go exit code {code} ke saath band "
                "hua — upar ke log me asal wajah hai.", "WARN")

    images = sorted(p for p in outdir.rglob("*")
                    if p.is_file() and p.suffix.lower() == ".img") \
        if outdir.is_dir() else []
    if not images:
        ctx.log("Output folder me koi .img file nahi bani — extract "
                "nakam raha.", "ERROR")
        ctx.log("Aam wajahen: file shayad FULL OTA nahi hai "
                "(incremental OTA hai), payload.bin kharab / adhoori "
                "hai, ya dumper ne is format ko mana kar diya — "
                "dumper ki asal output upar log me hai.", "WARN")
        return False

    total = 0
    ctx.log(f"{len(images)} partition images tayyar hain:", "OK")
    for p in images:
        try:
            size = p.stat().st_size
        except Exception:  # noqa: BLE001
            size = 0
        total += size
        ctx.log(f"  {p.name}  ({size:,} bytes)", "DATA")
    ctx.log(f"Kul size: {total:,} bytes — folder: {outdir}", "INFO")
    ctx.log("Note: ye images (boot / system / vendor waghera) ab "
            "maujooda flash ops se istemal ho sakti hain — flash se "
            "pehle model ki tasdeeq aur backup lazmi hai.", "INFO")
    ctx.progress(95, "payload.bin extract mukammal")
    return True
