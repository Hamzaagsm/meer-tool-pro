"""
meta_guard.py — New-Auth guard ka LADDER version (Round 7, B7).

SEPT-SEC-RESEARCH §4-B item 7: purana new-Auth guard (mdm_list ka
`_new_auth_guard`, aur meta_* ops ke local `_new_auth_blocked`)
FLAT rukta tha — wajah de kar khatam. Ladder wahi guard hai, lekin
rukne ke saath **doosra zinda darwaza khud offer** karta hai:

  Seedhi 1 — DA / Heapbait darwaza (Download route): vendored
             MTKClient ki bypass chain (payload → carbonara →
             heapbait → stock DA) Group A par bhi zinda hai jahan
             DA Nov-2024 fix se purana ho (research §2 Layer 2).
  Seedhi 2 — Test-point guidance: BROM software entry band ho to
             physical test point (research §2 Layer 1) — per-model
             note tools/testpoints.json library se (core.testpoints),
             na ho to aam rehnumai + library me data jorne ka tareeqa.
  Seedhi 3 — ADB darwaza: phone khulta ho to settings se USB
             debugging — hamesha imaandar akhri mashwara.

Guard ka usool nahi badla: new-Auth class (Dimensity 6300/6400/
7300/9000/9400 — core.mdm_list.NEW_AUTH_TOKENS) par META entry
server-signed authorization mangti hai jo public nahi; wahan META
op rukta hi hai. Ladder sirf itna karta hai ke user mare hue
raste par khara na rahe — wajah ke saath agli seedhi samne ho.
"""

from __future__ import annotations

from core.mdm_list import NEW_AUTH_TOKENS


def new_auth_hit(*texts):
    """Diye gaye texts (chipset/chip/model/detail) me new-Auth
    token mile to wahi token wapas, warna None. Pure function —
    bench ke baghair test ho sakta hai."""
    hay = " ".join(str(t or "") for t in texts).lower()
    for tok in NEW_AUTH_TOKENS:
        if tok.lower() in hay:
            return tok
    return None


def hit_for(ctx, model=None):
    """ctx.device + (ho to) muntakhib model se new-Auth hit."""
    dev = getattr(ctx, "device", None)
    texts = []
    if model:
        texts += [model.get("chipset", ""), model.get("name", ""),
                  model.get("code", "")]
    if dev is not None:
        texts += [getattr(dev, "chip", ""), getattr(dev, "model", ""),
                  getattr(dev, "detail", ""),
                  getattr(dev, "brand", "")]
    return new_auth_hit(*texts)


def ladder_stop(ctx, hit, model=None):
    """New-Auth wajah + doosre darwaze ki seedhi log karo.

    Hamesha False wapas karta hai — caller (op) isay apna return
    bana le (guard fail = op fail, lekin user ke samne rasta ho).
    """
    ctx.log(f"🔒 SERVER REQUIRED — chip pehchana gaya: {hit}. Is "
            "class (Dimensity 6300/6400/7300/9000 family) par META "
            "mode me ghusna hi signed 'new Auth' mangta hai — wo "
            "authorization Transsion ki private key se banti hai, "
            "tools use apne server se dete hain, aur koi public / "
            "free implementation maujood NAHI hai (SEPT-SEC "
            "research §3/§5). Is liye META wala ye op yahan ruk "
            "raha hai — jhooti koshish ya nakli success nahi "
            "hogi.", "ERROR")
    ctx.log("— Lekin darwaza yahin khatam NAHI hota. Isi phone ke "
            "liye doosri seedhiyan maujood hain:", "WARN")

    # Seedhi 1 — DA / Heapbait (Download route)
    tags = {str(t).upper() for t in (model or {}).get("tags", [])}
    if not model or (tags & {"MDL", "PL", "DA", "TMETA"}):
        ctx.log("Seedhi 1 — DOWNLOAD (DA) darwaza: META band hai, "
                "lekin DA layer ka rasta is class par bhi zinda "
                "hai jahan phone ka DA Nov-2024 wale fix se "
                "purana ho. MTK tab ka 'Latest Bypass (Auto)' op "
                "chalao — chain khud tartib se try karti hai: "
                "BROM payload → Carbonara → **Heapbait** (Carbonara-"
                "patched DA ke liye public exploit, hamare vendored "
                "MTKClient me shamil hai) → stock DA. Bypass ke "
                "baad FRP/reset/backup ke tamam MTK ops usi "
                "session se chalte hain.", "INFO")
    # Seedhi 2 — Test point
    ctx.log("Seedhi 2 — TEST POINT: naye security par software se "
            "BROM entry (crash preloader / force BROM) aksar band "
            "hoti hai; wahan entry physical test point se hoti "
            "hai (research §2 Layer 1).", "INFO")
    try:
        from core import testpoints
        for line in testpoints.guidance_lines(model):
            ctx.log(line, "INFO")
    except Exception:  # noqa: BLE001 — guidance ki nakami guard ko nahi rok sakti
        pass
    # Seedhi 3 — ADB
    ctx.log("Seedhi 3 — ADB darwaza: agar phone on hota hai aur "
            "screen khulti hai to Settings → Developer options se "
            "USB debugging ON karke ADB tab ke ops (info, app "
            "profiles, Security Plugin remove waghera) chal "
            "sakte hain — in par META auth ka koi asar nahi.",
            "INFO")
    ctx.log("Note: jaise hi is class ke liye koi public darwaza "
            "niklega, wo pehle MEER Tool Pro me ayega (standing "
            "rule). Tab tak ye teen seedhiyan hi asal raste "
            "hain.", "INFO")
    return False


def guard_or_ladder(ctx, model=None):
    """TMETA ops ka mushtaraka darwaza.

    True  = new-Auth class nahi — aage barho.
    False = hit mila; ladder log ho chuka hai — op ruk jaye.
    """
    hit = hit_for(ctx, model)
    if not hit:
        return True
    return ladder_stop(ctx, hit, model=model)
