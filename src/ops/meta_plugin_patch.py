"""
meta_plugin_patch.py — META Security Plugin patch (Round 7, B3)
+ tamam META patch ops ka mushtaraka flow.

SEPT-SEC-RESEARCH §4-B item 3: Fenix ka op-pair (SECURITY
PLUGIN NEW SEC / RESTORE MDM) sabit karta hai ke plugin ki
enrollment state META se pohanch wali proinfo/NVRAM-class
storage me hai. Protocol hamara hai; asal kaam per-model
patch-data library (tools/meta-patch-data.json) hai.

Mushtaraka flow (run_patch_flow — B2 ka LK patch bhi yahi
istemal karta hai), tartib sakht hai:
  1. DANGER GATE sab se pehle (ye asal device write hai).
  2. LADDER guard (new-Auth class par rukna + doosra darwaza).
  3. Patch-data lookup — model library me NA HO to guided
     STOP, wajah ke saath. **Guessed offset par likhne ka
     code me rasta hi nahi hai.**
  4. GPT compatibility check (B4) — patch wali partition
     device par maujood honi chahiye, warna STOP.
  5. BACKUP-FIRST: asal bytes parh kar record mehfooz —
     record na bane to write NAHI hota.
  6. FIND-PATTERN verify: device ke bytes library ke 'find'
     se match na hon to STOP (firmware mukhtalif hai).
  7. Write (FT_PART_WRITE, chunked, verified) → READ-BACK
     byte-match — tabhi SUCCESS.
"""

from core import meta_gpt, meta_guard, meta_patch, meta_session
from core.danger_gate import danger_gate

OP = {
    "id": "meta_plugin_patch",
    "category": "MDM / Transsion",
    "name": "⚠ Security Plugin Patch (META Mode) — Round 7",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "danger_write": True,
}


def run_patch_flow(ctx, model, kind, action_label,
                   pre_write_hook=None):
    """kind: 'plugin_patch' ya 'lk_patch' (library ki chaabi).
    pre_write_hook(session, entry) — GPT check ke baad, patch
    se pehle ka izafi kaam (B2 ka full-LK backup); False de to
    flow wahin ruk jata hai."""
    # 1) DANGER GATE — sab se pehle, baghair tasdeeq zero koshish
    if not danger_gate(ctx, action_label):
        return False
    # 2) LADDER guard
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    # 3) Patch-data lookup — na mile to guided STOP
    code = meta_patch.model_code_for(ctx, model)
    if model:
        ctx.log(f"Model: {model.get('name', '')} ({code or '?'})",
                "INFO")
    if not code:
        ctx.log("Device/model ki pehchan se patch-data library ka "
                "koi code match NAHI hua.", "ERROR")
        ctx.log("Guide: ye op MDM List se model select karke "
                "chalana behtar hai — wahan model ka code pakka "
                "milta hai. Baghair code ke tool andaze se koi "
                "data NAHI lagayega.", "WARN")
        return False
    entry, wajah = meta_patch.patch_entry_for(code, kind)
    if entry is None:
        ctx.log(wajah, "ERROR")
        ctx.log("Ye imaandari wali rukawat hai: is model ka "
                "verified patch-data library me jama hi nahi "
                "hua. Guessed offset par likhna phone brick kar "
                "sakta hai — is liye tool yahan rukta hai. Data "
                "tools/meta-patch-data.json me usi din jama hoga "
                "jis din kisi asal phone par verify hoga; us "
                "model par ye op phir asal chalega.", "WARN")
        return False
    part = entry["partition"]
    if entry.get("source"):
        ctx.log(f"Patch-data source: {entry['source']}", "INFO")
    # Session
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    try:
        with session:
            # 4) GPT compatibility check — B4 ki deewar
            ctx.progress(15, "GPT compatibility check ho raha hai...")
            if not meta_gpt.check_partitions(ctx, session, [part],
                                              model=model):
                return False
            if ctx.is_cancelled():
                return False
            # Izafi tayyari (B2: full LK backup)
            if pre_write_hook is not None:
                if not pre_write_hook(ctx, session, entry):
                    return False
                if ctx.is_cancelled():
                    return False
            # 5) BACKUP-FIRST — asal bytes parho
            ctx.progress(35, "Patch se pehle asal bytes ka backup "
                             "ban raha hai...")
            originals = []
            for p in entry["patches"]:
                try:
                    cur = meta_patch.ft_part_read(
                        session, part, p["offset"], len(p["find"]))
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    return False
                originals.append((p["offset"], cur))
            # 6) FIND-PATTERN verify
            for (off, cur), p in zip(originals, entry["patches"]):
                if cur != p["find"]:
                    ctx.log(
                        f"FIND-PATTERN MISMATCH — partition '{part}' "
                        f"offset {off} par device ke bytes library "
                        f"ke pattern se NAHI milte (device: "
                        f"{cur.hex()}, library: {p['find'].hex()}). "
                        "Is firmware par ye data lagana khatarnak "
                        "hota — op yahin RUK raha hai, kuch NAHI "
                        "likha gaya.", "ERROR")
                    return False
            ctx.log("Find-pattern verify PASS — device ke bytes "
                    "library se match karte hain.", "OK")
            rec_path = meta_patch.save_backup_record(
                ctx, code, kind, part, originals,
                source=entry.get("source", ""))
            ctx.log(f"Backup record mehfooz: {rec_path} — kuch "
                    "bhi ghalat ho to 'Restore' wala jora-op is "
                    "record se asal halat wapas kar dega.",
                    "DATA")
            # 7) WRITE + READ-BACK verify
            ctx.progress(60, "Patch likha ja raha hai...")
            for p in entry["patches"]:
                try:
                    meta_patch.ft_part_write(session, part,
                                             p["offset"],
                                             p["replace"])
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    ctx.log("KHABARDAR: kuch patches likhe ja "
                            "chuke ho sakte hain — phone ko is "
                            "halat me aage istemal karne se pehle "
                            "'Restore' jora-op chala kar asal "
                            "halat wapas karo.", "WARN")
                    return False
                if ctx.is_cancelled():
                    return False
            ctx.progress(80, "Read-back verify ho raha hai...")
            for p in entry["patches"]:
                try:
                    back = meta_patch.ft_part_read(
                        session, part, p["offset"],
                        len(p["replace"]))
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    return False
                if back != p["replace"]:
                    ctx.log("READ-BACK MATCH NAHI HUA — likha hua "
                            "data device se wapas parhne par "
                            "library ke replace bytes se NAHI "
                            "milta. Natija MASHKOOK hai — "
                            "'Restore' jora-op se asal halat "
                            "wapas karo.", "ERROR")
                    return False
            ctx.log("Read-back verify PASS — patch ke bytes "
                    "device par byte-to-byte tasdeeq ho gaye.",
                    "OK")
    except meta_patch.PatchError as e:
        ctx.log(str(e), "ERROR")
        return False
    ctx.progress(95, "Patch mukammal")
    return True


def run(ctx, model=None) -> bool:
    ctx.log("META Security Plugin patch: plugin ki enrollment "
            "state proinfo/NVRAM-class storage me per-model "
            "patch-data se badli jati hai. Chalna sirf usi "
            "model par hai jis ka VERIFIED data library me "
            "maujood ho.", "INFO")
    return run_patch_flow(ctx, model, "plugin_patch",
                          "META SECURITY PLUGIN PATCH")
