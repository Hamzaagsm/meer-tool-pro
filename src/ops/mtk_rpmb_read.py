"""
mtk_rpmb_read.py — MTK RPMB Read (MTKClient `da rpmb r`).

RPMB (Replay Protected Memory Block) eMMC/UFS ka authenticated
hissa hai — TSM/Pandora class ke tools isay advertise karte
hain aur vendored MTKClient ke andar pura `da rpmb` toolset
(r/w/e + key auth) pehle se mojood tha; sirf op ghayab tha
(TSM-UAT-RESEARCH §5 G-A).

IMAANDARI / VERIFICATION: MTKClient ka DA handler rpmb ka
natija apne caller ko wapas NAHI deta (mtk_da_handler return
discard karta hai) — yani process ka exit code is amal ka
saboot ho hi nahi sakta. Is liye ye op command ko CAPTURE
karke chalata hai aur SUCCESS sirf tab deta hai jab:
  1. DA ke output me asal saboot wali line ("Done reading
     rpmb to ...") maujood ho, aur koi rpmb error line na ho;
  2. Output file asal me bani ho, size > 0 aur 256 ka
     multiple ho (range diya ho to bilkul sectors*256).

Read default/safe amal hai — is par danger gate nahi lagta.
Range GUI ke neeche wale PARAMS bar se ata hai (Start Sector /
Sectors); khali = poori RPMB (sector 0 se, device ki size tak).
"""

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from core import engines
from core.runner import BACKUPS_DIR

OP = {
    "id": "mtk_rpmb_read",
    "category": "MTK",
    "name": "RPMB Read (DA)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
    "params": ("start_sector", "sectors"),
}

# DA ke asal jawab ke nishan — mtkclient ke xflash/xmlflash
# extension ke info/error alfaaz (source me verify shuda).
DONE_MARKERS = {
    "r": "Done reading rpmb to",
    "w": "Done writing",
    "e": "Done erasing rpmb",
}
ERROR_MARKERS = (
    "Couldn't read rpmb",
    "Couldn't write rpmb",
    "Couldn't erase rpmb",
    "cannot run read rpmb cmd",
    "cannot run write rpmb cmd",
    "cannot run erase rpmb cmd",
    "Device is not in xflash/xml mode",
)


def parse_range(params):
    """GUI params -> (sector:int, sectors:int|None, err:str|None).

    Khali start_sector = 0; khali sectors = None (poora area).
    Hex (0x..) bhi qabool hai. Galat value par err wapas ata
    hai — andaze se kabhi aage nahi barhte.
    """
    params = params or {}

    def _num(key):
        raw = params.get(key)
        if raw is None:
            return None
        raw = str(raw).strip()
        if not raw:
            return None
        return int(raw, 0)

    try:
        sector = _num("start_sector")
        sectors = _num("sectors")
    except (TypeError, ValueError):
        return 0, None, ("PARAMS bar me Start Sector / Sectors me "
                         "sirf number (ya 0x.. wala hex) likhen — "
                         "galat value ki wajah se op roka gaya hai.")
    if sector is None:
        sector = 0
    if sector < 0:
        return 0, None, "Start Sector manfi (negative) nahi ho sakta."
    if sectors is not None and sectors <= 0:
        return 0, None, "Sectors ki tadaad 0 se bari honi chahiye."
    return sector, sectors, None


def da_output_ok(text, kind):
    """DA ke capture shuda jawab ki asal tasdeeq (pure function).

    True sirf tab jab us amal ki 'Done ...' wali line maujood
    ho AUR koi rpmb error line na ho. Exit code yahan istemal
    hi nahi hota — MTKClient use propagate nahi karta.
    """
    text = text or ""
    if any(marker in text for marker in ERROR_MARKERS):
        return False
    return DONE_MARKERS[kind] in text


