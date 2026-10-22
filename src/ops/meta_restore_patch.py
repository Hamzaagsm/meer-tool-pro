"""
meta_restore_patch.py — Restore MDM (META): patch se pehle ki
asal halat wapas (Round 7, B3 ka jora-op).

Har META patch (plugin / LK) se pehle tool asal bytes ka backup
record (backups/meta-patch/) banata hai. Ye op usi record se
original bytes wapas likhta hai — Fenix ke RESTORE MDM wala
jora, META session se:

  1. DANGER GATE (ye bhi asal write hai).
  2. LADDER guard.
  3. Model ka sab se taza backup record — na mile to guided
     STOP (restore ke liye backup ka hona lazmi hai; tool
     nakli restore nahi karta).
  4. GPT compatibility check (record wali partition maujood
     ho).
  5. Original bytes write → READ-BACK byte-match → SUCCESS.

restore_from_record() mushtaraka hai — B2 ka Restore LK bhi
(range-record wali surat me) yahi istemal karta hai.
"""

from core import meta_gpt, meta_guard, meta_patch, meta_session
from core.danger_gate import danger_gate

OP = {
    "id": "meta_restore_patch",
    "category": "MDM / Transsion",
    "name": "⚠ Restore MDM (META Patch Backup se) — Round 7",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "danger_write": True,
}


def restore_from_record(ctx, session, rec):
    """Record ke original bytes wapas likho + verify karo.
    Session pehle se khula hua caller deta hai."""
    part = rec.get("partition", "")
    entries = rec.get("entries", [])
    if not part or not entries:
        ctx.log("Backup record na-mukammal hai (partition/entries "
                "nahi) — restore nahi ho sakta.", "ERROR")
        return False
    if not meta_gpt.check_partitions(ctx, session, [part]):
        return False
    ctx.progress(45, "Asal bytes wapas likhe ja rahe hain...")
    for ent in entries:
        try:
            orig = bytes.fromhex(ent.get("original_hex", ""))
        except Exception:  # noqa: BLE001
            ctx.log("Backup record ki hex kharab hai — restore "
                    "ROK di gayi hai.", "ERROR")
            return False
        try:
            meta_patch.ft_part_write(session, part,
                                     int(ent.get("offset", 0)),
                                     orig)
        except meta_session.MetaError as e:
            ctx.log(str(e), "ERROR")
            return False
        if ctx.is_cancelled():
            return False
    ctx.progress(75, "Read-back verify ho raha hai...")
    for ent in entries:
        orig = bytes.fromhex(ent.get("original_hex", ""))
        try:
            back = meta_patch.ft_part_read(
                session, part, int(ent.get("offset", 0)), len(orig))
        except meta_session.MetaError as e:
            ctx.log(str(e), "ERROR")
            return False
        if back != orig:
            ctx.log("READ-BACK MATCH NAHI HUA — restore ke bytes "
                    "device par tasdeeq nahi hue. Natija MASHKOOK "
                    "hai.", "ERROR")
            return False
    ctx.log("Read-back verify PASS — asal (patch se pehle wale) "
            "bytes device par byte-to-byte wapas hain.", "OK")
    return True


def run_restore_flow(ctx, model, kind, action_label):
    """kind se bandha hua restore (B2 ke liye 'lk_patch', B3 ke
    liye 'plugin_patch'); kind=None ho to model ka koi bhi taza
    record."""
    if not danger_gate(ctx, action_label):
        return False
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    code = meta_patch.model_code_for(ctx, model)
    if model:
        ctx.log(f"Model: {model.get('name', '')} "
                f"({code or '?'})", "INFO")
    if not code:
        ctx.log("Model/device ka code match NAHI hua — restore "
                "ke liye ye pakka hona lazmi hai.", "ERROR")
        ctx.log("Guide: MDM List se model select karke chalao — "
                "wahan code pakka milta hai.", "WARN")
        return False
    rec, path = meta_patch.latest_backup_record(code, kind)
    if rec is None:
        ctx.log(f"Model '{code}' ka koi patch backup record NAHI "
                "mila (backups/meta-patch/).", "ERROR")
        ctx.log("Guide: Restore sirf usi surat me mumkin hai jab "
                "pehle is model par patch op chala ho (har patch "
                "se pehle tool asal bytes ka record khud banata "
                "hai). Baghair record ke tool nakli restore NAHI "
                "karega.", "WARN")
        return False
    ctx.log(f"Backup record mila: {path} "
            f"({rec.get('when', '')}, partition "
            f"{rec.get('partition', '')})", "DATA")
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    try:
        with session:
            ok = restore_from_record(ctx, session, rec)
    except meta_patch.PatchError as e:
        ctx.log(str(e), "ERROR")
        return False
    if not ok or ctx.is_cancelled():
        return False
    ctx.log("Restore mukammal — device ki halat bilkul waisi "
            "hai jaisi patch se pehle thi (backup record ke "
            "mutabiq).", "OK")
    ctx.progress(95, "Restore mukammal")
    return True


def run(ctx, model=None) -> bool:
    ctx.log("Restore MDM (META): aakhri META patch se pehle ki "
            "asal proinfo/state bytes backup record se wapas "
            "likhe jayenge.", "INFO")
    return run_restore_flow(ctx, model, "plugin_patch",
                            "META RESTORE MDM (PATCH BACKUP)")
