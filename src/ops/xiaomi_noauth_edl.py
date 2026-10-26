"""
xiaomi_noauth_edl.py — Xiaomi No-Auth EDL — FRP Erase (Free).

SERVER-REQUIRED research §4.2: Xiaomi ke purane Qualcomm chips
par EDL auth public tareeqe se skip hota hai — `sig.bin` +
patched (no-auth) loader se. Naye locked Xiaomi par auth
handshake Xiaomi ke server se hota hai (server case).

  No-auth chips (public, sabit — Droidwin/XDA): Snapdragon
  636/660/665/675/680/710/712/730/845/855/860/870 class
  (Redmi Note 5/6/7/8, Mi 8/9, POCO F1/F3 waghera).
  Auth-free window (XDA Apr 2026, TANG window): Snapdragon
  8 Elite / 8 Gen 2 — sirf security patch Jan–Apr 2026 ki
  window me, Deep Flash Cable + downgrade mini-package ke
  saath; Kioxia (Toshiba) UFS supported nahi.

Flow (MEER ke apne engine me — koi bahari tool nahi):
  1. Device EDL (9008) me hona lazmi.
  2. No-auth loader No-Auth Slot se chuna jata hai (technician
     ne diya hua patched loader) — brand/chip match, ya slot
     me AKEla loader ho to wahi (saaf marzi).
  3. Tasdeeq: `edl printgpt` — loader baghair auth ke chala to
     hi aage barhte hain (yehi no-auth ka saboot hai).
  4. FRP erase GPT-driven (qc_edl_frp v2 wala usool: frp /
     persistent / config — `persist` kabhi nahi).

Imaandari: chip EDL mode me aksar pata nahi chalta (props
nahi milte) — is liye chip-class sirf maloomat hai, rok nahi.
Asal faisla loader ki tasdeeq (printgpt) karta hai. Naya
locked Xiaomi (auth handshake) is op se nahi hoga — wahan
server case saaf likha jayega.
"""

from __future__ import annotations

from core import engines, gpt_parse, loader_library

OP = {
    "id": "xiaomi_noauth_edl",
    "category": "Xiaomi",
    "name": "Xiaomi No-Auth EDL — FRP Erase (Free, purane chips)",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
}

# Public no-auth chips (research §4.2) — platform tokens.
NOAUTH_CHIPS = (
    "SDM636", "SDM660", "SDM665", "SM6125", "SDM675", "SM6150",
    "SDM710", "SDM712", "SDM730", "SDM845", "SDM855", "SDM860",
    "SDM870", "SM6225",
)

# Auth-free window chips (XDA Apr 2026) — tang patch window.
WINDOW_CHIPS = {
    "SM8550": "Snapdragon 8 Gen 2",
    "SM8750": "Snapdragon 8 Elite",
}

_WINDOW_NOTE = (
    "Is chip (8 Gen 2 / 8 Elite) par auth-free EDL sirf security "
    "patch Jan–Apr 2026 ki window me public hai — Deep Flash Cable "
    "+ downgrade mini-package chahiye; Kioxia (Toshiba) UFS "
    "supported nahi. Window se bahar ho to ye rasta band hai.")

_CRASH_CODES = (3221225477, -1073741819)  # 0xC0000005 dono suraton me

_CRASH_LINE = (
    "Engine crash hua (0xC0000005) — ye phone ka masla nahi, PC ke "
    "USB driver layer ka hai: UsbDk hatao + VCOM/filter setup karo "
    "(UTILITY → Install Drivers)."
)


def chip_class(chip_text):
    """Chip text → "noauth" | "window" | "unknown" (pure).

    "unknown" ka matlab sirf ye hai ke chip no-auth table me
    nahi — is se op nahi rukta, loader ki tasdeeq faisla karti
    hai."""
    hay = str(chip_text or "").upper()
    if not hay.strip():
        return "unknown"
    for tok in NOAUTH_CHIPS:
        if tok in hay:
            return "noauth"
    for tok in WINDOW_CHIPS:
        if tok in hay:
            return "window"
    return "unknown"


def _pick_noauth_loader(ctx, brand, hint):
    """No-auth loader chunna — (Path|None). Niyam pick_qualcomm_loader
    jaisi hi sakhti: tier ≤2 ka AKELA saaf match, ya slot me AKELA
    loader (technician ki saaf marzi). Barabar candidates par khud
    nahi chunte."""
    ranked = loader_library.match_noauth(brand, hint)
    if ranked:
        top_tier = ranked[0]["tier"]
        tops = [r for r in ranked if r["tier"] == top_tier]
        if top_tier <= 2 and len(tops) == 1:
            pick = tops[0]
            ctx.log(f"No-auth loader: {pick['path'].name} — "
                    f"{pick['why']}", "INFO")
            return pick["path"]
        names = ", ".join(f"{r['path'].name} ({r['why']})"
                          for r in tops[:6])
        ctx.log(f"No-auth slot me {len(tops)} barabar ke loader "
                f"candidates mile — galat loader khud NAHI chuna "
                f"gaya: {names}. Sahi wala khud rakhna ho to baqion "
                f"ko kuch dair ke liye slot se hata do.", "WARN")
        return None
    all_noauth = loader_library.noauth_entries()
    if len(all_noauth) == 1:
        p = loader_library.entry_abspath(all_noauth[0])
        ctx.log(f"Slot me akela no-auth loader hai — wahi istemal "
                f"ho raha hai: {p.name} (chip hint nahi mila, "
                f"technician ki marzi saaf hai).", "INFO")
        return p
    if not all_noauth:
        ctx.log("No-Auth slot khali hai — koi no-auth loader darj "
                "nahi.", "ERROR")
    else:
        ctx.log(f"Slot me {len(all_noauth)} no-auth loaders hain "
                "lekin device se match nahi ho saka — sirf sahi "
                "wala slot me rakho, ya brand/chip wale folder "
                "naam se dobara darj karo.", "WARN")
    ctx.log("Guide: 'No-Auth Loader Slot (Technician)' op se apna "
            "patched loader darj karo (tools/loaders-noauth/ me "
            "rakho) — phir ye op dobara chalao.", "WARN")
    return None


