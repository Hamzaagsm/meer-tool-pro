"""
mtk_frp_reset.py — MTKClient se FRP erase + factory reset (userdata/metadata).

Tarteeb: pehle `frp` partition erase, phir `userdata`, phir `metadata`,
phir `persist`, aur aakhir me `reset` taake phone saaf halat me reboot
ho. FRP ya userdata erase fail ho to poora operation FAIL hai — nakli
success kabhi nahi. Metadata/persist kuch devices par hote hi nahi ya
mehfooz hote hain, is liye un ki nakami sirf WARN hai; isi tarah
aakhiri reset ki nakami bhi WARN hai kyun ke asal kaam (erase) us se
pehle ho chuka hota hai.

Persist step ki wajah (FENIX-FEATURES-RESEARCH.md): kist-band /
security-plugin (MDM) lock ki config sakht partitions — khaas tor par
persist — me rehti hai. Persist saaf kiye baghair sirf FRP + hard
reset karne se lock reset ke baad WAPAS zinda ho jata hai; Fenix jaisay
tools ka "hard reset + FRP" asal me in partitions ko bhi saaf karta
hai. Isi liye ye step is flow ka hissa hai.
"""

from core import engines
from core.mtk_serial_fallback import MtkTransport, ensure_mtk_entry
from core.reset_honesty import pre_reset_honesty, result_label
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_frp_reset",
    "category": "MTK",
    "name": "FRP Erase + Factory Reset",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


def _engine(ctx):
    """(cmd_prefix, cwd) ya (None, None) — nakami par guided log de chuka hoga."""
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke engines/mtkclient/ "
                "folder me rakho, ya system me 'mtk' command install karo. "
                "Engine ke baghair ye operation chal hi nahi sakta — "
                "ye nakami nahi, setup ki kami hai.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def _guard(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band karke "
                "Volume dono dabaye hue cable lagao (kuch models par "
                "test-point lagta hai).", "ERROR")
        return False
    return True


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

    ctx.log("FRP erase aur factory reset dono kaam aik hi session me "
            "honge — phone ko cable se mat hatana.", "INFO")
    _hon = pre_reset_honesty(ctx)

    # (a) FRP erase — fail = overall FAIL
    ctx.progress(10, "FRP partition erase ho raha hai...")
    ctx.log("Step 1/5: FRP partition erase (e frp)", "INFO")
    code = transport.stream_step(["e", "frp"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"FRP erase fail hua (exit code {code}). Aam wajahen: "
                "device BROM se nikal gaya, ya DA/auth is chipset ke liye "
                "server-required hai (DESIGN.md ki matrix dekho).", "ERROR")
        return False
    ctx.log("FRP partition erase ho gaya.", "OK")

    # (b) userdata erase — fail = overall FAIL
    ctx.progress(35, "Userdata erase ho raha hai (factory reset)...")
    ctx.log("Step 2/5: Userdata erase (e userdata) — tamam user data "
            "mit jayega.", "INFO")
    code = transport.stream_step(["e", "userdata"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Userdata erase fail hua (exit code {code}) — factory "
                "reset mukammal nahi hua. Cable aur BROM mode check karke "
                "dobara koshish karo.", "ERROR")
        return False
    ctx.log("Userdata erase ho gaya — data saaf.", "OK")

    # (c) metadata erase — fail = sirf WARN (kuch devices par hota hi nahi)
    ctx.progress(60, "Metadata erase ho raha hai...")
    ctx.log("Step 3/5: Metadata erase (e metadata)", "INFO")
    code = transport.stream_step(["e", "metadata"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Metadata erase nahi hua — kuch devices par metadata "
                "partition hota hi nahi, is liye ye sirf warning hai, "
                "operation aage barh raha hai.", "WARN")
    else:
        ctx.log("Metadata erase ho gaya.", "OK")

    # (d) persist erase — fail = sirf WARN. Kist-band/security-plugin
    # lock ki config isi sakht partition me rehti hai; ye saaf na ho to
    # FRP + reset ke bawajood lock wapas zinda ho sakta hai.
    ctx.progress(75, "Persist erase ho raha hai (MDM config)...")
    ctx.log("Step 4/5: Persist erase (e persist) — security-plugin / "
            "kist-band lock ki config is partition me hoti hai; is ke "
            "baghair lock reset ke baad wapas aa sakta hai.", "INFO")
    code = transport.stream_step(["e", "persist"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Persist erase nahi hua — kuch devices par persist "
                "partition mehfooz (protected) hota hai ya hota hi "
                "nahi. FRP/reset ho chuke hain, lekin kist-band wala "
                "lock ho to wo wapas aa sakta hai — us surat me MDM "
                "Pack ke partition raste ki zaroorat paregi.", "WARN")
    else:
        ctx.log("Persist erase ho gaya — MDM config bhi saaf.", "OK")

    # (e) reset — fail = sirf WARN (asal erase kaam pehle ho chuka hai)
    ctx.progress(88, "Phone reset ho raha hai...")
    ctx.log("Step 5/5: Device reset (reset)", "INFO")
    code = transport.stream_step(["reset"], timeout=180)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("Reset command fail hua — lekin FRP aur userdata erase "
                "pehle hi ho chuke hain. Phone ko khud power button se "
                "on karo; pehli boot par kuch minute lag sakte hain.", "WARN")
    else:
        ctx.log("Phone reset ho gaya — pehli boot par kuch minute lag "
                "sakte hain.", "OK")

    result_label(ctx, _hon)
    ctx.progress(95, "FRP erase + factory reset mukammal")
    return True
