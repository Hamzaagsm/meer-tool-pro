"""
samsung_fw_download.py — Samsung Firmware Download (FUS, Free).

Samsung ke official FUS server se firmware download karta hai —
koi mirror hunting nahi, koi Samsung account/password nahi
(FUS anonymous hai). Protocol: SamLoader-RS (2026, Apache-2.0)
par mabni stdlib client (core/samloader_client.py) — nonce auth,
BinaryInform/Init, parallel nahi, resume wala single-stream
download, ENC2/ENC4 decrypt.

Model + CSC kahan se ata hai (tartib):
  1) tools/firmware-samsung/download-request.txt — "MODEL=SM-..."
     aur "CSC=EUX" lines (ya aik line me "SM-S918B EUX"); is
     tarah phone haath me na ho to bhi download ho jata hai.
  2) ADB device connected ho to us ke props se (model + CSC).
  3) Dono na hon to op ruk kar saaf instructions deta hai.

Output: tools/firmware-samsung/ me decrypted .zip (Odin flash
ops usi folder se utha lete hain). .enc4/.enc2 file decrypt ke
baad hata di jati hai (pehle size verify hota hai).

Had (imaandari se):
  * Firmware 5–17 GB ki hoti hai — waqt + disk space chahiye;
    download beech me ruke to resume hota hai (Range).
  * Decrypt pure-Python AES se slow hai (bara firmware ghanton
    me ja sakta hai); pycryptodome ho to fast path chalta hai.
  * 2026 protocol live-verify hua hai (2026-10-25: FOTA +
    BinaryInform S00 + 1 KB range download + decrypt se ZIP
    magic "PK" mila). Samsung API phir badal de to op imaandar
    FAIL dega, nakli file nahi.
  * Sirf firmware download — flash alag op ('Flash 4-File')
    karta hai; KG-locked ya FRP-locked phone par flash se pehle
    'KG Status' op se halat parh lo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from core import device_watch, engines
from core.runner import TOOLS_DIR
from core import samloader_client as fus

OP = {
    "id": "samsung_fw_download",
    "category": "Samsung",
    "name": "Firmware Download (Samsung FUS — Free)",
    "engine": "samsung-fus",
    "modes": (),
    "server_required": False,
}

OUT_DIR = TOOLS_DIR / "firmware-samsung"
REQUEST_FILE = OUT_DIR / "download-request.txt"

_GB = 1024 * 1024 * 1024


# ---------------------------------------------------------------------------
# Pure helpers (testable)
# ---------------------------------------------------------------------------
def parse_request_text(text):
    """Request file text → (model, region) ya (None, None).

    Qabool formats:
      MODEL=SM-S918B
      CSC=EUX
    ya aik line: "SM-S918B EUX" / "SM-S918B,EUX".
    """
    model = None
    region = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip().upper()
            val = val.strip().upper()
            if key in ("MODEL", "SM", "DEVICE"):
                model = val
            elif key in ("CSC", "REGION", "SALES_CODE"):
                region = val
            continue
        parts = [p.strip().upper() for p in
                 line.replace(",", " ").split() if p.strip()]
        if len(parts) >= 2 and model is None:
            model, region = parts[0], parts[1]
        elif len(parts) == 1 and model is None:
            model = parts[0]
    return model, region


def format_size(num_bytes):
    """Bytes → '16.9 GB' jaisi readable string."""
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024
    return "%.1f GB" % size


def request_file_template():
    """download-request.txt ka misali content."""
    return (
        "# Samsung firmware download request — aik line me model,\n"
        "# doosri me CSC (region) likho, phir op dobara chalao.\n"
        "# Misal: Galaxy S23 Ultra, Europe (EUX):\n"
        "MODEL=SM-S918B\n"
        "CSC=EUX\n"
    )


def _props_model_region(props):
    """ADB getprop dict → (model, region) ya (None, None)."""
    props = props or {}
    model = (props.get("ro.product.model", "") or "").strip().upper()
    region = (props.get("ro.csc.sales_code", "")
              or props.get("ro.csc.country_code", "") or "").strip().upper()
    return (model or None, region or None)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------
def _resolve_adb(ctx):
    adb = engines.find_platform_tool("adb")
    if not Path(adb).is_file() and shutil.which(adb) is None:
        return None
    return adb


# ---------------------------------------------------------------------------
# Asal op
# ---------------------------------------------------------------------------
def run(ctx) -> bool:
    ctx.log("Samsung Firmware Download — official FUS server se, "
            "anonymous (koi Samsung login/password nahi chahiye).",
            "INFO")

    # --- 1) Model + CSC: request file pehle, phir ADB device ---------
    model = region = None
    if REQUEST_FILE.is_file():
        try:
            model, region = parse_request_text(
                REQUEST_FILE.read_text(encoding="utf-8",
                                       errors="replace"))
        except Exception:  # noqa: BLE001 — file kharab ho to ADB rasta
            model = region = None
        if model and region:
            ctx.log(f"Request file se: Model {model}, CSC {region}",
                    "DATA")
    if not (model and region):
        dev = getattr(ctx, "device", None)
        serial = getattr(dev, "serial", "") if dev else ""
        mode = getattr(dev, "mode", "") if dev else ""
        if mode == "ADB" and serial:
            adb = _resolve_adb(ctx)
            if adb:
                try:
                    props = device_watch.adb_getprops(adb, serial)
                except Exception:  # noqa: BLE001
                    props = {}
                model, region = _props_model_region(props)
                if model and region:
                    ctx.log(f"ADB device se: Model {model}, CSC "
                            f"{region}", "DATA")
    if not model or not region:
        if not REQUEST_FILE.is_file():
            try:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                REQUEST_FILE.write_text(request_file_template(),
                                        encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        ctx.log("Model + CSC maloom nahi hue.", "ERROR")
        ctx.log("Do tareeqe hain: (1) tools/firmware-samsung/"
                "download-request.txt me MODEL= aur CSC= likho "
                "(misal file bana di gayi hai) aur op dobara chalao; "
                "(2) phone on karke ADB mode me lagao — model/CSC "
                "phone se parh liye jayenge.", "INFO")
        ctx.log("CSC = sales region code (misal: EUX Europe, XSG "
                "UAE, PAK Pakistan, INS India). Ghalat CSC par "
                "firmware nahi milegi — phone ki CSC 'Firmware "
                "Download Helper' op se parh lo.", "INFO")
        return False

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- 2) Latest version (FOTA) --------------------------------------
    ctx.progress(5, "Latest version check ho rahi hai...")
    try:
        version = fus.checkupdate(model, region, timeout=30)
    except fus.FUSError as e:
        ctx.log(f"Version check nakam: {e}", "ERROR")
        ctx.log("Model/CSC ghalat ho sakta hai — ya Samsung ne FOTA "
                "endpoint badal diya ho. 'Firmware Download Helper' "
                "op se model/CSC dobara parho.", "INFO")
        return False
    ctx.log(f"Latest firmware: {version}", "DATA")

    # --- 3) FUS handshake + BinaryInform -------------------------------
    ctx.progress(10, "FUS server se rabta (nonce handshake)...")
    try:
        client = fus.FUSClient(timeout=30)
        info = client.get_binary_info(model, region, version)
    except fus.FUSError as e:
        ctx.log(f"FUS se maloomat nahi mili: {e}", "ERROR")
        return False
    filename = info["filename"]
    size = info["size"]
    enc_path = OUT_DIR / filename
    zip_path = OUT_DIR / fus.decrypted_name(filename)
    ctx.log(f"File: {filename}", "DATA")
    ctx.log(f"Size: {format_size(size)}", "DATA")
    ctx.log(f"ENC version: {fus.enc_version_of(filename)}", "DATA")

    # Pehle se mukammal decrypted file maujood ho to dobara nahi.
    if zip_path.is_file() and zip_path.stat().st_size > 0:
        with open(zip_path, "rb") as fh:
            if fh.read(4) == b"PK\x03\x04":
                ctx.log(f"Pehle se maujood (decrypted, ZIP magic OK): "
                        f"{zip_path}", "OK")
                ctx.log("Flash ke liye Samsung section ka 'Flash "
                        "4-File' op istemal karo.", "INFO")
                return True

    # --- 4) Download (resume) ------------------------------------------
    start = 0
    if enc_path.is_file():
        start = enc_path.stat().st_size
        if start >= size:
            start = size
        elif start > 0:
            ctx.log(f"Adhoori download mili ({format_size(start)}) — "
                    "resume ho rahi hai.", "INFO")
    ctx.progress(15, "Firmware download ho rahi hai (bara file, "
                     "waqt lagega)...")
    last_pct = {"v": -1}

    def _on_progress(done, total):
        if total:
            pct = int(done * 100 / total)
            if pct != last_pct["v"] and pct % 5 == 0:
                last_pct["v"] = pct
                ctx.progress(15 + int(pct * 0.6),
                             f"Download {pct}% "
                             f"({format_size(done)}/{format_size(total)})")

    try:
        # Download host pehli byte dene me waqt le sakta hai (live
        # test me ~60s tak) — is liye lamba timeout.
        client.timeout = 120
        got = client.download_file(
            info["path"], filename, enc_path, start=start,
            progress=_on_progress,
            init=(info["version"], info["model_type"], info["region"]))
    except fus.FUSError as e:
        ctx.log(f"Download nakam: {e}", "ERROR")
        ctx.log("Adhoori file mehfooz hai — op dobara chalao, resume "
                "ho jayegi (dobara shuru se nahi).", "INFO")
        return False
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Download ke doran ghalti: {e}", "ERROR")
        return False
    if got != size:
        ctx.log(f"Download mukammal nahi hua: {format_size(got)} mila, "
                f"{format_size(size)} chahiye tha. Op dobara chalao "
                "(resume).", "ERROR")
        return False
    ctx.log(f"Download mukammal: {format_size(got)}", "OK")

    # --- 5) Decrypt ------------------------------------------------------
    ctx.progress(80, "Decrypt ho raha hai (AES-128-ECB)...")
    ctx.log("Decrypt ho raha hai — pure-Python AES par bara firmware "
            "slow ho sakta hai; pycryptodome install ho to fast "
            "hota hai.", "INFO")
    try:
        fus.decrypt_file(enc_path, zip_path, info["key"],
                         progress=lambda d, t: ctx.progress(
                             80 + (int(d * 15 / t) if t else 0),
                             "Decrypt %d%%" % (int(d * 100 / t)
                                              if t else 0)))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Decrypt nakam: {e}", "ERROR")
        return False
    with open(zip_path, "rb") as fh:
        magic = fh.read(4)
    if magic != b"PK\x03\x04":
        ctx.log("Decrypted file ZIP nahi lagti (magic ghalat) — "
                "decrypt key ya file kharab ho sakti hai. .enc file "
                "mehfooz rakhi gayi hai.", "ERROR")
        return False
    try:
        enc_path.unlink()
    except Exception:  # noqa: BLE001
        pass
    ctx.progress(95, "Firmware tayyar")
    ctx.log(f"✔ Firmware tayyar: {zip_path} "
            f"({format_size(zip_path.stat().st_size)})", "OK")
    ctx.log("Flash ke liye Samsung section ka 'Flash 4-File' op "
            "istemal karo (phone Download Mode me). Flash se pehle "
            "'KG Status' op se KG halat parh lena.", "INFO")
    return True
