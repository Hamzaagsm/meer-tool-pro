"""
mtk_reset_only.py — MTKClient se SIRF factory reset (FRP NAHI jayega).

mtk_frp_reset (combined) ka saathi op: jab sirf data saaf karke
factory reset karna ho. Tarteeb: `userdata` (fatal), phir
`metadata` (WARN), phir `persist` (WARN — MDM config note
mtk_frp_reset wali), aakhir me `reset` (WARN).

Saaf hidayat jo log me bhi ati hai: FRP is op se NAHI jayega —
reset ke baad phone pehle wala Google account mangega agar FRP
active tha. FRP ke liye 'FRP Only' ya combined wala op hai.
"""

from core import engines
from core.mtk_serial_fallback import MtkTransport, ensure_mtk_entry
from core.reset_honesty import pre_reset_honesty, result_label
from ops.mtk_frp_reset import _engine, _guard

OP = {
    "id": "mtk_reset_only",
    "category": "MTK",
    "name": "Factory Reset Only (FRP NAHI jayega)",
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

    ctx.log("Is op se SIRF factory reset hoga — FRP NAHI jayega. "
            "Reset ke baad phone pehle wala Google account mangega "
            "agar FRP active tha; FRP ke liye 'FRP Only' ya "
            "combined wala op (FRP Erase + Factory Reset) chalao.",
            "WARN")
    ctx.log("Phone ko cable se mat hatana.", "INFO")
    _hon = pre_reset_honesty(ctx)

    # (a) userdata erase — fail = overall FAIL
    ctx.progress(10, "Userdata erase ho raha hai (factory reset)...")
    ctx.log("Step 1/4: Userdata erase (e userdata) — tamam user "
            "data mit jayega.", "INFO")
    code = transport.stream_step(["e", "userdata"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Userdata erase fail hua (exit code {code}) — "
                "factory reset mukammal nahi hua. Cable aur BROM "
                "mode check karke dobara koshish karo.", "ERROR")
        return False
    ctx.log("Userdata erase ho gaya — data saaf.", "OK")

    # (b) metadata erase — fail = sirf WARN (kuch devices par hota hi nahi)
    ctx.progress(40, "Metadata erase ho raha hai...")
    ctx.log("Step 2/4: Metadata erase (e metadata)", "INFO")
    code = transport.stream_step(["e", "metadata"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Metadata erase nahi hua — kuch devices par "
                "metadata partition hota hi nahi, is liye ye sirf "
                "warning hai, operation aage barh raha hai.", "WARN")
    else:
        ctx.log("Metadata erase ho gaya.", "OK")

    # (c) persist erase — fail = sirf WARN. Kist-band/security-plugin
    # lock ki config isi sakht partition me rehti hai; ye saaf na ho
    # to lock reset ke baad WAPAS zinda ho sakta hai (mtk_frp_reset
    # wali hi wajah).
    ctx.progress(60, "Persist erase ho raha hai (MDM config)...")
    ctx.log("Step 3/4: Persist erase (e persist) — security-plugin "
            "/ kist-band lock ki config is partition me hoti hai; "
            "is ke baghair lock reset ke baad wapas aa sakta hai.",
            "INFO")
    code = transport.stream_step(["e", "persist"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Persist erase nahi hua — kuch devices par persist "
                "partition mehfooz (protected) hota hai ya hota hi "
                "nahi. Reset ho chuka hai, lekin kist-band wala "
                "lock ho to wo wapas aa sakta hai — us surat me "
                "MDM Pack ke partition raste ki zaroorat paregi.",
                "WARN")
    else:
        ctx.log("Persist erase ho gaya — MDM config bhi saaf.", "OK")

    # (d) reset — fail = sirf WARN (asal erase kaam pehle ho chuka hai)
    ctx.progress(85, "Phone reset ho raha hai...")
    ctx.log("Step 4/4: Device reset (reset)", "INFO")
    code = transport.stream_step(["reset"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Reset command fail hua — lekin userdata erase "
                "pehle hi ho chuka hai. Phone ko khud power button "
                "se on karo; pehli boot par kuch minute lag sakte "
                "hain.", "WARN")
    else:
        ctx.log("Phone reset ho gaya — pehli boot par kuch minute "
                "lag sakte hain.", "OK")

    result_label(ctx, _hon)
    ctx.progress(95, "Factory reset mukammal")
    ctx.log("Factory reset mukammal — yaad rahe FRP is op se NAHI "
            "gaya; phone Google account mange to FRP wala op "
            "chalana hoga.", "OK")
    return True
