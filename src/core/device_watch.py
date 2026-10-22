"""
device_watch.py — Device auto-detect (ADB / Fastboot / COM port scan).

Phone lagte hi tool ko khud pata chalna chahiye ke device kis mode me hai:
  - ADB mode        -> `adb devices` polling
  - Fastboot mode   -> `fastboot devices` polling
  - BROM / Preloader-> COM port par MediaTek VID/PID
  - EDL 9008        -> COM port par Qualcomm VID/PID
  - SPD Diag        -> COM port par Spreadtrum VID/PID

pyserial mojood ho to us se port scan hota hai; na ho to graceful degrade —
Windows par `wmic` fallback, aur agar wo bhi na ho to sirf ADB/Fastboot
detect chalega (crash kabhi nahi).

Koi GUI dependency nahi — main.py isay polling loop me istemal karta hai.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Pehchan ki table: (VID, PID) -> (mode, tafseel)
# ----------------------------------------------------------------------------
USB_ID_TABLE = {
    ("0e8d", "0003"): ("BROM", "MediaTek BROM"),
    ("0e8d", "2000"): ("PRELOADER", "MediaTek Preloader"),
    ("0e8d", "2001"): ("PRELOADER", "MediaTek Preloader"),
    ("0e8d", "2006"): ("PRELOADER", "MediaTek Preloader (DA)"),
    ("05c6", "9008"): ("EDL", "Qualcomm HS-USB QDLoader 9008"),
    ("05c6", "900e"): ("DIAG", "Qualcomm Diag 900E"),
    ("1782", "4d00"): ("SPD", "Spreadtrum Diag"),
    ("1782", "4d01"): ("SPD", "Spreadtrum Diag"),
}

MODE_ADB = "ADB"
MODE_FASTBOOT = "FASTBOOT"


@dataclass
class DeviceInfo:
    """Aik detected device ki maloomat — device panel isi se bharta hai."""
    serial: str = ""
    mode: str = ""               # ADB / FASTBOOT / BROM / PRELOADER / EDL / SPD / DEMO
    port: str = ""               # COM7 waghera (serial modes ke liye)
    brand: str = ""
    model: str = ""
    chip: str = ""
    android: str = ""
    detail: str = ""             # port description / extra line
    raw_props: dict = field(default_factory=dict)

    @property
    def connected(self) -> bool:
        return bool(self.mode)

    def label(self) -> str:
        name = " ".join(x for x in (self.brand, self.model) if x).strip()
        return name or self.detail or self.serial or "Unknown device"


# ----------------------------------------------------------------------------
# Subprocess helper (console window chhupaya hua — Windows GUI ke liye)
# ----------------------------------------------------------------------------
def _run_quiet(cmd, timeout=6):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, **kwargs
        )
        return out.stdout or ""
    except Exception:
        return ""


def find_tool(name):
    """platform-tools pehle app ke tools/ folder me, phir PATH me dhoondo."""
    return shutil.which(name)


# ----------------------------------------------------------------------------
# ADB / Fastboot polling
# ----------------------------------------------------------------------------
def scan_adb(adb_path="adb"):
    """`adb devices` se pehla authorized device wapas karo, warna None."""
    out = _run_quiet([adb_path, "devices"])
    for line in out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            return DeviceInfo(serial=serial, mode=MODE_ADB, detail="ADB mode")
    return None


def scan_fastboot(fastboot_path="fastboot"):
    out = _run_quiet([fastboot_path, "devices"])
    for line in out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "fastboot":
            return DeviceInfo(serial=parts[0], mode=MODE_FASTBOOT,
                              detail="Fastboot mode")
    return None


def adb_getprops(adb_path, serial):
    """getprop ki output ko dict me parse karo (device info ke liye)."""
    out = _run_quiet([adb_path, "-s", serial, "shell", "getprop"], timeout=10)
    props = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("[") and "]: [" in line and line.endswith("]"):
            key, _, val = line[1:].partition("]: [")
            props[key.strip()] = val[:-1].strip()
    return props


def enrich_from_props(dev: DeviceInfo, props: dict) -> DeviceInfo:
    dev.raw_props = props
    dev.brand = props.get("ro.product.brand", dev.brand)
    dev.model = props.get("ro.product.model", dev.model)
    dev.chip = (props.get("ro.board.platform")
                or props.get("ro.hardware")
                or props.get("ro.soc.model") or dev.chip)
    dev.android = props.get("ro.build.version.release", dev.android)
    return dev


# ----------------------------------------------------------------------------
# COM port scan (BROM / EDL / SPD) — pyserial ho to best, warna degrade
# ----------------------------------------------------------------------------
def _scan_ports_pyserial():
    try:
        from serial.tools import list_ports  # pyserial
    except Exception:
        return None  # pyserial nahi — caller fallback karega
    found = []
    for p in list_ports.comports():
        vid = f"{p.vid:04x}" if p.vid is not None else ""
        pid = f"{p.pid:04x}" if p.pid is not None else ""
        hit = USB_ID_TABLE.get((vid, pid))
        if hit:
            mode, detail = hit
            found.append(DeviceInfo(serial=p.device, mode=mode, port=p.device,
                                    detail=f"{detail} ({p.device})"))
    return found


def _scan_ports_wmic():
    """Windows fallback: wmic se Ports ki list, naam me pehchan dhoondo."""
    if not sys.platform.startswith("win"):
        return []
    out = _run_quiet(["wmic", "path", "Win32_PnPEntity", "where",
                      "Name like '%(COM%'", "get", "Name"], timeout=10)
    hints = [
        ("MediaTek", "BROM"), ("PreLoader", "PRELOADER"),
        ("QDLoader 9008", "EDL"), ("Qualcomm", "EDL"),
        ("Spreadtrum", "SPD"),
    ]
    found = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "(COM" not in line:
            continue
        port = line[line.rfind("(COM"):].strip("() ")
        for hint, mode in hints:
            if hint.lower() in line.lower():
                found.append(DeviceInfo(serial=port, mode=mode, port=port,
                                        detail=line))
                break
    return found


def scan_serial_modes():
    """BROM/EDL/SPD waghera serial modes ki list wapas karo (khali bhi ho sakti hai)."""
    result = _scan_ports_pyserial()
    if result is None:
        result = _scan_ports_wmic()
    return result or []


# ----------------------------------------------------------------------------
# Aik mukammal poll — main.py har ~2 second me ye chalata hai
# ----------------------------------------------------------------------------
def poll_once(adb_path="adb", fastboot_path="fastboot"):
    """Sab modes check karke sab se zyada maloomati device wapas karo.

    Tarjeeh: ADB (sab se zyada info) > Fastboot > serial modes.
    Kuch na mile to khali DeviceInfo (connected=False).
    """
    dev = scan_adb(adb_path)
    if dev:
        props = adb_getprops(adb_path, dev.serial)
        if props:
            enrich_from_props(dev, props)
        return dev
    dev = scan_fastboot(fastboot_path)
    if dev:
        return dev
    serials = scan_serial_modes()
    if serials:
        return serials[0]
    return DeviceInfo()
