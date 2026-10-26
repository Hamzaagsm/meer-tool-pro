"""
qc_qcn_backup.py — Qualcomm QCN backup (QPST/QFIL guided flow).

QCN device ki apni NV file hai — asal IMEI usi ke andar mehfooz
hota hai (REPAIR-METHODS-RESEARCH §3.3). Asal transfer Qualcomm
ke official QPST/QFIL ke "QCN Backup Restore" se hota hai; MEER
ka kaam:
  1. Diag port kholne ki asal koshish (ADB setprop route) +
     dialer-code wali hidayat.
  2. Backup ki jagah (tools/qcn/) aur file naam ki hidayat,
     taake kal ko restore wali file pehchani ja sake.
  3. QFIL/QPST khud kholne ki rehnumai — MEER ke andar se koi
     doosra tool NAHI khulta (Hamza ka usool; 2026-10-25 audit
     A4 — pehle ye op QFIL khol deta tha, ab retired).
"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core import engines
from core.runner import TOOLS_DIR

OP = {
    "id": "qc_qcn_backup",
    "category": "Qualcomm",
    "name": "QCN Backup — Guide (QFIL khud kholo)",
    "engine": "qpst",
    "modes": ("ADB",),
    "server_required": False,
}

QCN_DIR = TOOLS_DIR / "qcn"


def _adb_capture(adb, serial, args, timeout=25):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([adb, "-s", serial] + list(args),
                             capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def diag_enable(ctx):
    """Diag port kholne ki asal koshish + hidayat. True = koshish
    chal gayi (tasdeeq Device Manager se karni hai — log batata hai)."""
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Diag enable ke liye device pehle ADB mode me "
                "chahiye — phone on karke USB debugging ON karo.",
                "ERROR")
        return False
    adb = engines.find_platform_tool("adb")
    if not Path(adb).is_file() and shutil.which(adb) is None:
        ctx.log("adb nahi mila — platform-tools setup chahiye.", "ERROR")
        return False
    ctx.log("Diag port kholne ki koshish: sys.usb.config = diag,adb "
            "set kiya ja raha hai...", "INFO")
    code, out = _adb_capture(adb, dev.serial,
                             ["shell", "setprop", "sys.usb.config",
                              "diag,adb"])
    if code == 0:
        ctx.log("setprop chal gaya. Tasdeeq: Device Manager me "
                "'Qualcomm HS-USB Diagnostics' port ana chahiye. "
                "Stock locked firmwares par ye command khamoshi se "
                "asar nahi karti — port na aye to neeche wala "
                "dialer rasta dekho.", "INFO")
    else:
        ctx.log(f"setprop nahi chala (code {code}) — aam wajah: "
                "stock firmware par diag band hai ya root nahi. "
                "Neeche wala dialer rasta dekho.", "WARN")
    ctx.log("Dialer raste (model ke hisaab se): kuch OnePlus/Xiaomi "
            "par *#*#717717#*#* diag kholta hai; baqi models par "
            "diag aksar root/engineering firmware se hi khulta "
            "hai. Port khule baghair QCN transfer mumkin nahi — "
            "ye is raste ki imaandar hadd hai.", "INFO")
    return True


def find_qpst():
    """(exe|None) — QFIL pehle, phir QPSTConfig."""
    folder = TOOLS_DIR / "qpst"
    if not folder.is_dir():
        return None
    exes = [p for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() == ".exe"]
    for want in ("qfil", "qpstconfig", "qpst"):
        for exe in exes:
            if want in exe.name.lower():
                return exe
    return exes[0] if exes else None


def manual_open_guide(ctx, exe):
    """QFIL/QPST khud kholne ki rehnumai — MEER koi tool nahi kholta.

    Hamesha False: backup/restore ka asal transfer QFIL ke andar
    hota hai, jo abhi nahi hua — nakli SUCCESS nahi. (qc_qcn_restore
    bhi yahi istemal karta hai.)"""
    ctx.log(f"{exe.name} mila hai ({exe}) — isay Windows se khud "
            "kholo (tools/qpst/ folder se); MEER ke andar se koi "
            "doosra tool nahi khulta.", "WARN")
    ctx.log("Upar wale steps usi khule hue tool me karo — tayyari "
            "(diag port + file jagah) MEER ne kar di hai.", "INFO")
    return False


def run(ctx) -> bool:
    if not diag_enable(ctx):
        return False
    try:
        QCN_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    dev = ctx.device
    model = (getattr(dev, "model", "") or "qc").replace(" ", "-")
    stamp = datetime.now().strftime("%Y%m%d")
    suggest = QCN_DIR / f"{model}-{stamp}.qcn"
    ctx.log("QCN backup ke steps (khule hue QFIL/QPST me):", "INFO")
    ctx.log("1) Diag port select karo (QFIL status bar me port "
            "nazar ayega).", "INFO")
    ctx.log("2) Tools menu → 'QCN Backup Restore' kholo.", "INFO")
    ctx.log(f"3) Backup QCN dabao aur file yahan save karo: "
            f"{suggest}", "INFO")
    ctx.log("Note: QCN SIRF isi device ki pehchan hai — is file ko "
            "isi phone ke liye rakho; doosre phone/model par ye "
            "file kabhi istemal nahi hoti.", "WARN")
    exe = find_qpst()
    if exe is None:
        ctx.log("QFIL/QPST tools/qpst/ me nahi mila — Qualcomm ka "
                "official tool is package me bundle NAHI hai; "
                "apni copy wahan rakho, phir Windows se khud kholo. "
                "Diag wali tayyari aur steps upar mehfooz hain.",
                "ERROR")
        return False
    ctx.progress(60, "QFIL/QPST ki tayyari mukammal — ab khud kholo")
    return manual_open_guide(ctx, exe)
