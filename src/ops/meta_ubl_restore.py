"""
meta_ubl_restore.py — Restore LK (META): stock LK wapas —
relock ka rasta (Round 7, B2 ka jora-op).

UBL (LK patch) ke doran tool ne poori LK partition ka backup
(backups/meta-patch/lk-<code>-<time>.bin) banaya tha. Ye op
wahi file wapas likhta hai — ya, full backup na mile to, patch
ke range-record (asal bytes) wala restore istemal karta hai:

  1. DANGER GATE → LADDER guard → model code.
  2. Full-LK backup file (.bin) ho to: GPT check → poori file
     chunked write → poori read-back byte-compare.
  3. Na ho to: 'lk_patch' ka taza backup record →
     ops.meta_restore_patch.restore_from_record.
  4. Dono na hon to guided STOP — baghair backup ke restore
     mumkin nahi, nakli restore kabhi nahi.
"""

import re

from core import meta_gpt, meta_guard, meta_patch, meta_session
from core.danger_gate import danger_gate
from ops.meta_restore_patch import restore_from_record

OP = {
    "id": "meta_ubl_restore",
    "category": "MDM / Transsion",
    "name": "⚠ Restore LK / Relock (META Mode) — Round 7",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "danger_write": True,
}


def _latest_lk_bin(model_code):
    """Model ke liye sab se taza full-LK backup file ya None."""
    if not meta_patch.PATCH_BACKUP_DIR.is_dir():
        return None
    safe = re.sub(r"[^A-Za-z0-9]+", "-",
                  str(model_code or "")).strip("-")
    files = sorted(meta_patch.PATCH_BACKUP_DIR.glob("lk-*.bin"),
                   key=lambda p: p.stat().st_mtime)
    for path in reversed(files):
        if safe and path.name.startswith(f"lk-{safe}-"):
            return path
        if not safe:
            return path
    return None


def run(ctx, model=None) -> bool:
    if not danger_gate(ctx, "META RESTORE LK"):
        return False
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    code = meta_patch.model_code_for(ctx, model)
    if model:
        ctx.log(f"Model: {model.get('name', '')} "
                f"({code or '?'})", "INFO")
    if not code:
        ctx.log("Model/device ka code match NAHI hua — restore "
                "ke liye ye pakka hona lazmi hai. MDM List se "
                "model select karke chalao.", "ERROR")
        return False
    bin_path = _latest_lk_bin(code)
    rec, rec_path = meta_patch.latest_backup_record(code,
                                                     "lk_patch")
    if bin_path is None and rec is None:
        ctx.log(f"Model '{code}' ka na full-LK backup (.bin) "
                "mila, na LK patch ka backup record — restore "
                "ke liye kuch maujood NAHI hai.", "ERROR")
        ctx.log("Guide: Restore LK sirf tab mumkin hai jab "
                "pehle is model par 'Bootloader Unlock — LK "
                "Patch (META)' chala ho — wo har dafa patch se "
                "pehle backup khud banata hai.", "WARN")
        return False
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    try:
        with session:
            if bin_path is not None:
                data = bin_path.read_bytes()
                ctx.log(f"Full-LK backup: {bin_path} "
                        f"({len(data)} bytes)", "DATA")
                # Partition ka naam record se, warna 'lk'
                part = (rec or {}).get("partition") or "lk"
                if not meta_gpt.check_partitions(ctx, session,
                                                 [part],
                                                 model=model):
                    return False
                ctx.progress(45, "Stock LK wapas likha ja raha "
                                 "hai...")
                try:
                    meta_patch.ft_part_write(session, part, 0, data)
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    return False
                if ctx.is_cancelled():
                    return False
                ctx.progress(75, "Read-back verify ho raha hai...")
                try:
                    back = meta_patch.ft_part_read(session, part, 0,
                                                   len(data))
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    return False
                if back != data:
                    ctx.log("READ-BACK MATCH NAHI HUA — stock LK "
                            "ke bytes device par tasdeeq NAHI "
                            "hue. Natija MASHKOOK hai.", "ERROR")
                    return False
                ctx.log("Read-back verify PASS — poora stock LK "
                        "byte-to-byte wapas hai (relock ki halat "
                        "restore ho gayi).", "OK")
            else:
                ctx.log(f"Full-LK .bin NAHI mila — range-record "
                        f"se restore ho raha hai: {rec_path}",
                        "WARN")
                if not restore_from_record(ctx, session, rec):
                    return False
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Restore LK ke doran ghalti: {e}", "ERROR")
        return False
    if ctx.is_cancelled():
        return False
    ctx.log("Restore LK mukammal — phone ko reboot karke "
            "bootloader halat tasdeeq kar lo.", "OK")
    ctx.progress(95, "Restore LK mukammal")
    return True
