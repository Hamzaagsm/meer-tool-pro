"""
xiaomi_hyperos_unlock_helper.py — Xiaomi HyperOS Bootloader-Unlock
Helper (official path).

GUIDE-ONLY + helper — koi bypass nahi, koi "instant unlock" ka
daawa nahi. Wait server-side hai (server-enforced), is liye koi
tool use khatam nahi kar sakta.

SERVER-REQUIRED-ROUTES-RESEARCH-2 §4.1 / §8.9:
  - Official path (free, server): Mi Community app → apply →
    quiz → account bind → Mi Unlock → 72/168h wait (server
    par lagta hai). Mi account 30+ din purana; approval 3–7
    din; Global: 1 device/year; CN: Level 5 forum + 3
    devices/year.
  - 8 Elite 1-click unlock (XDA 4786790, ~Aug 2026): Snapdragon
    8 Elite, 8s Gen 4, Redmi K80 Ultra, K90 Max, K90 Ultra —
    bina EDL deep flashing (purana tareeqa outdated hai).
  - 8 Elite Gen 5 fastboot exploit (XDA 4781439, 9 Mar 2026):
    Xiaomi 17 series / POCO F8 Ultra / Redmi K90 Pro Max —
    unlock1.bat → fastboot exploit → unlock2.bat → data wipe.
    SHART: security patch Feb 2026 se PEHLE. Global vs CN
    variant — thread me sawal khula hai (unverified).
  - 8 Gen 2 ko ab bhi 9008 EDL deep flashing chahiye.
  - PHP bypass sirf *authorization* requirement skip karta hai
    HyperOS 1 / Global par — WAIT phir bhi rehta hai.
  - "Instant unlock" tools scams hain (TheLeaker 2026: wait
    server-side hai).

MEER ye methods EXECUTE nahi kar sakta (exploit code closed /
Chinese tools par hai) — is liye ye op sirf guided checklist +
per-model + patch-date check deta hai. Koi device zaroori nahi;
device laga ho to chip + patch se rasta batata hai.
"""

from __future__ import annotations

from core import device_watch

OP = {
    "id": "xiaomi_hyperos_unlock_helper",
    "category": "Xiaomi",
    "name": "HyperOS Bootloader Unlock Helper (Official)",
    "engine": "guide",
    "modes": (),
    "server_required": False,
}

# Patch gate: Gen 5 fastboot exploit sirf Feb 2026 se pehle wale
# security patch par (XDA 4781439).
_GEN5_PATCH_CUTOFF = (2026, 2)

# (token, class) — pehle match jeet-ta hai; Gen 5 ko Elite se
# PEHLE check karo ("8 Elite Gen 5" me "8 Elite" bhi hai).
_CLASS_TOKENS = (
    (("SM8850", "8 ELITE GEN 5", "ELITE GEN 5", "XIAOMI 17",
      "POCO F8 ULTRA", "K90 PRO MAX"), "gen5-exploit"),
    (("SM8750", "8 ELITE", "SM8735", "8S GEN 4", "K80 ULTRA",
      "K90 MAX", "K90 ULTRA"), "elite-1click"),
    (("SM8550", "8 GEN 2"), "gen2-edl"),
)


def parse_patch(text):
    """'2026-01-05' → (2026, 1); garbage/khaali → None (pure)."""
    try:
        parts = str(text or "").strip().split("-")
        if len(parts) < 2:
            return None
        year = int(parts[0])
        month = int(parts[1])
        if 2000 <= year <= 2100 and 1 <= month <= 12:
            return (year, month)
    except (ValueError, TypeError):
        return None
    return None


def patch_before_feb2026(patch_text):
    """Patch Feb 2026 se pehle hai? True / False / None (na-maloom)."""
    parsed = parse_patch(patch_text)
    if parsed is None:
        return None
    return parsed < _GEN5_PATCH_CUTOFF


def chip_class(chip_text):
    """Chip/model text → "gen5-exploit" | "elite-1click" |
    "gen2-edl" | "unknown" (pure)."""
    hay = str(chip_text or "").upper()
    if not hay.strip():
        return "unknown"
    for tokens, cls in _CLASS_TOKENS:
        if any(tok in hay for tok in tokens):
            return cls
    return "unknown"


