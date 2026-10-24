"""
mtk_frp_only.py — MTKClient se SIRF FRP erase (factory reset NAHI).

mtk_frp_reset (combined) ka halka saathi op: jab sirf Google
account wala lock (FRP) hatana ho aur user data mehfooz rakhna
ho, to ye op sirf `frp` partition erase karta hai — userdata ko
bilkul NAHI chuta. FRP erase fail ho to FAIL hai; aakhiri reset
ki nakami sirf WARN hai kyun ke asal kaam (erase) pehle ho chuka
hota hai.

Saaf hidayat: is op se MDM / persist NAHI chua jata — kist-band /
security-plugin lock ke liye combined wala op (FRP Erase +
Factory Reset) ya MDM Pack ka rasta hai.
"""

from core import engines
from core.mtk_serial_fallback import MtkTransport, ensure_mtk_entry
from ops.mtk_frp_reset import _engine, _guard

OP = {
    "id": "mtk_frp_only",
    "category": "MTK",
    "name": "FRP Only (Factory Reset NAHI hoga)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


def run(ctx) -> bool:
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    extra = engines.mtk_extra_args()
    # Entry: device pehle se ho to foran; warna cable-only wait
    # (band phone + cable, button zaroori nahi). Na mile to asal
    # _guard ki ERROR rehnumai + False (pehle wala bartao).
    ok, entry_note = ensure_mtk_entry(ctx)
    if not ok and not _guard(ctx):
        return False
    transport = MtkTransport(ctx, cmd, cwd, extra, entry_note=entry_note)
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")

    ctx.log("Is op se SIRF FRP jayega — factory reset NAHI hoga, "
            "user data (apps, photos, accounts) mehfooz rahega.",
            "INFO")
    ctx.log("Note: MDM / persist is op me NAHI chua jata — "
            "kist-band / security-plugin lock ke liye combined "
            "wala op (FRP Erase + Factory Reset) ya MDM Pack "
            "istemal karo.", "INFO")
    ctx.log("Phone ko cable se mat hatana.", "INFO")

    # (a) FRP erase — fail = overall FAIL
    ctx.progress(15, "FRP partition erase ho raha hai...")
    ctx.log("Step 1/2: FRP partition erase (e frp)", "INFO")
    code = transport.stream_step(["e", "frp"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"FRP erase fail hua (exit code {code}). Aam wajahen: "
                "device BROM se nikal gaya, ya DA/auth is chipset ke "
                "liye server-required hai.", "ERROR")
        return False
    ctx.log("FRP partition erase ho gaya.", "OK")

    # (b) reset — fail = sirf WARN (asal erase pehle ho chuka hai)
    ctx.progress(70, "Phone reset ho raha hai...")
    ctx.log("Step 2/2: Device reset (reset)", "INFO")
    code = transport.stream_step(["reset"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Reset command fail hua — lekin FRP erase pehle hi "
                "ho chuka hai. Phone ko khud power button se on "
                "karo; pehli boot par kuch minute lag sakte hain.",
                "WARN")
    else:
        ctx.log("Phone reset ho gaya — pehli boot par kuch minute "
                "lag sakte hain.", "OK")

    ctx.progress(95, "FRP erase mukammal")
    ctx.log("FRP hat gaya — user data mehfooz hai, factory reset "
            "NAHI hua.", "OK")
    return True