def run_capture(ctx, cmd, cwd=None, timeout=600):
    """Subprocess chalao: har line LIVE LOG me bhi, aur poora
    output text wapas bhi — (exit_code, pura_output).

    ctx.stream sirf exit code deta hai; DA wale ops ko jawab
    ka MATAN (text) chahiye hota hai tasdeeq ke liye, is liye
    ye capture wala rasta hai. Cancel/timeout par -1/-2.
    """
    ctx.log(" ".join(str(c) for c in cmd), "CMD")
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=str(cwd) if cwd else None,
            **kwargs)
    except FileNotFoundError:
        ctx.log(f"Engine nahi mila: {cmd[0]}", "ERROR")
        return -1, ""
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Process shuru nahi ho saka: {e}", "ERROR")
        return -1, ""
    ctx._proc = proc
    lines = []
    timed_out = threading.Event()
    timer = None
    if timeout:
        def _kill():
            timed_out.set()
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        timer = threading.Timer(timeout, _kill)
        timer.daemon = True
        timer.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if ctx.is_cancelled():
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                ctx.log("User ne operation rok diya (STOP).", "WARN")
                break
            line = line.rstrip("\n")
            lines.append(line)
            if line.strip():
                ctx.log(line, "DATA")
        proc.wait()
    finally:
        if timer:
            timer.cancel()
        ctx._proc = None
    if timed_out.is_set():
        ctx.log(f"Timeout ({timeout}s) — engine ko rok diya gaya.",
                "ERROR")
        return -2, "\n".join(lines)
    if ctx.is_cancelled():
        return -1, "\n".join(lines)
    return (proc.returncode if proc.returncode is not None else -1,
            "\n".join(lines))


def engine_and_guard(ctx):
    """(cmd, cwd) ya (None, None) — MTK DA ops ka mushtaraka
    guard + engine resolution (doosre MTK ops wali hi shakal)."""
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone "
                "band karke Volume dono dabaye hue cable lagao "
                "(kuch models par test-point lagta hai).", "ERROR")
        return None, None
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke "
                "engines/mtkclient/ folder me rakho.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def range_args(sector, sectors):
    """mtkclient `da rpmb` ke --sector/--sectors args banao."""
    args = []
    if sector:
        args += ["--sector", str(sector)]
    if sectors is not None:
        args += ["--sectors", str(sectors)]
    return args


def run(ctx) -> bool:
    cmd, cwd = engine_and_guard(ctx)
    if cmd is None:
        return False
    sector, sectors, err = parse_range(getattr(ctx, "params", {}))
    if err:
        ctx.log(err, "ERROR")
        return False
    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo "
                "tools/loaders/mtk/ me rakha hai.", "INFO")
    if sectors is None:
        ctx.log(f"Range: sector {sector} se POORI RPMB (device "
                "ki apni size tak).", "INFO")
    else:
        ctx.log(f"Range: sector {sector} se {sectors} sectors "
                f"({sectors * 256} bytes).", "INFO")

    outdir = BACKUPS_DIR / ("rpmb-" +
                            datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False
    outfile = outdir / "rpmb.bin"

    ctx.progress(25, "RPMB parhi ja rahi hai (DA)...")
    code, text = run_capture(
        ctx, cmd + ["da", "rpmb", "r", str(outfile)] +
        range_args(sector, sectors) + extra,
        cwd=cwd, timeout=600)
    if ctx.is_cancelled():
        return False
    if code in (-1, -2):
        ctx.log("RPMB read mukammal nahi hua (engine ruk gaya).",
                "ERROR")
        return False
    if not da_output_ok(text, "r"):
        ctx.log("DA ke jawab me 'Done reading rpmb' wala saboot "
                "NAHI mila — is liye SUCCESS nahi diya ja raha. "
                "Aam wajahen: DA is device par xflash/xml mode me "
                "nahi gaya, ya RPMB is storage par dastiyab nahi. "
                "Exit code yahan saboot nahi hota, is liye nakli "
                "success ka sawal hi nahi.", "ERROR")
        return False
    if not outfile.is_file() or outfile.stat().st_size == 0:
        ctx.log("DA ne 'Done' kaha lekin rpmb.bin bani hi nahi / "
                "khali hai — SUCCESS nahi diya ja raha.", "ERROR")
        return False
    size = outfile.stat().st_size
    if size % 256 != 0:
        ctx.log(f"rpmb.bin ka size {size} bytes hai jo 256 ka "
                "multiple nahi — data mashkook hai, SUCCESS nahi.",
                "ERROR")
        return False
    if sectors is not None and size != sectors * 256:
        ctx.log(f"Size mismatch: manga {sectors * 256} bytes, "
                f"mila {size} bytes — SUCCESS nahi diya ja raha.",
                "ERROR")
        return False
    ctx.log(f"rpmb.bin: {size} bytes — {outfile}", "DATA")
    ctx.log("RPMB read mukammal — DA ke 'Done reading' jawab aur "
            "file ke size dono se verify shuda.", "OK")
    ctx.progress(95, "RPMB read mukammal")
    return True
