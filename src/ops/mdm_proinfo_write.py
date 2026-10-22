"""
mdm_proinfo_write.py — Transsion MDM pack: proinfo partition likhna (restore).

Ye ASAL partition write hai — nakli ya andaza success kabhi nahi.
File hamesha tumhari apni MDM library (tools/mdm-backups/) se chuni
jati hai: pehle wahi file jo is device ke model se match karti ho,
warna sab se nayi backup file. Ghalat model ki proinfo likhne se
phone kharab ho sakta hai — is liye chunav aur warning log me saaf
dikhaye jate hain. Tool kisi model ko pehle se supported nahi kehta;
likhi jane wali file tumhare apne liye hue backup se hi ati hai.

DANGER GATE (Phase 2 backup-first audit ka fix): pehle ye op
warning-only tha — ab tasdeeq (neeche wale bar ki khatarnaak-write
checkbox) ke baghair AIK bhi write koshish nahi hoti.
"""

import re

from core import engines
from core.danger_gate import danger_gate
from core.runner import TOOLS_DIR

OP = {
    "id": "mdm_proinfo_write",
    "category": "MDM / Transsion",
    "name": "Proinfo Restore / Write",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
    "danger_write": True,
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
                "Engine ke baghair proinfo likhi nahi ja sakti.", "WARN")
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


def _find_candidates():
    base = TOOLS_DIR / "mdm-backups"
    if not base.is_dir():
        return []
    return [p for p in base.rglob("*.bin") if "proinfo" in p.name.lower()]


def _pick_candidate(candidates, dev):
    """Model-folder match wali file ko tarjeeh, warna sab se nayi file."""
    if dev is not None:
        slug = _model_slug(dev).lower()
        raw_model = (dev.model or "").lower()
        for cand in candidates:
            parent = cand.parent.name.lower()
            if not parent:
                continue
            if parent == slug or parent in slug or slug in parent:
                return cand
            if raw_model and (raw_model in parent or parent in raw_model):
                return cand
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run(ctx) -> bool:
    # DANGER GATE SAB SE PEHLE — tasdeeq ke baghair zero koshish
    # (Phase 2 audit fix: pehle ye op warning-only tha).
    if not danger_gate(ctx, "PROINFO WRITE"):
        return False
    candidates = _find_candidates()
    if not candidates:
        ctx.log("MDM library me koi proinfo backup file nahi mili — "
                "likhne ke liye file hi mojood nahi.", "ERROR")
        ctx.log("Guide: pehle 'Proinfo Backup' op se is ya kisi saaf "
                "phone ka backup lo; library tools/mdm-backups/<model>/ "
                "me banti hai. Bina backup ke write mumkin nahi.", "WARN")
        return False

    dev_for_pick = ctx.device
    chosen = _pick_candidate(candidates, dev_for_pick)
    ctx.log(f"Write ke liye chuni gayi file: {chosen}", "INFO")
    ctx.log("KHABARDAR: ye ASAL partition write hai — ghalat model ki "
            "file likhne se phone kharab ho sakta hai; sirf usi model "
            "ki saaf proinfo likho jiska backup tum ne khud liya tha.",
            "WARN")

    cmd, cwd = _resolve_mtk(ctx)
    if cmd is None:
        return False
    dev = _check_mtk_device(ctx)
    if dev is None:
        return False

    ctx.progress(10, "proinfo partition likhi ja rahi hai...")
    extra_args = engines.mtk_extra_args()
    code = ctx.stream(cmd + ["w", "proinfo", str(chosen)] + extra_args,
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "Write mukammal")
        ctx.log(f"proinfo write mukammal: {chosen.name} phone par likh "
                "di gayi hai.", "OK")
        return True
    ctx.log(f"proinfo write fail hua (MTKClient exit code {code}). "
            "Aam wajahen: device BROM/Preloader me nahi raha, DA/auth "
            "is chipset ke liye chahiye, ya file is phone ke liye nahi "
            "hai. Cable/driver check karke dobara try karo.", "ERROR")
    return False