def run(ctx) -> bool:
    dev = getattr(ctx, "device", None)
    if not dev or getattr(dev, "mode", None) != "EDL":
        ctx.log("Device EDL (9008) mode me nahi mila. Phone band karke "
                "Volume Up+Down dono dabaye hue cable lagao — Device "
                "Manager me 'Qualcomm HS-USB QDLoader 9008' ana chahiye.",
                "ERROR")
        return False

    cmd, cwd, note = engines.find_edl()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("EDL client"):
                ctx.log(line, "WARN")
        else:
            ctx.log(note, "ERROR")
            ctx.log("Guide: engines/edl/ me edl client ki copy honi "
                    "chahiye.", "WARN")
        return False
    ctx.log(note, "INFO")

    brand = getattr(dev, "brand", "") or ""
    hint = " ".join(str(x or "") for x in
                    (getattr(dev, "chip", ""),
                     getattr(dev, "detail", ""),
                     getattr(dev, "model", "")))
    cls = chip_class(hint)
    if cls == "window":
        ctx.log(_WINDOW_NOTE, "WARN")
    elif cls == "unknown" and hint.strip():
        ctx.log("Chip no-auth table me nahi mila — is chip par "
                "no-auth rasta public documented nahi. Phir bhi "
                "loader ki tasdeeq (printgpt) faisla karegi; na "
                "chala to ye server-auth case hoga.", "WARN")
    elif cls == "noauth":
        ctx.log("Chip no-auth table me hai — public no-auth rasta "
                "khula hona chahiye.", "OK")

    loader = _pick_noauth_loader(ctx, brand or "Xiaomi", hint)
    if loader is None:
        return False
    ctx.log(f"Loader: {loader}", "INFO")

    # --- Tasdeeq: printgpt = no-auth ka saboot --------------------------
    ctx.progress(15, "Loader tasdeeq (printgpt — no-auth saboot)...")
    code = ctx.stream(cmd + ["printgpt", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code in _CRASH_CODES:
        ctx.log(_CRASH_LINE, "ERROR")
        return False
    if code != 0:
        ctx.log(f"Loader tasdeeq nakam (exit code {code}) — no-auth "
                "loader is device par accept nahi hua.", "ERROR")
        ctx.log("Aam wajahen: loader is model/chip ka nahi hai; "
                "chip naya locked hai (auth handshake = server "
                "case); ya 9008 driver/cable ka masla hai.",
                "WARN")
        ctx.log("Doosra darwaza: sahi model ka patched loader slot "
                "me darj karo; naya locked Xiaomi ho to ye server "
                "wala kaam hai (authorized account).", "INFO")
        return False
    ctx.log("✔ Loader baghair auth ke chal gaya — no-auth rasta "
            "tasdeeq-shuda hai.", "OK")

    # --- GPT-driven FRP erase (qc_edl_frp v2 wala usool) -----------------
    from ops.qc_edl_frp import _read_gpt
    tables = _read_gpt(ctx, cmd, cwd, loader)
    if tables is None:
        return False
    if ctx.is_cancelled():
        return False

    plans = {}
    refusals = []
    for lun in sorted(tables):
        erase, refusal = gpt_parse.frp_erase_plan(tables[lun])
        if erase:
            plans[lun] = erase
        elif refusal:
            refusals.append((lun, refusal))
    if not plans:
        for lun, (rcode, wajah) in refusals:
            ctx.log(f"LUN {lun}: {wajah}", "ERROR")
        ctx.log("FRP erase NAHI hua — upar wajah wazeh hai.", "ERROR")
        return False
    for lun, (rcode, wajah) in refusals:
        ctx.log(f"LUN {lun}: {wajah} (is LUN par kuch nahi mita)",
                "WARN")

    erased = []
    total = sum(len(v) for v in plans.values())
    done = 0
    for lun in sorted(plans):
        for name in plans[lun]:
            if ctx.is_cancelled():
                return False
            done += 1
            ctx.progress(30 + int(60 * done / max(total, 1)),
                         f"{name} erase ho raha hai (LUN {lun})...")
            ctx.log(f"Erase: {name} (LUN {lun})", "INFO")
            code = ctx.stream(
                cmd + ["e", name, f"--lun={lun}", f"--loader={loader}"],
                timeout=300, cwd=cwd)
            if code != 0:
                ctx.log(f"{name} erase fail hua (exit code {code}). "
                        f"Ab tak erase hue: "
                        f"{', '.join(erased) if erased else 'koi nahi'}",
                        "ERROR")
                return False
            erased.append(f"{name}@LUN{lun}")
            ctx.log(f"{name} erase ho gaya.", "OK")
    ctx.log("FRP erase mukammal — ye partitions mitaye gaye: "
            + ", ".join(erased), "OK")
    ctx.progress(95, "FRP erase mukammal (no-auth EDL)")
    return True