def official_flow_steps():
    """Official unlock flow — checklist (Mi Unlock, free)."""
    return (
        "1. Mi account 30+ din purana hona chahiye (naya account "
        "nahi chalega).",
        "2. Mi Community app install karo → 'Unlock Bootloader' "
        "ke liye apply karo → quiz pass karo.",
        "3. Approval ka intezar: 3–7 din. Global: 1 device/year; "
        "CN: Level 5 forum + 3 devices/year.",
        "4. Phone par: Settings → Developer options → 'Mi Unlock "
        "status' → apna Mi account + device bind karo.",
        "5. PC par official Mi Unlock tool chalao → phone ko "
        "Fastboot mode me lagao → Unlock dabao.",
        "6. WAIT: 72 ghante (kuch models par 168 ghante) — ye "
        "wait Xiaomi ke SERVER par lagta hai, phone ya tool par "
        "nahi. Koi bypass nahi, koi 'instant unlock' nahi — "
        "'instant unlock' tools scams hain.",
        "7. Wait poora hote hi dobara Mi Unlock chalao → unlock "
        "hoga → phone ka DATA WIPE hoga (pehle backup lo).",
    )


def guidance_for(chip_text, patch_text=""):
    """(class, lines) — per-model + patch-date check ke saath."""
    cls = chip_class(chip_text)
    lines = list(official_flow_steps())
    if cls == "elite-1click":
        lines.append(
            "Is chip (Snapdragon 8 Elite / 8s Gen 4) par XDA ke "
            "mutabiq 1-click unlock maujood hai — bina 9008 EDL "
            "deep flashing (purana tareeqa outdated hai). Supported: "
            "8 Elite, 8s Gen 4, Redmi K80 Ultra, K90 Max, K90 Ultra. "
            "Tareeqa XDA thread 4786790 me hai — MEER use execute "
            "nahi kar sakta (exploit code closed tools par hai), "
            "sirf rasta bata sakta hai.")
    elif cls == "gen5-exploit":
        before = patch_before_feb2026(patch_text)
        if before is True:
            lines.append(
                "Is chip (Snapdragon 8 Elite Gen 5 — Xiaomi 17 / "
                "POCO F8 Ultra / Redmi K90 Pro Max) par fastboot "
                "exploit rasta KHULA hai: patch Feb 2026 se pehle "
                f"hai ({patch_text}). XDA thread 4781439: unlock1.bat "
                "→ fastboot exploit → unlock2.bat → data wipe. "
                "Global vs CN variant — thread me sawal khula hai "
                "(unverified).")
        elif before is False:
            lines.append(
                "Is chip (Snapdragon 8 Elite Gen 5) par fastboot "
                "exploit rasta BAND hai: patch Feb 2026 ya us ke "
                f"baad ka hai — exploit us patch par fix ho chuka. "
                "Sirf official flow (upar) bachta hai.")
        else:
            lines.append(
                "Is chip (Snapdragon 8 Elite Gen 5) par fastboot "
                "exploit sirf tab khulta hai jab security patch Feb "
                "2026 se PEHLE ho — patch na-maloom hai, is liye "
                "pehle patch check karo (Settings → About phone → "
                "Android security update).")
    elif cls == "gen2-edl":
        lines.append(
            "Is chip (Snapdragon 8 Gen 2) ko ab bhi 9008 EDL deep "
            "flashing chahiye — 1-click rasta is par nahi. EDL "
            "auth-free window sirf Jan–Apr 2026 patch par thi; us "
            "ke bahar auth server case hai (Xiaomi no-auth EDL op "
            "dekho).")
    else:
        lines.append(
            "Chip is helper ki table me nahi — upar wala official "
            "flow har Xiaomi par wahi hai (Mi Community → quiz → "
            "bind → Mi Unlock → 72/168h wait).")
    lines.append(
        "Yaad rakho: PHP bypass sirf *authorization* requirement "
        "skip karta hai (HyperOS 1 / Global par) — WAIT phir bhi "
        "rehta hai. Wait khatam karne ka koi tareeqa nahi.")
    return cls, lines


def run(ctx) -> bool:
    dev = getattr(ctx, "device", None)
    chip = ""
    patch = ""
    if dev is not None:
        chip = " ".join(str(x or "") for x in
                        (getattr(dev, "chip", ""),
                         getattr(dev, "model", ""),
                         getattr(dev, "brand", ""),
                         getattr(dev, "detail", ""))).strip()
        props = getattr(dev, "raw_props", None) or {}
        patch = str(props.get("ro.build.version.security_patch", "")
                    or "").strip()
        if not patch and getattr(dev, "mode", "") == "ADB":
            ctx.log("Patch ADB props se nahi mili — Settings → About "
                    "phone → Android security update se parho.",
                    "WARN")
    ctx.log("Xiaomi HyperOS bootloader unlock — OFFICIAL FLOW "
            "(guide-only, koi bypass nahi):", "INFO")
    _cls, lines = guidance_for(chip, patch)
    if chip:
        ctx.log(f"Device: {chip}" + (f" · patch {patch}" if patch
                                     else " · patch na-maloom"),
                "INFO")
    for line in lines:
        ctx.log(line, "INFO")
    ctx.progress(95, "HyperOS unlock helper guide mukammal")
    return True
