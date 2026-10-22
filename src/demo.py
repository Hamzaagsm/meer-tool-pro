"""
demo.py — DEMO MODE.

Baghair phone ke poora nakli session: detect → info → GPT → FRP erase →
reboot, bilkul asal jaisi live log lines aur progress ke saath. Maqsad:
Hamza ko tool "chalta nazar aye" aur UI/flow har waqt test ho sake.

IMAANDARI: har line par [DEMO] tag hai — ye simulation hai, asal device
par kuch nahi hota, aur log isay saaf kehta hai.
"""

import time

from core.device_watch import DeviceInfo


def fake_device() -> DeviceInfo:
    """Demo ke liye nakli device (Hamza ke Infinix X6887 ki misaal par)."""
    return DeviceInfo(
        serial="X6887DEMO0001",
        mode="BROM",
        port="COM7",
        brand="Infinix",
        model="X6887 (HOT 50 Pro+)",
        chip="MT6789 Helio G99",
        android="14",
        detail="MediaTek BROM (COM7) — DEMO",
    )


def _step(ctx, msg, level, pct, label, delay=0.55):
    if ctx.is_cancelled():
        raise _DemoCancelled()
    ctx.log(f"[DEMO] {msg}", level)
    if pct is not None:
        ctx.progress(pct, label)
    time.sleep(delay)


class _DemoCancelled(Exception):
    pass


def run_demo_session(ctx) -> bool:
    """Poora demo session chalao. run(ctx)->bool plugin contract par."""
    dev = fake_device()
    if ctx.update_device:
        ctx.update_device(dev)
    try:
        ctx.log("[DEMO] Demo mode shuru — ye simulation hai, asal phone "
                "nahi laga hua.", "WARN")
        _step(ctx, "Ports scan ho rahe hain... (COM1..COM12)", "INFO", 4,
              "Scanning ports")
        _step(ctx, "COM7 par device mila: VID_0E8D PID_0003 — MediaTek BROM",
              "OK", 12, "Device found")
        _step(ctx, "Handshake bhejha ja raha hai...", "INFO", 20, "Handshake")
        _step(ctx, "BROM handshake OK — DA download shuru", "DATA", 28,
              "Sending DA")
        _step(ctx, "DA1 bheja gaya... DA2 bheja gaya... DA agent chal raha hai",
              "DATA", 38, "DA running", 0.8)
        _step(ctx, "Chip: MT6789 Helio G99 | HW Code: 0x1205 | "
                   "Storage: UFS 256GB", "DATA", 48, "Chip info")
        _step(ctx, "Security: SLA OFF (ye chipset free engine se supported hai)",
              "DATA", 52, "Security check")
        _step(ctx, "GPT parhi ja rahi hai... 62 partitions mileen", "DATA",
              60, "Reading GPT")
        _step(ctx, "Partition 'frp' mila: offset 0x14A8000, size 0x100000",
              "DATA", 66, "FRP partition")
        _step(ctx, "FRP erase shuru...", "INFO", 72, "Erasing FRP", 0.7)
        _step(ctx, "Erasing block 0x14A8000 ... OK", "DATA", 82, "Erasing FRP")
        _step(ctx, "Erasing block 0x14B8000 ... OK", "DATA", 90, "Erasing FRP")
        _step(ctx, "FRP partition saaf ho gaya.", "OK", 95, "FRP erased")
        _step(ctx, "Device reboot kiya ja raha hai...", "INFO", 98, "Reboot")
        _step(ctx, "Session khatam. (Asal operation me bilkul yehi log asal "
                   "engine ki output ke saath ayega.)", "INFO", 100, "Done")
    except _DemoCancelled:
        return False
    return True
