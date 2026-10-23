"""
mtk_identify_backup.py — Identify + Auto-Backup (pehla qadam).

PAID-TOOLS-TEARDOWN ka sab se pehla item — CM2 / Avenger wali
discipline: **Identify = Backup**. Koi bhi destructive MTK op
(FRP erase, format, flash) chalane se PEHLE ye op chalao:
  1. Identify: MTKClient `printgpt` se asal GPT parhi jati hai
     (core/platforms_mtk wala hi capture + parse tareeqa).
  2. Usi GPT me jo SAFETY partitions mojood hain — preloader,
     nvram, nvdata, protect1, protect2 — wo foran backup ho
     jati hain: backups/identify-<model>-<waqt>/ me, saath
     summary.txt (model, GPT source, files + sizes, skip hue
     partitions).
Jo partition GPT me NAHI hai wo skip hoti hai (log line ke
saath) — andaze se kuch nahi parha jata. Identify fail ho to
op FAIL hai aur kisi backup ka dawa NAHI kiya jata.
"""

import subprocess
import sys
from datetime import datetime

from core import engines, platforms_mtk
from core.runner import BACKUPS_DIR
from ops.mtk_info import _CRASH_CODES, _CRASH_LINE

OP = {
    "id": "mtk_identify_backup",
    "category": "MTK",
    "name": "Identify + Auto-Backup (Pehla Qadam)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}

# Safety set — tartib yahi rahegi; GPT me jo mile wahi parha jayega
SAFETY_SET = ("preloader", "nvram", "nvdata", "protect1", "protect2")


def _engine(ctx):
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


def _guard(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone "
                "band karke Volume dono dabaye hue cable lagao.",
                "ERROR")
        return False
    return True


def _model_slug(dev) -> str:
    """Folder naam ke liye model code — saaf haroof/numbers hi."""
    raw = str(getattr(dev, "model", "") or "").strip()
    slug = "".join(c if (c.isalnum() or c in "-_") else "-"
                   for c in raw).strip("-")
    return slug or "unknown"


def _identify(ctx, cmd, cwd, extra):
    """printgpt capture + parse — partitions list ya None.

    Nakami ki har surat yahin log ho jati hai; caller sirf
    None dekh kar rukta hai (partial-backup ka dawa kabhi
    nahi hoga)."""
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            cmd + ["printgpt"] + extra, capture_output=True,
            text=True, timeout=300,
            cwd=str(cwd) if cwd else None, **kwargs)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"printgpt chal nahi saka: {e}", "ERROR")
        return None
    text = (out.stdout or "") + "\n" + (out.stderr or "")
    for line in text.splitlines():
        if line.strip():
            ctx.log(line, "DATA")
    if out.returncode in _CRASH_CODES:
        ctx.log(_CRASH_LINE, "ERROR")
        return None
    if out.returncode != 0:
        ctx.log(f"Identify fail — MTKClient exit code "
                f"{out.returncode} ke saath band hua. Aam "
                "wajahen: device BROM me nahi aya, DA/auth is "
                "chipset ke liye server-required hai, ya USB "
                "driver ka masla hai.", "ERROR")
        return None
    parts = platforms_mtk.parse_gpt(text)
    if not parts:
        ctx.log("printgpt chala lekin GPT parse nahi hua — "
                "identify nakam hai. Is halat me backup ka dawa "
                "nahi kiya jayega.", "ERROR")
        return None
    ctx.log(f"Identify ho gaya: GPT me {len(parts)} partitions "
            "mile.", "OK")
    return parts


