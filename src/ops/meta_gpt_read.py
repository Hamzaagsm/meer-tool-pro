"""
meta_gpt_read.py — META session se GPT / partition table read
(Round 7, B4 — SEPT-SEC-RESEARCH §4-B item 4).

UMT ke pattern par: patch-class kaam se pehle partition table
parhna hi hifazat ki deewar hai. Ye op wahi table dukaan ke
liye parh kar dikhata hai — FT_PART_READ se 'gpt'/'pgpt'
partition ke pehle 64 KB, core.gpt_parse se asal naam, aur
khaas partitions (frp / lk / proinfo / persist waghera) ki
maujoodgi ki report.

SUCCESS sirf asal parse-shuda table par hai; FT read ya GPT
parse fail ho to saaf FAIL — andaze wala table kabhi nahi.
"""

from core import meta_gpt, meta_session

OP = {
    "id": "meta_gpt_read",
    "category": "MDM / Transsion",
    "name": "GPT / Partition Table Read (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}

_INTEREST = ("frp", "lk", "lk1", "proinfo", "persist", "nvram",
             "nvdata", "seccfg", "boot", "vbmeta")


def run(ctx) -> bool:
    ctx.log("META session se GPT (partition table) parha ja raha "
            "hai...", "INFO")
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    ctx.progress(35, "GPT parha ja raha hai...")
    try:
        with session:
            names, _err = meta_gpt.read_gpt(ctx, session)
    except meta_session.MetaError as e:
        ctx.log(str(e), "ERROR")
        return False
    if names is None:
        return False
    if ctx.is_cancelled():
        return False
    meta_gpt.log_table(ctx, names)
    have = {n.lower() for n in names}
    for p in _INTEREST:
        state = "MAUJOOD" if p in have else "nahi"
        ctx.log(f"Partition '{p}': {state}", "DATA")
    ctx.log("GPT read mukammal — yehi table patch-class ops "
            "(UBL LK patch / plugin patch) se pehle compatibility "
            "check me istemal hoti hai.", "OK")
    ctx.progress(95, "GPT read mukammal")
    return True
