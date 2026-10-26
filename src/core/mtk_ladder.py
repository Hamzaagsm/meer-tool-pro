"""
mtk_ladder.py — MTK chip → public bypass ladder (pure, testable).

SERVER-REQUIRED research §3.6 ki seedhi: har MTK chip class ke liye
kaun sa darwaza khula hai, kaun sa shart par, kaun sa band hai.

  Kamakiri class (MT6761/MT6762/MT6765/MT6768/MT6769 — Helio
  A22/P35/G35/G70/G80/G85/G88): BROM mask-ROM exploit — patch-proof.
  V6 class (MT6781/MT6789/MT6855/MT6886/MT6895/MT6983/MT8985):
  BROM patched — DA layer (Carbonara / Heapbait) DA build-date par.
  Transsion NEW SEC (Helio G99/G100/G200 = MT6789 nasal): BROM band,
  META entry khuli hai.
  New-Auth class (NEW_AUTH_TOKENS — Dimensity 6300/6400/7100/7300/
  9000/9400 + MT6835/MT6878/MT6983): META entry signed Auth se gated.

Har qadam: {"door", "status", "note"} — status:
  "open"        — public rasta, shart ke baghair (ya seedha op hai)
  "conditional" — public rasta, shart par (DA build date, signed DA1,
                  unfused unit, test point)
  "server-only" — public implementation nahi; server-signed cheez
                  chahiye (MTKClient ki official line)
  "unknown"     — is chip ke liye koi tasdeeq-shuda rasta nahi

"unknown" kabhi "kuch nahi" ka bahana nahi — ladder hamesha
seedhi dikhata hai, jhoota darwaza kabhi nahi.
"""

from __future__ import annotations

import re

from core.mdm_list import NEW_AUTH_TOKENS

# Kamakiri class — BROM exploit wale purane chips (MTKClient payload).
_KAMAKIRI_CHIPS = ("MT6761", "MT6762", "MT6765", "MT6768", "MT6769")

# V6 protocol chips — BROM patched, sirf preloader + valid DA + UNFUSED
# (MTKClient mod README, research §3.4).
_V6_CHIPS = ("MT6781", "MT6789", "MT6855", "MT6886", "MT6895",
             "MT6983", "MT8985")

# Transsion NEW SEC — Helio G99/G100/G200 (MT6789 nasal). In par
# BROM band hai, META entry khuli hai (Fenix X6886 demo, UMT v3.8).
_NEWSEC_TOKENS = ("MT6789", "HELIO G99", "HELIO G100", "HELIO G200",
                  "DIMENSITY 6080", "DIMENSITY 7020")


def _has(hay, tokens):
    low = hay.lower()
    return any(tok.lower() in low for tok in tokens)


def chip_class(chip_text):
    """Chip text → class: "kamakiri" | "v6" | "newsec" | "new-auth" |
    "unknown". Tartib ahem hai: new-Auth pehle (MT6983 V6 list me
    bhi hai — guard jeet-ta hai), phir newsec (MT6789 V6 list me
    bhi hai — META entry is ki pehchan hai)."""
    hay = str(chip_text or "")
    if not hay.strip():
        return "unknown"
    if _has(hay, NEW_AUTH_TOKENS):
        return "new-auth"
    if _has(hay, _NEWSEC_TOKENS):
        return "newsec"
    if _has(hay, _KAMAKIRI_CHIPS):
        return "kamakiri"
    if _has(hay, _V6_CHIPS):
        return "v6"
    # Helio G35/G70/G80/G85/G88 naam se bhi Kamakiri class hai.
    if re.search(r"helio\s+g(?:35|70|80|85|88)\b", hay, re.I):
        return "kamakiri"
    if re.search(r"helio\s+(?:a22|p35)\b", hay, re.I):
        return "kamakiri"
    return "unknown"