def run(ctx) -> bool:
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False

    ctx.log("Ye op har MTK phone par PEHLA qadam hona chahiye — "
            "koi bhi destructive op (FRP erase / format / flash) "
            "chalane se pehle ye safety backup bana lo. Kuch "
            "bhool ho jaye to wapas ana isi se mumkin hota hai.",
            "INFO")
    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo "
                "tools/loaders/mtk/ me rakha hai.", "INFO")

    # Step 1: Identify (printgpt) — fail = seedha FAIL
    ctx.progress(15, "Identify ho raha hai (GPT parhi ja rahi hai)...")
    ctx.log("Step 1/2: Identify — GPT parhna (printgpt)", "INFO")
    parts = _identify(ctx, cmd, cwd, extra)
    if ctx.is_cancelled():
        return False
    if parts is None:
        return False

    # Step 2: GPT me mojood safety partitions ka backup
    dev = ctx.device
    in_gpt = {p["name"].strip().lower(): p["name"].strip()
              for p in parts}
    present = [in_gpt[k] for k in SAFETY_SET if k in in_gpt]
    skipped = [k for k in SAFETY_SET if k not in in_gpt]
    for name in skipped:
        ctx.log(f"Skip: {name} — is phone ke GPT me ye partition "
                "nahi hai.", "INFO")
    if not present:
        ctx.log("Safety set (preloader/nvram/nvdata/protect1/"
                "protect2) ka koi partition GPT me nahi mila — "
                "backup ban hi nahi sakta. Ye is model ki GPT "
                "sakht mukhtalif lagti hai; pehle 'Read Info / "
                "GPT' se poora table dekho.", "ERROR")
        return False

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BACKUPS_DIR / f"identify-{_model_slug(dev)}-{ts}"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka ({outdir}): {e}",
                "ERROR")
        return False
    ctx.log(f"Backup yahan save hoga: {outdir}", "INFO")

    ctx.progress(40, f"{len(present)} safety partitions ka "
                     "backup ho raha hai...")
    ctx.log(f"Step 2/2: Backup — {', '.join(present)}", "INFO")
    files = [outdir / f"{n}.bin" for n in present]
    code = ctx.stream(
        cmd + ["r", ",".join(present),
               ",".join(str(f) for f in files)] + extra,
        timeout=900, cwd=cwd)
    if ctx.is_cancelled():
        return False

    done = [f for f in files if f.is_file() and f.stat().st_size > 0]
    if code != 0 or len(done) != len(present):
        missing = [f.name for f in files if f not in done]
        ctx.log(f"Backup MUKAMMAL nahi hua (exit code {code}) — "
                f"ye files nahi parhi ja sakeen: "
                f"{', '.join(missing) if missing else '?'}.",
                "ERROR")
        if done:
            ctx.log("Jo files ban gayi hain wo folder me hain, "
                    "lekin ye mukammal safety backup NAHI mana "
                    "jayega — wajah theek karke op dobara chalao: "
                    f"{outdir}", "WARN")
        return False

    # summary.txt — dukaan ke record ke liye saboot
    lines = [
        "MEER Tool Pro — Identify + Auto-Backup",
        f"Waqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Model: {getattr(dev, 'model', '') or '(naam nahi mila)'}",
        f"Chip: {getattr(dev, 'chip', '') or '(maloom nahi)'}",
        f"Mode: {getattr(dev, 'mode', '')}",
        f"GPT source: MTKClient printgpt ({len(parts)} "
        "partitions)",
        "",
        "Backup files:",
    ]
    for f in done:
        lines.append(f"  {f.name} — {f.stat().st_size:,} bytes")
    if skipped:
        lines.append("")
        lines.append("Skip hue (GPT me nahi thay): "
                     + ", ".join(skipped))
    lines.append("")
    lines.append("Note: ye backup kisi bhi destructive op se "
                 "pehle ka safety record hai — customer ke phone "
                 "ki asal halat isi me mehfooz hai.")
    try:
        (outdir / "summary.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        ctx.log(f"summary.txt nahi likhi ja saki ({e}) — backup "
                "files phir bhi tayyar hain.", "WARN")

    for f in done:
        ctx.log(f"{f.name}: {f.stat().st_size:,} bytes", "DATA")
    ctx.log(f"Identify + safety backup mukammal: {outdir} — "
            "ab koi bhi MTK op chalane se pehle ye backup "
            "tumhare paas mehfooz hai.", "OK")
    ctx.progress(95, "Identify + backup mukammal")
    return True
