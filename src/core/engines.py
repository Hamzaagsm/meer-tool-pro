"""
engines.py — Engine resolution ka aik hi markazi rasta.

Tamam ops engines yahin se dhoondhte hain, taake har op ka behavior aik
jaisa ho aur GUI kabhi crash na ho — engine na mile to op khud log me
guided FAIL deta hai (ye module sirf "mila / nahi mila" batata hai).

Runtime layout (EXE ke saath, APP_ROOT ke barabar):
    engines/platform-tools/   adb.exe / fastboot.exe (Google, self-contained)
    engines/mtkclient/        MTKClient source (mtk.py) — Python program hai
    engines/edl/              bkerler edl source (edl.py) — Python program hai
    engines/python/           (ikhtiyari) bundled Python, user dal sakta hai
    tools/                    user ki cheezen: loaders, firmware, backups

Python engines (MTKClient / edl) chalane ke liye Python chahiye.
Resolution tartib (task ki hidayat ke mutabiq):
    1. engines/python/ me bundled python ho to wo
    2. source mode (frozen nahi) me sys.executable — wahi Python jo app
       chala raha hai
    3. PATH par `py` launcher (-3), phir `python`, phir `python3`
    Kuch na mile to None — op guided FAIL dega ke Python lazmi hai.

Purani jaghen bhi fallback rehti hain (tools/mtkclient/, PATH par `mtk`)
taake purana setup na tore.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from core.runner import APP_ROOT, BACKUPS_DIR, ENGINES_DIR, TOOLS_DIR  # noqa: F401

LOADER_EXTS = (".elf", ".mbn")


# --------------------------------------------------------------------------
# Python resolution
# --------------------------------------------------------------------------
def find_python():
    """Python chalane ki command prefix (list) ya None.

    Return list kisi .py file se pehle lagane ke liye hai,
    masalan ['python', 'C:/.../mtk.py', 'printgpt'].
    """
    bundled_dir = ENGINES_DIR / "python"
    for name in ("python.exe", "python"):
        cand = bundled_dir / name
        if cand.is_file():
            return [str(cand)]
    if not getattr(sys, "frozen", False):
        # Source mode: app khud Python se chal rahi hai — wahi istemal karo
        if sys.executable:
            return [sys.executable]
    py = shutil.which("py")
    if py:
        return [py, "-3"]
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if exe:
            return [exe]
    return None


def python_missing_hint(engine_label="ye engine"):
    """Guided FAIL ke liye tayyar lines (Roman Urdu) — op inhen log kare."""
    return [
        f"{engine_label} aik Python program hai aur is PC par Python "
        "nahi mila.",
        "Guide: Python install karo (https://www.python.org/downloads/) "
        "aur install ke doran 'Add python.exe to PATH' lazmi tick karo. "
        "Ya phir Python ki copy app ke engines/python/ folder me rakho.",
        "Us ke baad engine ki dependencies bhi chahiye hongi: command "
        "prompt me ye chalao — python -m pip install -r "
        "engines\\mtkclient\\requirements.txt (MTKClient ke liye) ya "
        "engines\\edl\\requirements.txt (EDL ke liye).",
    ]


# --------------------------------------------------------------------------
# Script engines (MTKClient / edl)
# --------------------------------------------------------------------------
def _script_engine(script_rel, vendored_rel, path_cmd, label):
    """(cmd_prefix, cwd, source_note) ya (None, None, wajah) wapas karo.

    cmd_prefix: command list jis ke aage subcommand jorna hai.
    cwd: engine ki apni directory (us ke relative files ke liye).
    """
    script = ENGINES_DIR / script_rel
    if script.is_file():
        py = find_python()
        if py is None:
            return None, None, "python_missing"
        return py + [str(script)], str(script.parent), \
            f"bundled engine ({script_rel})"
    vendored = TOOLS_DIR / vendored_rel
    if vendored.is_file():
        py = find_python()
        if py is None:
            return None, None, "python_missing"
        return py + [str(vendored)], str(vendored.parent), \
            f"tools/ wali copy ({vendored_rel})"
    exe = shutil.which(path_cmd)
    if exe:
        return [exe], None, f"PATH command ({path_cmd})"
    return None, None, f"{label} setup nahi hai — engines/ folder me " \
                       f"{script_rel} maujood nahi."


def find_mtkclient():
    """MTKClient: (cmd_prefix|None, cwd|None, note)."""
    return _script_engine("mtkclient/mtk.py", "mtkclient/mtk.py",
                          "mtk", "MTKClient")


def find_edl():
    """bkerler edl: (cmd_prefix|None, cwd|None, note)."""
    return _script_engine("edl/edl.py", "edl/edl.py", "edl", "EDL client")


# --------------------------------------------------------------------------
# spd_dump (Unisoc FDL sessions) — self-contained binary
# --------------------------------------------------------------------------
def find_spd_dump():
    """spd_dump: (exe_path|None, note).

    Tartib: engines/spd_dump/spd_dump.exe → tools/spd/spd_dump.exe →
    PATH. Source bundle (spd_dump.c) akela kaafi nahi — asal binary
    chahiye; na mile to op imaandar guided FAIL dega.
    """
    for base in (ENGINES_DIR / "spd_dump", TOOLS_DIR / "spd"):
        for name in ("spd_dump.exe", "spd_dump"):
            cand = base / name
            if cand.is_file():
                return str(cand), f"spd_dump mila: {cand}"
    exe = shutil.which("spd_dump")
    if exe:
        return exe, f"spd_dump mila (PATH): {exe}"
    return None, ("spd_dump binary nahi mila — engines/spd_dump/ me "
                  "sirf source (spd_dump.c) hai ya wo bhi nahi. "
                  "Official release ka spd_dump.exe app ke "
                  "engines/spd_dump/ ya tools/spd/ folder me rakho.")


# --------------------------------------------------------------------------
# platform-tools (adb / fastboot) — self-contained binaries
# --------------------------------------------------------------------------
def find_platform_tool(name):
    """adb/fastboot ka poora rasta (str) ya sirf naam (PATH bharosa).

    Tartib: engines/platform-tools/ → tools/platform-tools/ → PATH.
    """
    for base in (ENGINES_DIR / "platform-tools", TOOLS_DIR / "platform-tools"):
        for cand in (base / f"{name}.exe", base / name):
            if cand.is_file():
                return str(cand)
    return shutil.which(name) or name


# --------------------------------------------------------------------------
# User-supplied cheezen: MTK DA, Qualcomm loaders, firmware folders
# --------------------------------------------------------------------------
def user_mtk_da():
    """tools/loaders/mtk/ me agar AKEli DA file (.bin) ho to us ka Path.

    Ek se zyada hon to None (galat DA khud chunna khatarnak hai — op
    log me saaf kahega ke sirf aik rakho).
    """
    folder = TOOLS_DIR / "loaders" / "mtk"
    if not folder.is_dir():
        return None
    bins = sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() == ".bin")
    if len(bins) == 1:
        return bins[0]
    return None


def scan_qualcomm_loaders():
    """tools/loaders/qualcomm/ ke tamam firehose loaders (Path list)."""
    folder = TOOLS_DIR / "loaders" / "qualcomm"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and p.suffix.lower() in LOADER_EXTS)


def pick_qualcomm_loader(device=None):
    """(loader Path|None, note str) — HWID/chip hint matching jahan mumkin.

    0 loader → (None, khali-library wali wajah)
    1 loader → (wohi, '')
    zyada → device ke chip/detail ya loader ke naam me chip token
    (masalan 'msm8953', 'sm6225', 'sdm660') match ho to wo, warna
    (None, fehrist wali wajah) — galat loader khud nahi chunte.
    """
    loaders = scan_qualcomm_loaders()
    if not loaders:
        return None, ("Loader library khali hai — koi firehose loader "
                      "nahi mila.")
    if len(loaders) == 1:
        return loaders[0], ""
    haystacks = []
    if device is not None:
        haystacks = [getattr(device, "chip", "") or "",
                     getattr(device, "detail", "") or "",
                     getattr(device, "model", "") or ""]
    hint = " ".join(haystacks).lower()
    if hint.strip():
        for loader in loaders:
            name = loader.stem.lower()
            # naam ke tokens (underscore/dash se tore hue) hint me dhoondo
            tokens = [t for t in name.replace("-", "_").split("_")
                      if len(t) >= 4]
            if any(tok in hint for tok in tokens):
                return loader, (f"Device ki chip se match karke chuna: "
                                f"{loader.name}")
    names = ", ".join(p.name for p in loaders)
    return None, (f"{len(loaders)} loaders mile lekin device se match "
                  f"nahi ho saka: {names}. Sirf sahi loader ko "
                  "tools/loaders/qualcomm/<brand>/ me rakho, ya baqi ko "
                  "kuch dair ke liye wahan se hata do.")


def mtk_extra_args():
    """MTKClient ke liye ikhtiyari global args — user DA ho to --loader."""
    da = user_mtk_da()
    if da is not None:
        return ["--loader", str(da)]
    return []
