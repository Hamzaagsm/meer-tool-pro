"""
fastboot_slot.py — A/B Slot Switch (doosra slot active karna).

Usool: pehle `getvar all` se current-slot ASAL me parha jata
hai. Agar current-slot 'a'/'b' me se koi nahi to device A/B
slot wala nahi lagta — wahan op koshish ka natak nahi karta,
saaf wajah ke saath FAIL deta hai. Switch ke baad getvar dobara
parh kar VERIFY kiya jata hai: current-slot asal me target ban
gaya ho tab hi SUCCESS, warna FAIL.
"""

from ops.fastboot_frp import getvar_all, parse_getvar, resolve_fastboot

OP = {
    "id": "fastboot_slot",
    "category": "ADB / Fastboot",
    "name": "Slot Switch (A/B — doosra slot active)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}


def _current_slot(ctx, fb, serial):
    """current-slot ki asal value ya None (jawab na aya ho to)."""
    text = getvar_all(fb, serial)
    data = parse_getvar(text)
    if not data:
        return None
    val = (data.get("current-slot") or "").strip().lower()
    return val


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial

    ctx.progress(25, "current-slot parha ja raha hai...")
    current = _current_slot(ctx, fb, serial)
    if current is None:
        ctx.log("getvar se jawab nahi aya — cable/driver check "
                "karo; slot ki halat ke baghair switch nahi hoga.",
                "ERROR")
        return False
    if current not in ("a", "b"):
        ctx.log(f"getvar me current-slot ki value "
                f"'{current or '(khali)'}' ayi hai — ye device "
                "A/B slot wala nahi lagta (ya bootloader slot ki "
                "maloomat nahi deta). Slot switch is device par "
                "lagu nahi hota.", "ERROR")
        return False

    ctx.log(f"Current slot: {current}", "INFO")
    target = "b" if current == "a" else "a"
    ctx.log(f"Target slot: {target} — ab slot {current} se "
            f"slot {target} active kiya jayega.", "INFO")

    ctx.progress(50, f"slot {target} active ho raha hai...")
    code = ctx.stream([fb, "-s", serial, f"--set-active={target}"],
                      timeout=60)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"Slot switch ka hukum fail hua (exit code "
                f"{code}) — slot tabdeel nahi hua. Upar ke log "
                "me wajah dekho.", "ERROR")
        return False

    ctx.progress(75, "slot switch verify ho raha hai...")
    after = _current_slot(ctx, fb, serial)
    if after is None:
        ctx.log("Switch ke baad getvar se jawab nahi aya — slot "
                "ki nayi halat confirm nahi ho saki, is liye "
                "SUCCESS nahi diya ja raha. Cable laga kar "
                "'Read Device Info (Fastboot)' se current-slot "
                "khud check karo.", "ERROR")
        return False
    if after != target:
        ctx.log(f"Slot switch confirm nahi hua — hukum ke baad "
                f"bhi current-slot '{after}' hai, target "
                f"'{target}' tha. Device ne switch qabool nahi "
                "kiya.", "ERROR")
        return False

    ctx.log(f"Slot switch confirm ho gaya: pehle slot "
            f"'{current}' tha, ab current-slot '{after}' hai "
            f"(target '{target}').", "OK")
    ctx.log("Note: agli reboot par phone naye active slot se "
            "boot hoga. Reboot ke liye 'Reboot (Fastboot → "
            "Normal)' op chalao.", "INFO")
    ctx.progress(95, "Slot switch mukammal")
    return True
