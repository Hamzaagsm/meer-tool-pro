"""
samsung_odin.py — Samsung Download-Mode flash ke shared helpers.

odin4 (Samsung ka official CLI flasher) dhoondhna, 4-file firmware
(BL_/AP_/CP_/CSC_/HOME_CSC_) scan karna, Download-Mode COM port
(VID 0x04E8) pehchanna, aur asal flash chalana — sab yahan hai
taake dono Samsung flash ops (CSC = full reset, HOME_CSC = data
mehfooz) aik hi imaandar flow istemal karen.

Usool: SUCCESS sirf tab jab odin4 ka exit code 0 ho AUR us ki
apni output me PASS/success ka saboot mile. Output ctx.stream se
nahi milti, is liye flash ke liye yahan apna subprocess capture
helper hai (fastboot_frp.getvar_all wala pattern).
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from core.runner import ENGINES_DIR, TOOLS_DIR

# Samsung USB Vendor ID — Download Mode me device isi VID se ata hai.
SAMSUNG_VID = 0x04E8

_FIRMWARE_KEYS = ("HOME_CSC", "BL", "AP", "CP", "CSC")


def find_odin():
    """odin4 ya heimdall dhoondho → (path_str, kind) ya (None, None).

    Tartib: engines/samsung/ → tools/samsung/ → PATH. pehle odin4
    ki poori koshish, phir heimdall (fallback sirf pehchan ke liye
    hai — is build ka flash flow sirf odin4 chalata hai).
    """
    for name in ("odin4", "heimdall"):
        for base in (ENGINES_DIR / "samsung", TOOLS_DIR / "samsung"):
            for cand in (base / f"{name}.exe", base / name):
                if cand.is_file():
                    return str(cand), name
        found = shutil.which(name)
        if found:
            return found, name
    return None, None


def scan_samsung_firmware(folder):
    """Folder (non-recursive) me 4-file firmware ki files pehchano.

    Naam BL_/AP_/CP_/CSC_/HOME_CSC_ se shuru ho (case-insensitive)
    aur .tar ya .tar.md5 ho. Return: {"BL": Path|None, "AP": ...,
    "CP": ..., "CSC": ..., "HOME_CSC": ...}. Aik key ki aik se
    zyada files hon to pehli (sorted) li jati hai.
    """
    result = {key: None for key in _FIRMWARE_KEYS}
    folder = Path(folder)
    if not folder.is_dir():
        return result
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        low = path.name.lower()
        if not (low.endswith(".tar") or low.endswith(".tar.md5")):
            continue
        upper = path.name.upper()
        for key in _FIRMWARE_KEYS:
            if upper.startswith(key + "_"):
                if result[key] is None:
                    result[key] = path
                break
    return result


def find_samsung_download_port():
    """Download Mode me Samsung COM port ka naam, warna None.

    pyserial lazy import hai — na ho to None (FAIL wajah op dega,
    yahan crash nahi).
    """
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        return None
    try:
        for port in list_ports.comports():
            if port.vid == SAMSUNG_VID:
                return port.device
    except Exception:  # noqa: BLE001
        return None
    return None


_VERSION_RE = re.compile(r"[A-Z0-9]{8,}")


def ap_version_token(filename):
    """AP filename se version-ish token (PDA build string) — pure.

    Naam ko '_' / '.' / '-' par tor kar pehla [A-Z0-9]{8,} segment
    jis me harf AUR digit dono hon; yaqeen na ho to "".
    Masalan: AP_A546EXXS8CXG1_...tar.md5 → A546EXXS8CXG1.
    """
    name = Path(str(filename)).name.upper()
    for segment in re.split(r"[._\- ]+", name):
        if _VERSION_RE.fullmatch(segment) \
                and any(c.isdigit() for c in segment) \
                and any(c.isalpha() for c in segment):
            return segment
    return ""


def odin4_args(odin, files, csc_key):
    """odin4 ki argv list banao (pure-ish — sirf dict parhna hai).

    -b BL, -a AP, -c CP, -s chuna hua CSC (csc_key = "CSC" ya
    "HOME_CSC"). Jo hissa files me na ho wo skip ho jata hai
    (AP aur chuna hua CSC lazmi hain — op pehle check karta hai).
    """
    args = [str(odin)]
    if files.get("BL"):
        args += ["-b", str(files["BL"])]
    if files.get("AP"):
        args += ["-a", str(files["AP"])]
    if files.get("CP"):
        args += ["-c", str(files["CP"])]
    if files.get(csc_key):
        args += ["-s", str(files[csc_key])]
    return args


def _run_capture(cmd, timeout=3600):
    """Command chala kar (returncode, combined output) wapas do.

    Flash lamba kaam hai; cancellation yahan sirf shuru hone se
    PEHLE check hoti hai (run_flash me) — chalti flash ko beech
    me rokna phone ko brick kar sakta hai, is liye beech me
    process ko nahi mara jata.
    """
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        text = (out.stdout or "") + "\n" + (out.stderr or "")
        return out.returncode, text
    except subprocess.TimeoutExpired as exc:
        text = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") \
            + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return None, text + f"\n[timeout {timeout}s]"
    except Exception as exc:  # noqa: BLE001
        return None, f"[chalne me kharabi: {exc}]"


def run_flash(ctx, csc_key) -> bool:
    """Dono Samsung flash ops ka mushtarka flow.

    csc_key = "CSC" (full reset / data wipe) ya "HOME_CSC"
    (data mehfooz). Har kami par guided FAIL; SUCCESS sirf asal
    odin4 output ke saboot par.
    """
    keep_data = (csc_key == "HOME_CSC")

    # --- 1) Engine: odin4 lazmi hai -------------------------------------
    path, kind = find_odin()
    if path is None:
        ctx.log("odin4 nahi mila. odin4 Samsung ka official "
                "command-line flasher hai (Download Mode flash ke "
                "liye) — use engines/samsung/ ya tools/samsung/ "
                "folder me rakho (odin4.exe). Us ke baghair Samsung "
                "flash mumkin nahi, is liye yahan ruk raha hoon.",
                "ERROR")
        return False
    if kind == "heimdall":
        ctx.log("Sirf Heimdall mila hai. Heimdall open-source hai, "
                "lekin is build me us ka flash flow guided (manual) "
                "hai — ye op sirf odin4 chalata hai. odin4 ko "
                "engines/samsung/ ya tools/samsung/ me rakho aur "
                "op dobara chalao.", "ERROR")
        return False
    ctx.log(f"odin4 mila: {path}", "OK")

    # --- 2) Firmware: 4-file, AP lazmi, chuna hua CSC lazmi -------------
    folder = TOOLS_DIR / "firmware-samsung"
    files = scan_samsung_firmware(folder)
    if files["AP"] is None:
        ctx.log("Firmware nahi mili. Is phone ki 4-file firmware "
                "(BL_..., AP_..., CP_..., CSC_... / HOME_CSC_... "
                ".tar ya .tar.md5) tools/firmware-samsung/ folder "
                "me rakho — AP_ wali file lazmi hai. Firmware bilkul "
                "isi model ki ho; ghalat model ki firmware = brick "
                "ka khatra.", "ERROR")
        return False
    if files[csc_key] is None:
        if keep_data:
            ctx.log("HOME_CSC_ wali file nahi mili — data mehfooz "
                    "flash mumkin nahi. Sirf CSC_ hai: CSC wala op "
                    "('Flash 4-File (Download Mode, CSC = Full "
                    "Reset)') TAMAM data mita dega — pehle customer "
                    "se pooch kar, us ki ijazat se hi wahi op "
                    "chalao.", "ERROR")
        else:
            if files["HOME_CSC"] is not None:
                ctx.log("CSC_ wali file nahi mili, sirf HOME_CSC_ "
                        "hai. Ye op (CSC = Full Reset) CSC_ ke "
                        "baghair nahi chalegi. Agar data mehfooz "
                        "rakhna hai to 'Flash 4-File (HOME_CSC = "
                        "Data Mehfooz)' wala op chalao — ya poori "
                        "4-file firmware (CSC_ samait) "
                        "tools/firmware-samsung/ me rakho.",
                        "ERROR")
            else:
                ctx.log("CSC_ wali file bhi nahi mili aur HOME_CSC_ "
                        "bhi nahi — firmware na-mukammal hai. Poori "
                        "4-file firmware tools/firmware-samsung/ "
                        "me rakho.", "ERROR")
        return False
    for key in ("BL", "AP", "CP", csc_key):
        if files.get(key):
            ctx.log(f"{key}: {files[key].name}", "DATA")
    if files["BL"] is None:
        ctx.log("BL_ file nahi mili — bootloader hissa skip hoga. "
                "Aksar halat me chal jata hai, lekin poori 4-file "
                "firmware behtar hai.", "WARN")
    if files["CP"] is None:
        ctx.log("CP_ file nahi mili — modem hissa skip hoga.",
                "WARN")

    # --- 3) Download Mode port check ------------------------------------
    ctx.progress(15, "Download Mode port dhoondha ja raha hai...")
    port = find_samsung_download_port()
    if port is None:
        ctx.log("Samsung Download Mode port nahi mila. Phone ko "
                "Download Mode me lao: phone band karo, phir Vol "
                "Down + Vol Up dono dabaye hue USB cable lagao, "
                "screen par warning aye to Vol Up dabao (Download "
                "Mode). Ya phone agar ADB me on hai to 'Reboot → "
                "Download (Samsung)' wala op pehle chalao. Cable "
                "lagi rehne do aur ye op dobara chalao. (Samsung "
                "USB drivers bhi install hone chahiyein.)", "ERROR")
        return False
    ctx.log(f"Download Mode device mila: {port}", "OK")

    # --- 4) Downgrade warning --------------------------------------------
    token = ap_version_token(files["AP"].name)
    if token:
        ctx.log(f"AP version token: {token}", "DATA")
    dev = ctx.device
    if dev and (getattr(dev, "model", "") or getattr(dev, "android", "")):
        ctx.log("⚠ Downgrade warning: pehle tasdeeq kar lo ke is "
                "AP ki version phone ki maujooda build se chhoti "
                "na ho — binary (bit) version chhota ho to Odin "
                "khud flash rok dega aur error dega. Upar wala AP "
                "token phone ki current build se mila kar dekho.",
                "WARN")

    # --- 5) Flash (apna capture — saboot output se ayega) ----------------
    if keep_data:
        ctx.log("HOME_CSC istemal ho raha hai — userdata mehfooz "
                "rehne ke liye hai, phir bhi flash se pehle customer "
                "ko backup ka mashwara lazmi do.", "INFO")
    else:
        ctx.log("⚠ CSC flash = TAMAM data mit jayega (factory "
                "reset jaisa asar). Age barhne se pehle customer ko "
                "bata do — ye op yahi kaam karega.", "WARN")

    # NOTE: cancellation sirf yahan, shuru hone se pehle check
    # hoti hai — chalti flash beech me rokna khatarnak hai.
    if ctx.is_cancelled():
        ctx.log("Flash shuru hone se pehle cancel kar diya gaya.",
                "WARN")
        return False

    args = odin4_args(path, files, csc_key)
    ctx.log("Flash shuru ho raha hai — cable HARGIZ mat nikalna, "
            "PC band mat karna...", "CMD")
    ctx.progress(30, "odin4 flash chal raha hai (waqt lag sakta hai)...")
    code, output = _run_capture(args, timeout=3600)
    out_lines = [ln.strip() for ln in (output or "").splitlines()
                 if ln.strip()]
    for line in out_lines[-60:]:
        ctx.log(line, "DATA")

    low = (output or "").lower()
    if code == 0 and ("pass" in low or "success" in low):
        ctx.progress(95, "Flash mukammal")
        ctx.log("odin4 ne PASS/success ka saboot diya — flash "
                "mukammal.", "OK")
        ctx.log("Imaandar note: CSC/HOME_CSC flash se FRP NAHI "
                "jata — FRP phone ki Google account halat par "
                "bandha hai; setup ke waqt purana Google account "
                "mang sakta hai. Phone reboot karke poora setup "
                "check karo.", "INFO")
        return True

    ctx.log(f"Flash ka saboot nahi mila (exit code: {code}). "
            "Upar wali output ki aakhri lines hi asal wajah hain — "
            "cable/port dobara check karke, phone ko dobara "
            "Download Mode me la kar op phir chalao. 'PASS' na aye "
            "to flash mukammal NAHI mani jayegi.", "ERROR")
    return False
