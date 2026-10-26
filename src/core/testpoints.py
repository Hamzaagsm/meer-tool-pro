"""
testpoints.py — Test-point guidance library (Round 7, B9).

SEPT-SEC-RESEARCH §2 Layer 1 + §4-B item 9: September patch ke
baad naye models par BROM software entry (crash preloader /
force BROM) aksar band hai — wahan entry **physical test point**
se hoti hai. Ye module usi ka guided-flow data layer hai:

  - Data file: tools/testpoints.json (user-editable; per-model
    note Hamza apne asal kaam se bharta hai — bilkul MDM models
    DB ki tarah).
  - Public sources se jo milta hai sirf wahi file me pehle se
    darj hai: UMT ke public changelogs ka usool ("Force BROM
    may not work on new security, use Test Point instead").
    Kisi model ki TP location public source ke baghair file me
    NAHI likhi gayi — andaze wali location phone kharab kar
    sakti hai, is liye library jaan-boojh kar khali-but-saaf
    structure ke saath ati hai.
  - guidance_lines(model): model ka note ho to wahi, warna aam
    (generic) TP rehnumai — meta_guard ki ladder aur koi bhi
    guided flow yahi istemal karta hai.
"""

from __future__ import annotations

import json

from core.runner import TOOLS_DIR

TP_FILE = TOOLS_DIR / "testpoints.json"

GENERIC_LINES = (
    "Test point ka aam tareeqa: phone band karo, pichhla cover / "
    "shield ehtiyat se kholo, board par model ke test point "
    "(aksar 'TP' ya sunehra nuqta, battery connector ke qareeb) "
    "ko tweezers se GND se short karte hue USB cable lagao — "
    "Device Manager me MediaTek Preloader/BROM port ana "
    "chahiye. Point milte hi short chhor do.",
    "KHABARDAR: ghalat point short karna board ko mustaqil "
    "kharab kar sakta hai. Is model ki tasdeeq-shuda TP tasveer "
    "hamari library me abhi NAHI hai — pehle kisi bharosa-mand "
    "public source (masalan Hovatek forum ke model thread) se "
    "tasveer match karo, phir hi point chhuo.",
    "Apne kaam se TP tasveer/note mil jaye to yahan jama karo: "
    "tools/testpoints.json me model code ke neeche 'note' aur "
    "'source' likh do — agli dafa ladder khud wahi note "
    "dikhayegi.",
)


def load_library():
    """tools/testpoints.json parho → dict. File na ho / kharab
    ho to khali structure (guidance generic par gir jati hai)."""
    try:
        data = json.loads(TP_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"version": 1, "models": {}}


def note_for(model):
    """Model (dict ya code string) ka TP note dict ya None."""
    if not model:
        return None
    code = model if isinstance(model, str) else (model.get("code") or "")
    if not code:
        return None
    models = load_library().get("models", {})
    entry = models.get(code) or models.get(str(code).upper())
    return entry if isinstance(entry, dict) else None


def lookup(query):
    """Model code ya model naam se entry dhoondo → dict ya None.

    Code exact (case-insensitive) pehle; phir model naam par
    substring match (masalan "Spark 40 Pro+" → KM7). Na mile to
    None — guess nahi, caller imaandar 'nahi mila' jawab deta hai.
    """
    q = str(query or "").strip()
    if not q:
        return None
    models = load_library().get("models", {})
    entry = models.get(q) or models.get(q.upper())
    if isinstance(entry, dict):
        return entry
    low = q.lower()
    for code, entry in models.items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("model", "")).lower()
        brand = str(entry.get("brand", "")).lower()
        if low and (low in name or low in f"{brand} {name}"
                    or low == str(code).lower()):
            return entry
    return None


def lookup_lines(query):
    """Lookup ka imaandar jawab — lines list.

    Entry mile to us ki tafseel (confidence ke saath — unverified
    ho to saaf warning); na mile to 'test point nahi mila' +
    generic rehnumai. Kabhi khali ya andaze wala jawab nahi."""
    entry = lookup(query)
    if entry is None:
        return [
            f"Test point nahi mila — '{query}' is library me nahi hai.",
            "Is ka matlab ye nahi ke point maujood nahi — sirf ye "
            "ke hamari apni DB me abhi darj nahi. Chimera / "
            "UnlockTool ki DB se copy nahi karte — apni DB bench "
            "photos aur public forum posts se bharti hai.",
        ] + list(GENERIC_LINES)
    lines = [
        f"Test point: {entry.get('brand', '')} "
        f"{entry.get('model', '')} ({entry.get('code', '')}) — "
        f"chipset: {entry.get('chipset', 'na-maloom')}.",
        f"Location: {entry.get('location') or entry.get('note', '')}",
    ]
    if entry.get("procedure"):
        lines.append(f"Tareeqa: {entry['procedure']}")
    if entry.get("image"):
        lines.append(f"Tasveer: {entry['image']}")
    if entry.get("source"):
        lines.append(f"Source: {entry['source']}")
    if str(entry.get("confidence", "")).lower() != "verified":
        lines.append(
            "⚠ CONFIDENCE: UNVERIFIED — is point ki location abhi "
            "tasdeeq-shuda NAHI hai. Board par 'TP' print se match "
            "karo ya Hamza ke bench photo se verify karo — andaze "
            "se point short karna board kharab kar sakta hai.")
    else:
        lines.append("Confidence: verified (bench / bharosa-mand source).")
    return lines


def guidance_lines(model=None):
    """Guided flow ke liye lines: model ka apna note ho to pehle
    wahi (source ke saath), phir generic rehnumai ki wo lines jo
    note me shamil nahi."""
    lines = []
    entry = note_for(model)
    if entry:
        note = str(entry.get("note", "")).strip()
        source = str(entry.get("source", "")).strip()
        if note:
            lines.append(f"Is model ka TP note (library se): {note}")
        if source:
            lines.append(f"TP note ka source: {source}")
    lines.extend(GENERIC_LINES)
    return lines
