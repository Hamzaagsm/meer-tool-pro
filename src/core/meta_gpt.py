"""
meta_gpt.py — META session se GPT / partition-table read +
model-match compatibility check (Round 7, B4).

SEPT-SEC-RESEARCH §4-B item 4 (UMT ka pattern): koi bhi patch
op (B2 LK patch, B3 plugin patch) chalne se PEHLE partition
table parh kar verify karna ke device wohi class hai jis ke
liye data hai — mismatch par RUKNA. Ye module wahi deewar hai:

  - read_gpt(): FT_PART_READ se GPT rakhne wali partition
    ("gpt", phir "pgpt") ko tolerant parhai (aakhir tak, max
    64 KB) se parh kar core.gpt_parse se asal partition naam
    nikalta hai — GPT partition aksar 64 KB se chhoti hoti
    hai, exact-length wali parhai wahan nakam hoti. Parse
    fail / partition na mile / FT read unsupported — sab
    saaf wajah ke saath (None, wajah); andaze wala table
    kabhi nahi.
  - check_partitions(): diye gaye lazmi partitions GPT me
    maujood hain ya nahi — patch op apni partition (lk /
    proinfo / frp) is se pehle lazmi verify karta hai; na ho
    to op aage nahi barhta (brick-hifazat ki deewar).
  - log_table(): poora table log me — dukaan ke paas saboot
    ke kya parha gaya.

IMAANDARI: GPT kiss partition naam se FT par milta hai, ye
firmware par munhasir hai (aam tor par 'gpt'/'pgpt'); dono
nakam hon to op imaandari se rukta hai, nakli table nahi
banta. Bench-verification asal phone par baqi hai — baqi
round-7 META kaam ki tarah.
"""

from __future__ import annotations

from core import gpt_parse, meta_patch, meta_session

GPT_CANDIDATE_NAMES = ("gpt", "pgpt")
GPT_READ_BYTES = 64 * 1024     # header + 128 entries × 128B ke liye kaafi


def read_gpt(ctx, session):
    """(names, wajah) — names = GPT partition naamon ki list
    (asal case), ya (None, wajah) nakami par. Har nakami yahin
    log bhi ho jati hai."""
    last_err = ""
    for name in GPT_CANDIDATE_NAMES:
        # Tolerant parhai: GPT partition aksar 64 KB se chhoti
        # hoti hai — exact-length mangna nakam hota; jitna
        # verified mile wahi parh kar parse karte hain.
        raw = meta_patch.ft_part_read_to_end(session, name,
                                             GPT_READ_BYTES)
        if not raw:
            last_err = (f"'{name}' partition se kuch NAHI parha "
                        "ja saka (FT part-read unsupported ya "
                        "partition maujood nahi).")
            continue
        try:
            names = gpt_parse.parse_gpt(raw)
        except ValueError as e:
            last_err = (f"'{name}' parha gaya ({len(raw)} bytes) "
                        f"lekin GPT parse nahi hua: {e}")
            continue
        ctx.log(f"GPT '{name}' partition se parha gaya — "
                f"{len(names)} partitions mileen.", "OK")
        return names, None
    ctx.log("GPT parha nahi ja saka: " + (last_err or "koi wajah "
            "nahi mili") + " Kuch firmwares par FT partition read "
            "supported nahi hota — aisi surat me patch-class ops "
            "imaandari se yahin rukte hain (andaze par kaam "
            "nahi hota).", "ERROR")
    return None, last_err or "GPT read fail"


def log_table(ctx, names):
    """Poora partition table log me (saboot ke liye)."""
    for i, n in enumerate(names, 1):
        ctx.log(f"  {i:>2}. {n}", "DATA")


def check_partitions(ctx, session, needed, model=None):
    """Compatibility deewar: GPT parho, `needed` partitions ki
    maujoodgi verify karo. True = sab maujood (aage barho);
    False = wajah log ho chuki hai, op RUK jaye."""
    names, _err = read_gpt(ctx, session)
    if names is None:
        return False
    log_table(ctx, names)
    have = {n.lower() for n in names}
    missing = [p for p in needed if p.lower() not in have]
    if missing:
        who = ""
        if model:
            who = (f" (muntakhib model: {model.get('name', '')} "
                   f"{model.get('code', '')})")
        ctx.log("COMPATIBILITY MISMATCH — GPT me ye lazmi "
                f"partitions NAHI mileen: {', '.join(missing)}"
                f"{who}. Device muntakhib model/data se match "
                "nahi karta — patch op yahin RUK raha hai. "
                "Ghalat device par patch likhna brick ki dawat "
                "hai.", "ERROR")
        return False
    ctx.log("Compatibility check PASS — lazmi partitions GPT "
            f"me maujood hain: {', '.join(needed)}.", "OK")
    return True
