"""
moto_fastboot_frp.py — Motorola par Fastboot se FRP erase (LOCKED bootloader par bhi).

Gap jo ye band karta hai (ROUND-5-RESEARCH §1 — EFT Pro v5.6.6 parity):
EFT Pro deta hai "[MOTO - Fastboot] FRP Erase Only (bootloader LOCKED
rehta hai)". Rasta sirf public fastboot protocol hai — Motorola ka
fastboot implementation aksar models par `fastboot erase frp` ko
LOCKED bootloader ke bawajood chalne deta hai (aksar vendors ke
baraks jahan erase sirf unlocked par hota hai).

Usool:
- Pehle getvar se BRAND confirm hota hai (product / manufacturer me
  "motorola"/"moto"). Motorola nahi mila to op FAIL deta hai aur
  aam fastboot FRP op ki taraf bhejta hai — koi andhi koshish nahi.
- Unlock check YAHAN NAHI hai — ye op ka maksad hi yehi hai ke
  locked bootloader par bhi chal sakta hai (EFT parity).
- Single-purpose: sirf "frp" erase hota hai — "config" erase ki
  koshish tak nahi hoti (EFT ke "FRP Erase Only" ki tarah).
- Lock rehta hai: ye op bootloader ko khud unlock nahi karta.
"""

from ops.fastboot_frp import (
    getvar_all,
    parse_getvar,
    resolve_fastboot,
)

OP = {
    "id": "moto_fastboot_frp",
    "category": "ADB / Fastboot",
    "name": "FRP Erase (Motorola Fastboot \u2014 Locked BL OK)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}

_BRAND_HINTS = ("motorola", "moto")


def is_motorola(data):
    """True / False (pure) — getvar ke product/manufacturer se brand check."""
    text = " ".join(
        (data or {}).get(k, "") for k in ("product", "manufacturer")
    ).lower()
    return any(h in text for h in _BRAND_HINTS)


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial
    ctx.log("Motorola brand check (getvar product/manufacturer)...")
    text = getvar_all(fb, serial)
    data = parse_getvar(text)
    if not data:
        ctx.log("getvar se jawab nahi aya — cable/driver check karo; "
                "brand confirm kiye baghair ye op nahi chalega.", "ERROR")
        return False
    product = data.get("product", "")
    manufacturer = data.get("manufacturer", "")
    if not is_motorola(data):
        ctx.log(f"Ye op sirf Motorola devices ke liye hai (getvar me "
                f"motorola nahi mila: product={product!r}, "
                f"manufacturer={manufacturer!r}). Doosre brands ke "
                f"liye aam 'FRP Erase (Fastboot, unlocked only)' op "
                f"istemal karo.", "ERROR")
        return False
    ctx.log(f"Motorola device confirm hua (product={product!r}, "
            f"manufacturer={manufacturer!r}).", "OK")
    ctx.log("EFT-parity note: is op me unlock check NAHI hai — "
            "Motorola ke fastboot par FRP erase locked bootloader par "
            "bhi chalta hai (public protocol; EFT Pro bhi yahi rasta "
            "deta hai). Bootloader locked hi rahega, khud unlock "
            "nahi hoga.", "INFO")
    ctx.progress(45, "Motorola frp erase ho raha hai...")
    code = ctx.stream([fb, "-s", serial, "erase", "frp"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"frp erase fail hua (exit code {code}) — is "
                "model/par locked-fastboot variant par ye command "
                "blocked ho sakta hai. Phir BROM/EDL wala rasta dekho "
                "(chipset ke hisaab se: Motorola MTK par MTK wali "
                "FRP ops, Snapdragon par QC EDL ops).", "ERROR")
        return False
    ctx.log("Motorola FRP erase mukammal. Phone reboot karke setup "
            "check karo — purana Google account nahi mangna chahiye. "
            "Bootloader locked hi rahega (reboot ke baad fastboot "
            "me getvar se verify kar sakte ho).", "OK")
    ctx.progress(95, "Motorola FRP erase mukammal")
    return True
