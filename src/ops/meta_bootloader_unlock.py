"""
meta_bootloader_unlock.py — META Bootloader Unlock: Direct +
Generic (Round 2, §8.2 / §9.1).

Pandora Ultra 10.3.0 (Oct 2026) ka "META bootloader unlock",
UMT UltimateMTK2 v3.8 ka META UBL (tested X6531/X6532, Tecno
KJ5/KJ8/KL4h) aur MDMFixTool v1.0.0.5 (18 Oct 2026) ka
"Transsion Bootloader Unlock (Direct + Generic)" — sab is baat
ka saboot hain ke META protocol se bootloader unlock ka rasta
khula hai, khaas taur par naye Helio G200/G100 class par (Hot
60 Pro/Pro+, Spark 40 Pro+, Camon 50/50 Pro — RESEARCH-2 §1.8).

MEER ki amal-dari — imaandari se do raste:
  - DIRECT: maujooda LK-patch flow (ops.meta_ubl_unlock):
    META session → GPT check → poora LK backup → per-model
    patch-data se LK patch → read-back verify. Patch-data
    library (tools/meta-patch-data.json) me model ho to hi
    chalta hai; guessed offset par LK kabhi nahi likha jata.
  - GENERIC: closed tools ka "Generic" rasta apne bytes publish
    nahi karta — MEER ke paas is ka koi verified public
    mechanism nahi hai, is liye generic yahan KOI andaza nahi
    lagata. Generic sirf itna karta hai: model ka verified LK
    patch-data maujood ho to wahi Direct rasta istemal karta
    hai; na ho to guided STOP — bench-capture program ka rasta
    batata hai (LK capture → patch-data library me jama → phir
    unlock). Nakli unlock ka button code me hai hi nahi.

ANTI-CRACK par saaf had (RESEARCH-2 §1.8 caveat): AUT V200 ki
apni changelog kehti hai us ki anti-crack removal
"server-based" hai — META entry local hai, patch data server
-side ho sakta hai. MEER anti-crack removal NAHI banata
(patch bytes gap hain — doosri group sirf capture program
bana rahi hai); ye op sirf bootloader unlock hai.

KHABARDAR (hamesha): bootloader unlock par aam tor par tamam
userdata WIPE ho jata hai — danger gate (PARAMS bar ki tasdeeq)
+ warning pehle; tasdeeq ke baghair device par AIK bhi koshish
nahi hoti. New-Auth class (Dimensity 6300/6400/7100/7300/7400
/9000/9400/9500) par LADDER guard rukta hai — wahan META entry
hi gated hai.
"""

from __future__ import annotations

from core import meta_guard, meta_patch

OP = {
    "id": "meta_bootloader_unlock",
    "category": "MDM / Transsion",
    "name": "⚠ Bootloader Unlock (META Mode) — Direct + Generic",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "danger_write": True,
    "params": ("method",),
}

METHODS = ("auto", "direct", "generic")

# UMT v3.8 ne META UBL in chips/models par test kiya tha (public
# changelog — precedent, MEER ka daawa nahi ke har aik par chalega).
UMT_TESTED_PRECEDENT = ("X6531", "X6532", "KJ5", "KJ8", "KL4h")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def parse_method(params, method=None):
    """'auto' | 'direct' | 'generic' — ghalat value par 'auto'
    + wajah (andaze se koi method nahi chuni jati, default
    imaandar hai: pehle patch-data dekho)."""
    raw = str(method if method is not None else
              (params or {}).get("method", "") or "auto").strip().lower()
    if raw in METHODS:
        return raw, None
    return "auto", (f"Method '{raw}' pehchana nahi gaya — 'auto' "
                    "istemal ho raha hai (pehle patch-data dekha "
                    "jayega).")


def has_patch_data(model_code):
    """Model ka verified LK patch-data library me hai ya nahi."""
    if not model_code:
        return False
    entry, _why = meta_patch.patch_entry_for(model_code, "lk_patch")
    return entry is not None


def generic_stop_lines(code):
    """Generic rasta rukne par rehnumai (pure — testable)."""
    lines = [
        "GENERIC rasta yahin ruk raha hai — wajah imaandari se:",
        "• Is model ka verified LK patch-data library "
        f"(tools/meta-patch-data.json) me NAHI hai{' (' + code + ')' if code else ''}.",
        "• Closed tools (MDMFixTool Direct+Generic, UMT v3.8) apne "
        "generic unlock ke bytes publish nahi karte — MEER andaze "
        "se LK par kuch nahi likhega (galat LK = seedha brick).",
        "• Anti-crack removal is op ka hissa NAHI hai — AUT V200 "
        "ki apni changelog kehti hai wo server-based hai; patch "
        "bytes ka gap bench-capture se bharega, internet se nahi.",
        "Agla qadam (bench): isi model ka stock LK backup lo "
        "(META Partition Manager → Read 'lk'), phir unlock-pattern "
        "capture program se patch-data library me jama karo — us "
        "ke baad yehi op Direct raste se unlock karega.",
        "Aarzi rasta: phone on hota ho to Settings → Developer "
        "options me 'OEM unlocking' ON karke Fastboot 'oem unlock' "
        "azmao — wo official rasta hai, META ki zaroorat nahi.",
    ]
    return lines


# ---------------------------------------------------------------------------
# Op
# ---------------------------------------------------------------------------
def run(ctx, model=None, method=None) -> bool:
    meth, note = parse_method(getattr(ctx, "params", {}), method)
    if note:
        ctx.log(note, "WARN")
    ctx.log("META Bootloader Unlock (Direct + Generic): naye models "
            "pehle — Helio G200/G100 class (Hot 60 Pro/Pro+, "
            "Spark 40 Pro+, Camon 50/50 Pro) par META entry khuli "
            "hai; UMT-tested precedent: X6531/X6532, KJ5/KJ8/KL4h.",
            "INFO")
    ctx.log("KHABARDAR: Bootloader unlock par aam tor par tamam "
            "userdata WIPE ho jata hai — customer ki ijazat aur "
            "zaroori backup pehle lazmi hai. Tasdeeq (PARAMS bar) "
            "ke baghair device par AIK bhi koshish nahi hogi.",
            "WARN")

    # LADDER guard — new-Auth class par META entry hi gated hai.
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    code = meta_patch.model_code_for(ctx, model)
    if model:
        ctx.log(f"Model: {model.get('name', '')} "
                f"({code or '?'})", "INFO")

    if meth == "direct":
        ctx.log("Method: DIRECT (LK patch — per-model patch-data "
                "se).", "INFO")
        from ops import meta_ubl_unlock
        return meta_ubl_unlock.run(ctx, model=model)

    # generic / auto: pehle patch-data dekho — ho to Direct rasta,
    # na ho to guided STOP (koi andaza nahi).
    if has_patch_data(code):
        ctx.log(f"Method: {meth.upper()} → is model ({code}) ka "
                "verified LK patch-data maujood hai, is liye "
                "Direct (LK patch) rasta istemal ho raha hai.",
                "INFO")
        from ops import meta_ubl_unlock
        return meta_ubl_unlock.run(ctx, model=model)
    ctx.log(f"Method: {meth.upper()} — model '{code or '?'}' ka "
            "verified LK patch-data library me NAHI hai.", "ERROR")
    for line in generic_stop_lines(code):
        ctx.log(line, "INFO" if line.startswith(("Agla", "Aarzi"))
                else "WARN")
    return False
