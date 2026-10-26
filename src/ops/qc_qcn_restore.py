"""
qc_qcn_restore.py — Qualcomm QCN restore (QPST/QFIL guided flow).

QCN wapas likhna NV/IMEI wala kaam hai — is liye:
  1. **IMEI gate** sab se pehle (warning + tasdeeq) —
     core/imei_gate.py. Baghair tasdeeq aage kuch nahi hota.
  2. Restore SIRF tools/qcn/ me maujood usi device ki apni
     backup file se hota hai — file na ho to FAIL.
  3. Model-match ki sakht warning: doosre model ki QCN brick
     kar sakti hai (documented technician warning) — file ka
     naam log me wazeh ata hai taake technician khud tasdeeq
     kare ke ye usi phone ki file hai.
Asal transfer QFIL/QPST ke andar hota hai — QFIL ko Windows se
khud kholo (MEER ke andar se koi tool nahi khulta; 2026-10-25
audit A4). Diag tayyari qc_qcn_backup se hi milti hai.
"""

from core.imei_gate import imei_write_gate
from ops.qc_qcn_backup import QCN_DIR, diag_enable, find_qpst, manual_open_guide

OP = {
    "id": "qc_qcn_restore",
    "category": "Qualcomm",
    "name": "QCN Restore (QPST/QFIL Guide) — Original IMEI",
    "engine": "qpst",
    "modes": ("ADB",),
    "server_required": False,
    "imei_write": True,
}


def _latest_qcn():
    if not QCN_DIR.is_dir():
        return None
    files = sorted(QCN_DIR.glob("*.qcn"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def run(ctx) -> bool:
    # IMEI GATE — warning + tasdeeq sab se pehle.
    if not imei_write_gate(ctx):
        return False
    qcn = _latest_qcn()
    if qcn is None:
        ctx.log("tools/qcn/ me koi .qcn backup file nahi mili — "
                "pehle 'QCN Backup' se isi device ki file banao ya "
                "apni mehfooz file wahan rakho. Baghair apni file "
                "ke restore mumkin nahi.", "ERROR")
        return False
    ctx.log(f"Restore ki file: {qcn.name} "
            f"({qcn.stat().st_size} bytes)", "DATA")
    ctx.log("⚠️ MODEL TASDEEQ: ye file SIRF usi device/model ki "
            "honi chahiye jis ki backup li gayi thi. Doosre model "
            "ki QCN restore karna phone brick kar sakta hai — "
            "naam dekh kar khud tasdeeq karo, phir aage barho.",
            "WARN")
    if not diag_enable(ctx):
        return False
    exe = find_qpst()
    if exe is None:
        ctx.log("QFIL/QPST tools/qpst/ me nahi mila — Qualcomm ka "
                "official tool bundle NAHI hai; apni copy wahan "
                "rakho. File aur tayyari upar mehfooz hai.", "ERROR")
        return False
    ctx.log("QCN restore ke steps (khule hue QFIL/QPST me):", "INFO")
    ctx.log("1) Diag port select karo.", "INFO")
    ctx.log("2) Tools → 'QCN Backup Restore' kholo.", "INFO")
    ctx.log(f"3) Restore QCN me ye file select karo: {qcn}", "INFO")
    ctx.log("4) Restore ke baad phone restart karke *#06# se "
            "dabbe wala asal IMEI milao.", "INFO")
    ctx.progress(60, "QFIL/QPST ki tayyari mukammal — ab khud kholo")
    return manual_open_guide(ctx, exe)
