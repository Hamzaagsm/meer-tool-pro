"""
mtk_route_ladder.py — MTK Route Ladder: chip se rasta, nazar ke samne.

SERVER-REQUIRED research §3.6/§6 item 3: Kamakiri → Carbonara →
Heapbait chain pehle se built hai (`mtk_bypass_chain`), lekin
user ko nazar nahi ata ke us ke chip par kaun sa qadam khula hai.
Ye op seedhi dikhata hai — device laga ho to us ke chip ki,
warna poori table (har class ki).

Imaandari: "unknown" chip par bhi seedhi khaali nahi — live
detection + auto-try chain ka qadam dikhta hai. New-Auth class
(Dimensity 6300/6400/7100/7300/9000) guarded rehta hai — META
entry server-only likhi hai, DA ladder conditional.

Device ki zaroorat nahi (modes ()).
"""

from core import mtk_ladder

OP = {
    "id": "mtk_route_ladder",
    "category": "MTK",
    "name": "MTK Route Ladder — Chip se Rasta (Kamakiri / Carbonara / Heapbait / META)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}

_STATUS_MARK = {
    "open": "✔ KHULA",
    "conditional": "◐ SHART PAR",
    "server-only": "🔒 SERVER-ONLY",
    "unknown": "? NA-MALOOM",
}


def _log_steps(ctx, title, steps):
    ctx.log(title, "INFO")
    for i, step in enumerate(steps, 1):
        mark = _STATUS_MARK.get(step["status"], step["status"])
        op = step.get("op")
        tail = f" — op: {op}" if op else ""
        ctx.log(f"  {i}. [{mark}] {step['door']}{tail}", "INFO")
        ctx.log(f"     {step['note']}", "DATA")


def run(ctx) -> bool:
    dev = getattr(ctx, "device", None)
    chip = ""
    brand = ""
    if dev is not None:
        chip = " ".join(str(x or "") for x in
                        (getattr(dev, "chip", ""),
                         getattr(dev, "model", ""),
                         getattr(dev, "detail", "")))
        brand = getattr(dev, "brand", "") or ""

    if chip.strip():
        cls = mtk_ladder.chip_class(chip)
        _log_steps(ctx,
                   f"Chip: {chip.strip()} — class: {cls}",
                   mtk_ladder.ladder_for_chip(chip, brand))
        ctx.log("Seedhi ke khule qadam 'Latest Bypass (Auto)' op se "
                "tartib se chalte hain — har rasta GPT se verify "
                "hota hai.", "INFO")
        return True

    ctx.log("Koi device nahi laga — poori seedhi (har chip class):",
            "INFO")
    for title, steps in mtk_ladder.ladder_table().items():
        _log_steps(ctx, title, steps)
    ctx.log("Phone lagao to is ki chip ki seedhi alag se dikhegi.",
            "INFO")
    return True
