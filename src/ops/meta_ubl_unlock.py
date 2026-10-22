"""
meta_ubl_unlock.py — META UBL: LK backup → LK patch → unlock
(Round 7, B2 — SEPT-SEC-RESEARCH §4-B item 2).

UMT v3.8 ka public mechanism, jis par Fenix ka "UBL NEW SEC"
bhi khara hai: META session → partition table read → **LK
backup → LK patch → unlock**; stock LK wapas = relock (jora-op
meta_ubl_restore). Un ke tested devices me hamare DB ke
models aur 2026-05 tak ke patch dates shamil hain.

Hamari amal-dari, sakht usoolon ke saath:
  - Mushtaraka patch flow (ops.meta_plugin_patch.run_patch_flow,
    kind='lk_patch'): DANGER GATE → LADDER guard → patch-data
    lookup → GPT compatibility check → backup-first → find-
    pattern verify → write → read-back verify.
  - Us se pehle, izafi hifazat: **poori LK partition ka backup**
    (full_lk_backup hook) backups/meta-patch/lk-<code>-<time>.bin
    me — taake Restore LK poora stock LK wapas kar sake, sirf
    patched hisay nahi.
  - Patch ke byte-pattern per-model patch-data library se
    ate hain (tools/meta-patch-data.json, 'lk_patch'). Model
    library me na ho to guided STOP — **guessed offset par
    LK kabhi nahi likha jayega** (galat LK = seedha brick).
  - KHABARDAR log me pehle se: bootloader unlock par aam tor
    par userdata WIPE hota hai.

IMAANDARI: LK ki mukammal parhai FT part-read ki chunk requests
se hoti hai; partition ka aakhir wahan mana jata hai jahan
firmware mukammal chunk dene se inkaar kare — beech me nakami
ho to backup na-mukammal samajh kar op patch se PEHLE ruk
jata hai (find-pattern verify is ka dohra saboot bhi hai).
Bench-verification asal phone par baqi hai.
"""

import re
from datetime import datetime

from core import meta_patch, meta_session
from ops.meta_plugin_patch import run_patch_flow

OP = {
    "id": "meta_ubl_unlock",
    "category": "MDM / Transsion",
    "name": "⚠ Bootloader Unlock — LK Patch (META Mode) — Round 7",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "danger_write": True,
}

def _read_to_end(session, part):
    """Partition ko aakhir tak parho — asal amal core.meta_patch
    ke tolerant reader me hai (4096 ki units + 512 salvage)."""
    return meta_patch.ft_part_read_to_end(
        session, part, meta_patch.MAX_PART_BYTES)


def full_lk_backup(ctx, session, entry, model=None):
    """Poori LK (entry wali partition) parh kar .bin backup.

    run_patch_flow ka pre_write_hook: True = backup tayyar,
    aage barho; False = wajah log ho chuki, patch NAHI hoga."""
    part = entry["partition"]
    code = meta_patch.model_code_for(ctx, model)
    ctx.progress(25, f"Poori '{part}' partition ka backup ban "
                     "raha hai...")
    try:
        raw = _read_to_end(session, part)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"LK backup ke doran ghalti: {e}", "ERROR")
        return False
    data = bytearray(raw)
    if not data:
        ctx.log(f"Partition '{part}' se AIK byte bhi NAHI parha "
                "ja saka — baghair mukammal backup ke LK patch "
                "NAHI hoga.", "ERROR")
        return False
    # Patches ki jagah backup ke dayre me honi chahiye — warna
    # backup na-mukammal hai aur patch rukna chahiye.
    need_end = max(p["offset"] + len(p["find"])
                   for p in entry["patches"])
    if len(data) < need_end:
        ctx.log(f"LK backup sirf {len(data)} bytes bana lekin "
                f"patch data ko {need_end} bytes tak ki jagah "
                "chahiye — backup na-mukammal hai, patch ROK di "
                "gayi hai.", "ERROR")
        return False
    try:
        meta_patch.PATCH_BACKUP_DIR.mkdir(parents=True,
                                          exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9]+", "-",
                      str(code or "model")).strip("-")
        path = (meta_patch.PATCH_BACKUP_DIR /
                f"lk-{safe or 'model'}-{ts}.bin")
        path.write_bytes(bytes(data))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"LK backup file nahi ban saki: {e}", "ERROR")
        return False
    ctx.log(f"Poora stock LK backup tayyar: {path} "
            f"({len(data)} bytes) — Restore LK isi file se poora "
            "stock LK wapas karega.", "DATA")
    return True


def run(ctx, model=None) -> bool:
    ctx.log("META UBL (LK Patch): META session → GPT check → "
            "poora LK backup → per-model patch-data se LK patch "
            "→ read-back verify.", "INFO")
    ctx.log("KHABARDAR: Bootloader unlock par aam tor par tamam "
            "userdata WIPE ho jata hai — customer ki ijazat aur "
            "zaroori backup pehle lazmi hai.", "WARN")

    def hook(c, session, entry):
        return full_lk_backup(c, session, entry, model)

    return run_patch_flow(ctx, model, "lk_patch",
                          "META UBL (LK PATCH)",
                          pre_write_hook=hook)
