"""
mdm_proinfo_backup.py — Transsion MDM pack: proinfo partition ka backup.

Ye op kisi model ko pehle se "supported" nahi kehta — ye sirf MECHANISM
deta hai: MTKClient se proinfo partition parh kar tools/mdm-backups/
<model>/ me mehfooz karna. Saaf (MDM-free) phone ka yahi backup kal
tumhari asal MDM library banega — per-model patch data tumhare apne
backups se ayega, waqt ke saath.
"""

import json
import re
from datetime import datetime

from core import engines
from core.runner import TOOLS_DIR

OP = {
    "id": "mdm_proinfo_backup",
    "category": "MDM / Transsion",
    "name": "Proinfo Backup (MDM Library)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


def _model_slug(dev) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", (dev.model or "")).strip("-")
    return slug or "unknown-model"


def _resolve_mtk(ctx):
    """(cmd_prefix, cwd) ya (None, None) — guided FAIL khud log karta hai."""
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient engine app ke engines/mtkclient/ folder "
                "me rakho (mtk.py), ya PATH par 'mtk' command install karo. "
                "Engine ke baghair proinfo parhi nahi ja sakti.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def _check_mtk_device(ctx):
    dev = ctx.device
    if not dev or dev.mode not in ("BROM", "PRELOADER"):
        ctx.log("Device BROM/Preloader mode me nahi hai. Phone band karke "
                "Volume Up + Volume Down dono dabaye hue cable lagao — "
                "pehle 'META Mode Guide' op chala kar port confirm kar lo.",
                "ERROR")
        return None
    return dev


def run(ctx) -> bool:
    cmd, cwd = _resolve_mtk(ctx)
    if cmd is None:
        return False
    dev = _check_mtk_device(ctx)
    if dev is None:
        return False

    slug = _model_slug(dev)
    dest_dir = TOOLS_DIR / "mdm-backups" / slug
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka ({dest_dir}): {e}", "ERROR")
        return False

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{ts}-proinfo.bin"

    ctx.progress(10, "proinfo partition parhi ja rahi hai...")
    ctx.log(f"Backup ki jagah: {dest}", "INFO")
    extra_args = engines.mtk_extra_args()
    code = ctx.stream(cmd + ["r", "proinfo", str(dest)] + extra_args,
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False

    if dest.is_file() and dest.stat().st_size > 0:
        size = dest.stat().st_size
        sidecar = {
            "brand": dev.brand or "",
            "model": dev.model or "",
            "chip": dev.chip or "",
            "serial": dev.serial or "",
            "when": datetime.now().isoformat(timespec="seconds"),
            "file": dest.name,
            "size_bytes": size,
            "source": "MTKClient r proinfo",
        }
        try:
            dest.with_suffix(".json").write_text(
                json.dumps(sidecar, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Note (.json) nahi likh saka, lekin backup ban gaya "
                    f"hai: {e}", "WARN")
        ctx.progress(95, "Backup mukammal")
        ctx.log(f"proinfo backup tayyar hai: {dest} ({size} bytes) — "
                "ye file MDM library me mehfooz hai.", "OK")
        return True

    ctx.log(f"proinfo backup nahi bana (MTKClient exit code {code}). "
            "File khali hai ya bani hi nahi. Note: kuch chipsets par "
            "proinfo read ke liye bhi DA/auth lag sakta hai — sahi DA "
            "tools/loaders/mtk/ me rakho, driver (MediaTek VCOM) aur "
            "cable check karo, phir dobara try karo.", "ERROR")
    return False
