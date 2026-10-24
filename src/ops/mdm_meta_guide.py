"""
mdm_meta_guide.py — Transsion MDM pack: META / Preloader mode me lane ki guide.

Ye op koi engine subprocess nahi chalata — guided flow hai: pehle
qadam-ba-qadam hidayat log hoti hai, phir tool 30 second tak asal
port dhoondhta hai (device_watch scan + pyserial). Port mil jaye to
hi success hai; na mile to saaf FAIL aur wajah — nakli success nahi.
"""

import time

from core import device_watch

OP = {
    "id": "mdm_meta_guide",
    "category": "MDM / Transsion",
    "name": "META Mode Guide (Transsion MDM)",
    "engine": "guide",
    "modes": (),
    "server_required": False,
}

_POLL_SECONDS = 30
_POLL_INTERVAL = 1.5


def _scan_via_device_watch():
    """device_watch se pehla PRELOADER/BROM device, warna None."""
    try:
        devices = device_watch.scan_serial_modes()
    except Exception:  # noqa: BLE001
        return None
    for dev in devices or []:
        if getattr(dev, "mode", "") in ("PRELOADER", "BROM"):
            return dev.port or dev.serial or dev.mode
    return None


def _scan_via_pyserial():
    """pyserial se MediaTek/META port ka naam, warna None."""
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001 — pyserial na ho to sirf (a) par bharosa
        return None
    try:
        ports = list_ports.comports()
    except Exception:  # noqa: BLE001
        return None
    for port in ports:
        desc = (getattr(port, "description", "") or "").lower()
        if getattr(port, "vid", None) == 0x0E8D:
            return port.device
        if "meta" in desc or "preloader" in desc or "mediatek" in desc:
            return port.device
    return None


def run(ctx) -> bool:
    ctx.log("META mode me lane ka tareeqa — qadam ba qadam:", "INFO")
    ctx.log("1) Pehle BINA button wala rasta: phone ON rakho (ADB "
            "ON ho) aur tool ke 'Enter META Mode (ADB — bina "
            "button)' op se META me jao — META port khud ban "
            "jayega.", "INFO")
    ctx.log("2) Ya band phone sirf cable se lagao (koi button "
            "nahi) — MediaTek PreLoader / META port Device "
            "Manager me nazar ayega; ye tool ab 30 second tak "
            "port dhoondhega.", "INFO")
    ctx.log("3) Vol combo META ke liye nahi hai — wo sirf BROM "
            "ke liye hai. Port na mile to driver (MediaTek "
            "VCOM) check karo.", "INFO")

    start = time.monotonic()
    while True:
        if ctx.is_cancelled():
            return False
        elapsed = time.monotonic() - start
        if elapsed > _POLL_SECONDS:
            break
        ctx.progress(int(elapsed / _POLL_SECONDS * 100),
                     "META port ka intezaar...")

        port_name = _scan_via_device_watch()
        if not port_name:
            port_name = _scan_via_pyserial()
        if port_name:
            ctx.progress(95, "Port mil gaya")
            ctx.log(f"META/Preloader port mil gaya ({port_name}) — ab "
                    "Proinfo Backup/Write ops chal sakte hain.", "OK")
            return True

        # Intezaar ke doran bhi cancel foran pakro
        deadline = time.monotonic() + _POLL_INTERVAL
        while time.monotonic() < deadline:
            if ctx.is_cancelled():
                return False
            time.sleep(0.2)

    ctx.log("Port nahi mila — cable/driver (MediaTek VCOM) check karke "
            "dobara try karo. Pehle phone ON + ADB se 'Enter META "
            "Mode (ADB — bina button)' chalao, ya band phone sirf "
            "cable se lagao (Vol combo META ke liye nahi, sirf "
            "BROM ke liye hai); driver na ho to port nazar hi nahi "
            "ayega.", "ERROR")
    return False
