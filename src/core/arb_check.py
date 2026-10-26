"""arb_check.py — ColorOS 16 hardware ARB-fuse check (Round 2, Group 6).

SERVER-REQUIRED-ROUTES-RESEARCH-2 §4.2(b) / §9.12 / §11.5:
ColorOS 16.0.3.500 / .501 / .503 (Android 16) update karte hi
QFPROM eFuse blow hota hai — purana ROM / custom ROM flash =
HARD BRICK, motherboard replacement hi rasta. "Previously
developed unauthorized 9008 tools and Chimera firehose
programmers will FAIL because the fuse has been blown."
Affected: OnePlus 13, 13T, 15, Ace 5, Ace 5 Pro (CN builds;
OxygenOS same codebase — international par aane ka khatra).

CONFLICT (dono likhne hain, ek ko chhupana nahi):
  - XDA / Notebookcheck / 9to5Google / Android Authority:
    fuse HARDWARE hai — permanent, wapas nahi hota.
  - OnePlus ka jawab (27 Jan 2026, Android Authority ko
    statement): "we've temporarily paused the ability to
    downgrade from 16.0.2.50x software builds to older builds.
    We will be restoring the ability to downgrade… in our next
    routine software update."
  Fuse hardware hai (wapas nahi hota), lekin OnePlus kehta hai
  downgrade wapas ayega — UNRESOLVED CONFLICT. MEER is liye
  fused phone par EDL flash se PEHLE fuse check ki warning
  deta hai, aur fused ko "downgrade ho jayega" keh kar nahi
  dikhata.

Pure helpers — GUI/op se azad, logic tests in par chalte hain.
"""

from __future__ import annotations

import re

# Build 16.0.3.500 se fuse blown mana jata hai (research §4.2b).
FUSED_FROM = (16, 0, 3, 500)

# Fuse wale models (research §4.2b — sirf yehi list, andaza nahi).
AFFECTED_MODELS = (
    "OnePlus 13",
    "OnePlus 13T",
    "OnePlus 15",
    "OnePlus Ace 5",
    "OnePlus Ace 5 Pro",
)

_VERSION_RE = re.compile(r"(\d+(?:\.\d+){2,3})")

_CONFLICT_NOTE = (
    "CONFLICT (dono sach likhe ja rahe hain): XDA ke mutabiq ARB "
    "fuse HARDWARE hai — permanent, wapas nahi hota. OnePlus ka "
    "jawab (27 Jan 2026, Android Authority): downgrade 'temporarily "
    "paused' hai aur 'next routine software update' me wapas ayega. "
    "Fuse hardware hai to downgrade kaise wapas ayega — ye sawal "
    "abhi HAL NAHI HUA. Jab tak OnePlus ka update waqai downgrade "
    "wapas na la de, fused phone ko FUSED hi mano."
)


def parse_version(text):
    """Build string se (major, minor, patch, build) tuple ya None.

    "16.0.3.500" → (16, 0, 3, 500); "ColorOS 16.0.2.505" →
    (16, 0, 2, 505); "CPH2653_16.0.3.501" → (16, 0, 3, 501).
    Teen hisse hon to chautha 0 mana jata hai."""
    if not text:
        return None
    m = _VERSION_RE.search(str(text))
    if not m:
        return None
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def fuse_status(build_text):
    """Build string → "fused" | "not-fused" | "unknown".

    >= 16.0.3.500 → fused. Us se neeche (masalan 16.0.2.50x) →
    not-fused. Version parhi na ja sake → unknown (guess nahi)."""
    ver = parse_version(build_text)
    if ver is None:
        return "unknown"
    return "fused" if ver >= FUSED_FROM else "not-fused"


def is_affected_model(model_text):
    """Model fuse wali list me hai ya nahi (case-insensitive).

    Word-boundary match — "OnePlus 13" likha ho to True, lekin
    "OnePlus 13R" is list me NAHI (research me us ka zikr nahi,
    is liye andaze se affected nahi kehte). "OnePlus 13T" apni
    entry se match karta hai (lambi entry pehle check hoti hai)."""
    hay = str(model_text or "").strip().lower()
    if not hay:
        return False
    for model in sorted(AFFECTED_MODELS, key=len, reverse=True):
        pattern = re.escape(model.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, hay):
            return True
    return False


def arb_warning_lines(status, build_text=""):
    """Fuse status ki warning lines (guide op + EDL flash link
    dono istemal karte hain)."""
    ver = parse_version(build_text)
    ver_txt = ".".join(str(p) for p in ver) if ver else "na-maloom"
    lines = [f"Build version: {build_text or 'na-maloom'} "
             f"(parsed: {ver_txt}) — fuse check line: "
             f"16.0.3.500+ = fused."]
    if status == "fused":
        lines += [
            "⛔ FUSED — is phone par ARB fuse blow ho chuka hai.",
            "Purana ROM / custom ROM / EDL se purana firmware flash "
            "= HARD BRICK. Fused phone par EDL unbrick rasta BAND hai "
            "— server bhi nahi, MOTHERBOARD hi rasta hai.",
            "Is phone par sirf usi ya naye build ka ROM flash karo; "
            "downgrade ki koshish mat karo.",
            _CONFLICT_NOTE,
        ]
    elif status == "not-fused":
        lines += [
            "✅ NOT-FUSED (abhi tak) — build 16.0.3.500 se neeche hai, "
            "fuse abhi blow nahi hua.",
            "KHABARDAR: 16.0.3.500+ update karte hi fuse blow ho "
            "jayega — update se pehle customer ko batao, aur update "
            "ke baad dobara check karo.",
        ]
    else:
        lines += [
            "❓ FUSE STATUS UNKNOWN — build version parhi nahi ja saki.",
            "EDL flash se PEHLE build version check karo (Settings → "
            "About phone → Version, ya ADB se). Bina fuse check ke "
            "OnePlus 13 / 13T / 15 / Ace 5 / Ace 5 Pro par purana "
            "ROM flash mat karo — fused nikla to hard brick hoga.",
            _CONFLICT_NOTE,
        ]
    return lines


def check_build(build_text, model_text=""):
    """Aik call me poora faisla: {status, version, affected, lines}."""
    status = fuse_status(build_text)
    return {
        "status": status,
        "version": parse_version(build_text),
        "affected_model": is_affected_model(model_text),
        "lines": arb_warning_lines(status, build_text),
    }
