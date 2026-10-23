"""
fastboot_slot.py — A/B Slot Switch (chuna hua slot active karna).

PAID-TOOLS-TEARDOWN ki fehrist ka item (A/B slot, [PUBLIC-METHOD]).
Usool: pehle `getvar all` se current-slot ASAL me parha jata hai.
Agar current-slot 'a'/'b' me se koi nahi to device A/B slot wala
nahi lagta — wahan op koshish ka natak nahi karta, saaf wajah ke
saath FAIL deta hai.

Target slot:
  - ctx.params me 'slot' = 'a'/'b' diya gaya ho to WAHI slot
    (GUI ke PARAMS bar me filhal sirf numeric fields hain, is
    liye GUI se ye value nahi ati — programmatic istemal aur
    aayenda ke GUI field ke liye rasta khula rakha gaya hai).
  - Warna default: doosra slot (jo active nahi hai wahi active
    hoga — is op ka roz ka kaam yahi hai).

Command: `fastboot set-active <slot>`; purane fastboot builds
par ye command-naam na mile to `--set-active=<slot>` wala
option bhi azmaya jata hai. Switch ke baad getvar dobara parh
kar VERIFY kiya jata hai: current-slot asal me target ban gaya
ho tab hi SUCCESS, warna FAIL.
"""

from ops.fastboot_frp import getvar_all, parse_getvar, resolve_fastboot

OP = {
    "id": "fastboot_slot",
    "category": "ADB / Fastboot",
    "name": "Slot Switch (A/B — slot active karo)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}


def _current_slot(fb, serial):
    """current-slot ki asal value ya None (jawab na aya ho to)."""
    text = getvar_all(fb, serial)
    data = parse_getvar(text)
    if not data:
        return None
    val = (data.get("current-slot") or "").strip().lower()
    return val


def _pick_target(ctx, current):
    """(target, wajah) — params wala slot ya doosra slot.

    Galat params value par (None, wajah): chup chaap andaza
    nahi lagaya jayega."""
    raw = str((getattr(ctx, "params", None) or {}).get("slot")
              or "").strip().lower()
    if raw in ("a", "b"):
        return raw, "params se muntakhib"
    if raw:
        return None, (f"params me slot ki value '{raw}' ayi hai — "
                      "sirf 'a' ya 'b' chalega.")
    return ("b" if current == "a" else "a"), "doosra slot (default)"


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial

    ctx.progress(20, "current-slot parha ja raha hai...")
    current = _current_slot(fb, serial)
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
    target, wajah = _pick_target(ctx, current)
    if target is None:
        ctx.log(wajah, "ERROR")
        return False
    ctx.log(f"Target slot: {target} ({wajah}) — ab slot "
            f"{target} active kiya jayega.", "INFO")
    if target == current:
        ctx.log("Note: target slot pehle se hi active hai — "
                "set-active dobara laga kar verify kiya jayega.",
                "INFO")

    ctx.progress(50, f"slot {target} active ho raha hai...")
    code = ctx.stream([fb, "-s", serial, "set-active", target],
                      timeout=60)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log("`set-active` command is fastboot build ne qabool "
                "nahi kiya — purane andaaz `--set-active=` ki "
                "koshish ho rahi hai...", "WARN")
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
    after = _current_slot(fb, serial)
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
