"""
spd_frp.py — Unisoc / Spreadtrum standalone FRP erase (FDL session).

Gap jo ye band karta hai (REPAIR-METHODS-RESEARCH §1.3 #1): is se
pehle Unisoc par FRP ka sirf PAC-flash guide ya PayJoy-combo tha —
saada FRP wala one-click op nahi tha. Ab hai:

  spd_dump (engines/spd_dump/) + model ke apne stock PAC se nikle
  signed FDL1/FDL2 → FDL session → `erase_part persist`
  (Unisoc par FRP ka state persist partition me hota hai —
  research §1.2). FDL ya us ke Base addresses na milein to guided
  FAIL — nakli erase kabhi nahi.
"""

from core import spd_fdl

OP = {
    "id": "spd_frp",
    "category": "SPD / Unisoc",
    "name": "Unisoc FRP Erase (FDL / spd_dump)",
    "engine": "spd_dump",
    "modes": ("SPD",),
    "server_required": False,
}


def run(ctx) -> bool:
    if not spd_fdl.spd_guard(ctx):
        return False
    session = spd_fdl.prepare_fdl(ctx)
    if session is None:
        return False
    ctx.log("FRP ka nishana: 'persist' partition (Unisoc FRP state "
            "yahi rehta hai). userdata NAHI mitaya jayega.", "INFO")
    ctx.progress(30, "FDL session — persist erase ho raha hai...")
    cmd = spd_fdl.session_args(session, ["erase_part", "persist",
                                         "power_off"])
    code = spd_fdl.stream_yes(ctx, cmd, timeout=420)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"FRP erase fail hua (spd_dump exit code {code}). Aam "
                "wajahen: FDL is chipset ka nahi, download gadget ka "
                "libusb driver nahi laga, ya phone session se pehle "
                "nikal gaya. Upar spd_dump ki asal lines dekho.",
                "ERROR")
        return False
    ctx.progress(95, "FRP erase mukammal")
    ctx.log("persist erase ho gaya — FRP state khatam. Phone on "
            "karke check karo; setup wizard me purana Google "
            "account NAHI mangna chahiye.", "OK")
    return True
