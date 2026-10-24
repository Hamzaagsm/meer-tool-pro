"""
mtk_meta_imei_restore.py — META mode se ASAL IMEI restore,
MEER ke apne engine se (koi bahari tool nahi khulta).

Hamza ka usool (2026-10-24): MEER ke andar se koi doosra
tool nahi khulega — har kaam MEER ke apne engine, apni
window, apne log se hoga. Ye op wahi usool hai: pura amal
META session (core.meta_session) ke andar hota hai —
core.meta_imei ka engine nvdata ke ext4 se MP0B_001 file
parhta hai, wahan asal IMEI dekhta hai, aur likhna ho to
usi file me wapas likhta hai.

Flow (koi shortcut nahi):
  1. LADDER guard (new-Auth class par seedhi ke saath rukna).
  2. META session + GPT compatibility check ('nvdata'
     partition maujood hona lazmi).
  3. Pehle MAUJOODA IMEI parho aur log me dikhao (null/
     kharab halat bhi saaf likhi jayegi — yahi repair ki
     pehchan hai).
  4. Type kiya hua IMEI (Network tab ke khane — ctx.params
     se) + Luhn tasdeeq. IMEI 1 lazmi; IMEI 2 khali ho to
     purana wala barqarar rehta hai.
  5. IMEI GATE (core.imei_gate) — warning + tasdeeq ke
     baghair write ki koi koshish nahi.
  6. BACKUP-FIRST: file ki asal halat backups/meta-imei/
     me mehfooz — backup na bane to write nahi.
  7. Write (sirf badle hue hisse) — phir READ-BACK:
     SUCCESS sirf jab dobara parha hua number typed number
     se lafz-ba-lafz mile. 000000 / kharab record / mismatch
     = FAIL, asal parha hua number log me.

Typed IMEI kahan se ata hai: OP par imei_write flag hai —
GUI Network tab (MDM Library me model kholo → Network)
ke "Original IMEI 1/2" wale khanon ki values runner
ctx.params me deta hai, aur tasdeeq checkbox bhi wahin
ka hai. Khane khali hon to op guide karke rukta hai.
"""

from core import meta_gpt, meta_guard, meta_imei, meta_session
from core.imei_gate import imei_write_gate

OP = {
    "id": "mtk_meta_imei_restore",
    "category": "MTK",
    "name": "Restore Original IMEI (META — MEER Engine)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "imei_write": True,
}


def _log_current(ctx, parsed):
    """Maujooda IMEI halat saaf log karo (repair ki pehchan)."""
    for slot in ("1", "2"):
        state = parsed.get(f"state{slot}")
        val = parsed.get(f"imei{slot}")
        if state == "ok":
            ctx.log(f"Maujooda IMEI {slot}: {val}", "DATA")
        elif state == "zero":
            ctx.log(f"Maujooda IMEI {slot}: NULL "
                    "(000000000000000) — NVRAM kharab hai, "
                    "yahi restore hoga.", "WARN")
        else:
            ctx.log(f"Maujooda IMEI {slot}: record KHARAB "
                    "parha gaya (checksum/format durust nahi) "
                    "— NVRAM kharab hai, yahi restore hoga.",
                    "WARN")


def run(ctx, model=None) -> bool:
    # LADDER guard — new-Auth class par seedhi ke saath rukna
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    ctx.log("META IMEI Restore (MEER Engine): koi bahari tool "
            "nahi khulega — pura amal isi window me, META "
            "session se hoga. Sirf phone ka APNA asal IMEI "
            "(dabbe/sticker wala) restore hota hai.", "INFO")
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    try:
        with session:
            return _run_inner(ctx, session)
    except meta_session.MetaError as e:
        ctx.log(str(e), "ERROR")
        return False


