"""
mtk_sn_writer.py — RETIRED launcher (2026-10-24).

Ye op pehle MediaTek ke bahari tools (SN Write Tool /
Modem META) ko kholta tha. Hamza ka pakka usool hai:
**MEER ke andar se koi doosra tool kabhi nahi khulega** —
“hum doosron ke tool apne tool me rakhen? Jab open
karenge to unka tool khulega???” Is liye launcher khatam
kar diya gaya: ab ye op koi program NAHI kholta, koi
subprocess nahi chalata. ID is liye barqarar rakha hai
taake registry / purani fehrist na toote; naam par
RETIRED saaf likha hai.

Is ki jagah asal kaam MEER ke apne engine se hota hai:
  - “Restore Original IMEI (META — MEER Engine)”
    (MTK tab) — META session se nvdata ke MP0B_001 par
    asal IMEI parhna/likhna + read-back tasdeeq.
  - “NV Restore (nvram + nvdata)” — apna NV backup ho to
    wohi wapas (sab se saaf rasta, §3.1a).

Neeche wali guide sirf maloomat ke liye mehfooz hai —
official flow aisa hota hai (phone META mode → model ke
stock firmware se AP_DB + MD1_DB load → asal IMEI darj →
write → *#06# check). Is se aik cheez samajh bhi ati
hai: bahari tools ko har model ki DB files is liye
chahiye hoti hain ke IMEI record ka LID har model ka
apna hota hai — universal number koi nahi. MEER ka
native engine us DB/LID raste ki jagah nvdata wali
public-pehchani file (MP0B_001) par chalta hai, isi liye
use kisi model ki DB file nahi chahiye.
"""

from core.imei_gate import IMEI_WARNING

OP = {
    "id": "mtk_sn_writer",
    "category": "MTK",
    "name": "SN Writer / Modem META — RETIRED (Native META IMEI istemal karo)",
    "engine": "none",
    "modes": (),
    "server_required": False,
}

_GUIDE = [
    "=== SN WRITER / MODEM META — PURANA OFFICIAL FLOW "
    "(sirf maloomat) ===",
    "1) Model ka STOCK firmware PC par; us ke andar se "
    "AP_DB aur MD1_DB database files (aksar 'APDB_...' / "
    "'MD1_DB...' naamon se). DB model se match na kare to "
    "write fail hota tha.",
    "2) Bahari tool me target: 'IMEI Download' (SN Writer) "
    "ya IMEI wala section (Modem META); pehle AP_DB, phir "
    "MD1_DB load.",
    "3) Phone META mode me; IMEI wale khane me SIRF dabbe / "
    "sticker wala asal IMEI; Write; aakhir me phone on "
    "karke *#06# se milana.",
    "Note: ye flow ab MEER ke andar se NAHI chalega — "
    "bahari tool kholna Hamza ke usool ke khilaf hai. "
    "Upar sirf tareeqa mehfooz rakha hai taake technician "
    "ko samajh rahe ke DB files kyun mangi jati theen.",
]


def run(ctx) -> bool:
    # Warning ki wording mehfooz — ye hissa IMEI tehreer se
    # juda hai, is liye Hamza ki shart yahan bhi chhapegi.
    ctx.log("=" * 72, "WARN")
    ctx.log(IMEI_WARNING, "WARN")
    ctx.log("=" * 72, "WARN")
    ctx.log("YE OP RETIRE HO CHUKA HAI — ab MEER koi bahari "
            "tool (SN Writer / Modem META) NAHI kholta. "
            "Hamza ka usool hai: har kaam MEER ke apne "
            "engine, apni window, apne log se hoga.",
            "WARN")
    ctx.log("Asal IMEI restore ke liye ye chalao: MTK tab "
            "→ 'Restore Original IMEI (META — MEER Engine)' "
            "— wo META session se khud IMEI parhta/likhta "
            "hai aur read-back se tasdeeq karta hai. Apna "
            "NV backup maujood ho to 'NV Restore (nvram + "
            "nvdata)' us se bhi saaf rasta hai.", "INFO")
    for line in _GUIDE:
        ctx.log(line, "INFO")
    ctx.log("Natija: is retired op ne kuch NAHI kiya — na "
            "koi tool khula, na device ko haath laga. Ye "
            "guided stop hai, error nahi.", "WARN")
    return False
