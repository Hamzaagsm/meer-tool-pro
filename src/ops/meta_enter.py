"""
meta_enter.py — MTKClient se phone ko META mode me bhejna + asal
META port ki verification.

Do hisay: (1) MTKClient ka `meta usb` command stream hota hai taake
phone BROM/Preloader se META mode me chala jaye; (2) phir tool 45
second tak asal META port (VID 0x0E8D) ka intezaar karta hai.
SUCCESS sirf tab hai jab META port asal me nazar ajaye — command ka
exit code akela kabhi success nahi mana jata. Port na mile to saaf
FAIL, driver/cable ki hidayat ke saath.
"""

import time

from core import engines, meta_session

OP = {
    "id": "meta_enter",
    "category": "MDM / Transsion",
    "name": "Enter META Mode (MTKClient → META port verify)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}

_POLL_SECONDS = 45
_POLL_INTERVAL = 1.5


def _engine(ctx):
    """(cmd_prefix, cwd) ya (None, None) — nakami par guided log de chuka hoga."""
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke "
                "engines/mtkclient/ folder me rakho. Engine ke baghair "
                "META mode me bhejna mumkin nahi.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band "
                "karke Volume dono dabaye hue cable lagao (kuch models "
                "par test-point lagta hai) — META mode ka safar wahin "
                "se shuru hota hai.", "ERROR")
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    ctx.progress(10, "MTKClient se META mode ka hukum bheja ja raha hai...")
    ctx.log("MTKClient 'meta usb' chala rahe hain — phone ko META "
            "mode me bhejne ka hukum.", "INFO")
    code = ctx.stream(cmd + ["meta", "usb"] + engines.mtk_extra_args(),
                      timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"MTKClient exit code {code} ke saath band hua — phir "
                "bhi META port ki asal verification hogi; port ajaye "
                "to hi kaam bane ga.", "WARN")
    ctx.progress(35, "META port ka intezaar...")

    pyserial_note = None
    start = time.monotonic()
    while True:
        if ctx.is_cancelled():
            return False
        elapsed = time.monotonic() - start
        if elapsed > _POLL_SECONDS:
            break
        ctx.progress(35 + int(elapsed / _POLL_SECONDS * 60),
                     "META port ka intezaar...")
        try:
            port = meta_session.find_meta_port()
        except meta_session.MetaError as e:
            pyserial_note = str(e)
            port = None
        if port is not None:
            desc = getattr(port, "description", "") or "MediaTek META"
            ctx.progress(95, "META port mil gaya")
            ctx.log(f"META port asal me mil gaya: {port.device} "
                    f"({desc}) — phone META mode me hai. Ab META "
                    "session wale ops (Read Info / Factory Reset / "
                    "Enable ADB) chal sakte hain.", "OK")
            return True
        deadline = time.monotonic() + _POLL_INTERVAL
        while time.monotonic() < deadline:
            if ctx.is_cancelled():
                return False
            time.sleep(0.2)

    if pyserial_note:
        ctx.log(pyserial_note, "ERROR")
    ctx.log("META port 45 second me nazar nahi aya — phone META mode "
            "me nahi gaya. Wajahen check karo: (1) MediaTek VCOM/USB "
            "driver laga hai ya nahi (driver na ho to port banta hi "
            "nahi), (2) cable asal data cable ho, charge-only na ho, "
            "(3) phone poori tarah band halat me Volume dono dabaye "
            "hue lagaya gaya ho, (4) kuch models par META entry ke "
            "liye test-point ya new Auth lag sakta hai — naye "
            "Dimensity par ye rasta server-required ho sakta hai.",
            "ERROR")
    return False