def _run_inner(ctx, session) -> bool:
    # GPT compatibility deewar — nvdata partition lazmi
    if not meta_gpt.check_partitions(ctx, session, ["nvdata"]):
        return False
    ctx.progress(25, "nvdata se IMEI file parhi ja rahi hai...")
    try:
        found = meta_imei.locate_imei(session)
    except meta_imei.MetaImeiError as e:
        ctx.log(str(e), "ERROR")
        ctx.log("Guide: is device par IMEI is shakl "
                "(nvdata/MP0B_001) me nahi mila — aisi surat "
                "me asal rasta 'NV Restore (nvram + nvdata)' "
                "hai (apna NV backup wapas likhna), ya model "
                "ki AP_DB/MD1_DB wali surat hai jo abhi MEER "
                "ke is engine ke dayre se bahir hai. Nakli "
                "koshish nahi hogi.", "WARN")
        return False
    parsed = found["parsed"]
    ctx.log(f"IMEI file mili: nvdata/{found['path']} "
            f"(DB v{parsed['version']}, "
            f"{len(found['content'])} bytes)", "OK")
    _log_current(ctx, parsed)
    if ctx.is_cancelled():
        return False

    # Type kiya hua IMEI — Network tab ke khanay (ctx.params)
    params = getattr(ctx, "params", {}) or {}
    imei1 = str(params.get("imei1") or "").strip()
    imei2 = str(params.get("imei2") or "").strip()
    if not imei1:
        ctx.log("IMEI 1 type nahi kiya gaya — write roki "
                "gayi. Pehle UNLOCK page ke IMEI section (upar) "
                "me 'IMEI A' ke khane me DABBE / STICKER wala "
                "asal number type karo (IMEI B dual-SIM ho to "
                "woh bhi), tasdeeq wala checkbox ON karo, phir "
                "ye op dobara chalao. (Purana rasta bhi chalta "
                "hai: MDM Library me is phone ka model kholo → "
                "Network tab.) Upar maujooda halat parh kar "
                "dikha di gayi hai.", "ERROR")
        return False
    for label, val in (("IMEI 1", imei1), ("IMEI 2", imei2)):
        if not val:
            continue
        if val == meta_imei.ZERO_IMEI:
            ctx.log(f"{label}: 000000000000000 likhna mana "
                    "hai — ye null number hai, asal number "
                    "type karo.", "ERROR")
            return False
        if not meta_imei.luhn_ok(val):
            ctx.log(f"{label} durust nahi lagta (15 hindsay + "
                    f"Luhn checksum fail): {val} — dabbe se "
                    "mila kar dobara dekho.", "ERROR")
            return False

    # IMEI GATE — warning + tasdeeq; baghair is ke write nahi
    if not imei_write_gate(ctx):
        return False
    ctx.log(f"IMEI 1 (original): {imei1}", "DATA")
    if imei2:
        ctx.log(f"IMEI 2 (original): {imei2}", "DATA")
    else:
        ctx.log("IMEI 2 type nahi kiya gaya — maujooda IMEI 2 "
                "barqarar rahega, sirf IMEI 1 badlega.", "INFO")

    # BACKUP-FIRST — asal halat mehfooz, warna ruk jao
    ctx.progress(45, "Write se pehle IMEI file ka backup "
                     "liya ja raha hai...")
    try:
        bin_path, _json_path = meta_imei.save_file_backup(
            ctx, found)
    except meta_imei.MetaImeiError as e:
        ctx.log(str(e), "ERROR")
        ctx.log("Backup ke baghair write nahi hogi — wapsi "
                "ka rasta band karke IMEI nahi likha jata.",
                "ERROR")
        return False
    ctx.log(f"Backup mehfooz: {bin_path}", "OK")
    if ctx.is_cancelled():
        return False

    # Nayi file banao (self-check codec ke andar hai)
    try:
        new_content = meta_imei.patch_db(
            found["content"],
            imei1=imei1, imei2=imei2 or None)
    except ValueError as e:
        ctx.log(str(e), "ERROR")
        return False

    # Write — sirf badle hue hisse
    ctx.progress(65, "IMEI nvdata me likha ja raha hai "
                     "(MEER engine)...")
    try:
        chunks = meta_imei.write_imei_content(session, found,
                                              new_content)
    except meta_imei.MetaImeiError as e:
        ctx.log(str(e), "ERROR")
        return False
    except meta_session.MetaError as e:
        ctx.log(f"Write darmiyan me ruka: {e}", "ERROR")
        ctx.log(f"Note: kuch hisse likhe ja chuke ho sakte "
                f"hain. Wapsi ke liye asal file yahan mehfooz "
                f"hai: {bin_path} — pehle READ-BACK tasdeeq "
                "wale hisse se asal halat dekho.", "WARN")
        return False
    if chunks == 0:
        ctx.log("Type kiya hua number pehle se device me "
                "maujood hai — koi byte badalne ki zarurat "
                "nahi pari. Phir bhi read-back tasdeeq hogi.",
                "INFO")

    # READ-BACK — SUCCESS sirf pure match par
    ctx.progress(85, "Read-back tasdeeq: number dobara parha "
                     "ja raha hai...")
    try:
        again = meta_imei.locate_imei(session)
    except (meta_imei.MetaImeiError, meta_session.MetaError) as e:
        ctx.log(f"Read-back hi nahi ho saka: {e}", "ERROR")
        ctx.log("Write ki tasdeeq nahi ho saki — natija FAIL "
                f"mana jayega. Asal file ka backup: {bin_path}",
                "ERROR")
        return False
    expected = {"imei1": imei1,
                "imei2": imei2 or parsed.get("imei2")}
    ok, wajah = meta_imei.compare_readback(expected,
                                           again["parsed"])
    if not ok:
        ctx.log(f"READ-BACK FAIL — {wajah}.", "ERROR")
        _log_current(ctx, again["parsed"])
        ctx.log(f"Natija FAIL hai — nakli kamyabi nahi "
                f"chhupayi gayi. Write se pehle wali asal "
                f"file yahan mehfooz hai: {bin_path}",
                "ERROR")
        return False
    ctx.progress(95, "Read-back match — restore mukammal")
    ctx.log(f"IMEI 1 restore ho gaya aur read-back se MATCH "
            f"hua: {again['parsed'].get('imei1')}", "OK")
    if imei2:
        ctx.log(f"IMEI 2 restore ho gaya aur read-back se "
                f"MATCH hua: {again['parsed'].get('imei2')}",
                "OK")
    ctx.log("Aakhri tasdeeq tum khud karo: phone on karke "
            "*#06# dabao — number dabbe/sticker wale se "
            "milna chahiye.", "INFO")
    return True
