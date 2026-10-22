"""
mtk_nv_format.py — MTK NVRAM + NVDATA format (IMEI khatam ho jayega!).

SAB SE KHATARNAK NV op: nvram aur nvdata dono erase karne se
phone ka IMEI / NV data mit jata hai — phone "invalid IMEI" /
no-service halat me ja sakta hai. Ye op tab istemal hota hai jab
NV itna kharab ho ke saaf slate par dobara likhna hi wahid rasta
ho. Isi liye:

  - Shuru me bhaari warnings log hoti hain: pehle 'NV Backup
    (nvram + nvdata)' wala op chala kar backup lazmi lo.
  - Dono erase FATAL hain — aik bhi fail ho to FAIL; aadha format
    success NAHI kaha jata (warna phone na idhar ka na udhar ka).
  - Wapas lane ka rasta bhi log me saaf likha hai: NV Restore
    (backup se) ya SN Writer (dabbe/sticker wala asal IMEI).
"""

from core import engines
from ops.mtk_frp_reset import _engine, _guard

OP = {
    "id": "mtk_nv_format",
    "category": "MTK",
    "name": "Format NVRAM + NVDATA (IMEI khatam ho jayega!)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


def run(ctx) -> bool:
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False
    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")

    ctx.log("=" * 72, "WARN")
    ctx.log("KHABARDAR: NVRAM + NVDATA format se phone ka IMEI aur "
            "NV data MIT jayega — phone 'invalid IMEI' ho sakta hai "
            "aur network (calls/signals) band ho sakta hai.", "WARN")
    ctx.log("PEHLE 'NV Backup (nvram + nvdata)' wala op chala kar "
            "backup LAZMI lo — baghair backup ke ye format mat "
            "karo. Backup ho to wapas lane ka rasta 'NV Restore' "
            "hai; warna SN Writer se dabbe/sticker wala ASAL IMEI "
            "dobara likhna parega.", "WARN")
    ctx.log("=" * 72, "WARN")
    ctx.log("Phone ko cable se mat hatana — aadha format phone ko "
            "na idhar ka na udhar ka kar sakta hai.", "WARN")

    # (a) nvram erase — fail = overall FAIL
    ctx.progress(20, "NVRAM format ho raha hai...")
    ctx.log("Step 1/2: NVRAM erase (e nvram)", "INFO")
    code = ctx.stream(cmd + ["e", "nvram"] + extra,
                      timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"NVRAM erase fail hua (exit code {code}) — format "
                "yahin ruk gaya hai, NVDATA ko NAHI chua gaya. "
                "Cable/BROM check karke dobara koshish karo ya NV "
                "Restore se purani halat wapas lao.", "ERROR")
        return False
    ctx.log("NVRAM erase ho gaya.", "OK")

    # (b) nvdata erase — fail = overall FAIL (SUCCESS sirf dono par)
    ctx.progress(60, "NVDATA format ho raha hai...")
    ctx.log("Step 2/2: NVDATA erase (e nvdata)", "INFO")
    code = ctx.stream(cmd + ["e", "nvdata"] + extra,
                      timeout=180, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"NVDATA erase fail hua (exit code {code}) — NVRAM "
                "mit chuka hai lekin NVDATA baqi hai; ye AADHA "
                "format hai, success NAHI hai. NV Restore se backup "
                "wapas likho ya dobara format ki koshish karo.",
                "ERROR")
        return False
    ctx.log("NVDATA erase ho gaya.", "OK")

    ctx.progress(95, "NVRAM + NVDATA format mukammal")
    ctx.log("Format mukammal: NVRAM + NVDATA dono saaf — IMEI "
            "khatam ho chuka hai. Ab 'NV Restore' se backup wapas "
            "likho ya SN Writer se dabbe/sticker wala asal IMEI "
            "likho, warna phone invalid IMEI par rahega.", "OK")
    return True