def ladder_for_chip(chip_text, brand=None):
    """Chip ke liye seedhi — qadam tartib se (pehla qadam pehle azmao).

    Har qadam: {"door", "status", "note", "op"} — "op" MEER ke us
    operation ki id hai jo ye qadam chalata hai (ya None, agar
    qadam guide/manual ho)."""
    cls = chip_class(chip_text)
    brand = str(brand or "").strip().lower()

    if cls == "kamakiri":
        return [
            {"door": "Kamakiri — BROM payload",
             "status": "open",
             "note": "Mask-ROM exploit — OTA patch is darwaze ko "
                     "band nahi karta. MTKClient payload se SLA/DAA "
                     "bypass, phir GPT verify.",
             "op": "mtk_bypass_chain"},
            {"door": "MTK ops (FRP / reset / backup)",
             "status": "open",
             "note": "Bypass ke baad MTK tab ke tamam ops usi "
                     "session se chalte hain.",
             "op": "mtk_frp_reset"},
        ]

    if cls == "newsec":
        steps = [
            {"door": "META entry — Transsion NEW SEC",
             "status": "open",
             "note": "BROM band hai, lekin META entry khuli hai "
                     "(Fenix X6886 demo, UMT v3.8 META UBL). MEER "
                     "ka META engine isi par chalta hai.",
             "op": "meta_enter_adb"},
            {"door": "META FRP / UBL (META session ke andar)",
             "status": "open",
             "note": "META session khul jaye to FRP/UBL ka algorithm "
                     "local hai — per-op server auth nahi.",
             "op": "meta_frp_erase"},
            {"door": "DA ladder (Carbonara → Heapbait)",
             "status": "conditional",
             "note": "META na khule to DA rasta: Carbonara (signed "
                     "DA1 chahiye, DA pre-2024) phir Heapbait (DA "
                     "pre-Nov-2024).",
             "op": "mtk_bypass_chain"},
        ]
        return steps

    if cls == "v6":
        return [
            {"door": "Carbonara — DA1 patch (unsigned DA2)",
             "status": "conditional",
             "note": "Signed DA1 chahiye (model ke stock firmware "
                     "se) aur DA Carbonara-patch se purana hona "
                     "chahiye (2024 se pehle wale builds).",
             "op": "mtk_bypass_chain"},
            {"door": "Heapbait — DA2 heap overflow",
             "status": "conditional",
             "note": "Carbonara-patched DA par doosra darwaza — "
                     "sirf jab DA Nov-2024 wale fix se purana ho.",
             "op": "mtk_bypass_chain"},
            {"door": "Preloader + stock DA (unfused)",
             "status": "conditional",
             "note": "Sirf unfused units par — koi patch nahi "
                     "lagta, stock DA chalta hai.",
             "op": "mtk_bypass_chain"},
            {"door": "Fused + DAA/SLA/Remote-Auth active",
             "status": "server-only",
             "note": "Is halat ka koi public rasta documented nahi "
                     "(MTKClient official line) — server-signed DA "
                     "hi darwaza hai.",
             "op": None},
        ]

    if cls == "new-auth":
        return [
            {"door": "META entry",
             "status": "server-only",
             "note": "Is class par META mode me ghusna hi signed "
                     "'new Auth' mangta hai — Transsion ki private "
                     "key se banta hai, koi public implementation "
                     "nahi.",
             "op": None},
            {"door": "DA ladder (Heapbait, DA purana ho to)",
             "status": "conditional",
             "note": "META band hai, lekin DA layer ka rasta zinda "
                     "hai jahan phone ka DA Nov-2024 fix se purana "
                     "ho — bypass chain tartib se try karti hai.",
             "op": "mtk_bypass_chain"},
            {"door": "Test point (physical BROM entry)",
             "status": "conditional",
             "note": "Software entry band ho to physical test point "
                     "se BROM — per-model note tools/testpoints.json "
                     "me dekho.",
             "op": None},
            {"door": "ADB darwaza (phone khulta ho to)",
             "status": "open",
             "note": "Settings se USB debugging ON karke ADB tab ke "
                     "ops — in par META auth ka koi asar nahi.",
             "op": "adb_info"},
        ]

    # unknown — imaandar khaali seedhi nahi: hamesha agla qadam dikhao.
    return [
        {"door": "Chip pehchan (live detection)",
         "status": "unknown",
         "note": "Is chip ka rasta abhi verify nahi hua — phone "
                 "lagao: BROM/Preloader/EDL/ADB se chip live parhi "
                 "jayegi, phir seedhi banegi.",
         "op": "mtk_info"},
        {"door": "Bypass chain (auto-try)",
         "status": "conditional",
         "note": "Chip unknown ho to bhi chain tartib se try karti "
                 "hai — har rasta GPT se verify hota hai, nakli "
                 "success nahi.",
         "op": "mtk_bypass_chain"},
    ]


def ladder_table():
    """Poori seedhi — har class ke liye (op bina device ke dikhaye)."""
    return {
        "Kamakiri class (MT6761/62/65/68/69 — Helio A22/P35/G35/G70/G80/G85/G88)":
            ladder_for_chip("MT6765"),
        "Transsion NEW SEC (Helio G99/G100/G200 — MT6789)":
            ladder_for_chip("MT6789"),
        "V6 class (MT6781/MT6855/MT6886/MT6895/MT6983/MT8985)":
            ladder_for_chip("MT6781"),
        "New-Auth class (Dimensity 6300/6400/7100/7300/9000/9400)":
            ladder_for_chip("Dimensity 7300"),
        "Unknown chip": ladder_for_chip(""),
    }


def open_doors(chip_text, brand=None):
    """Sirf khule/conditional darwaze — op ko 'kya azmaon' ke liye."""
    return [s for s in ladder_for_chip(chip_text, brand)
            if s["status"] in ("open", "conditional")]
