"""
spd_launcher.py — RETIRED launcher (2026-10-25 audit A4).

Ye op pehle Spreadtrum/Unisoc ke bahari tools (Upgrade Download /
Research Download) ko kholta tha. Hamza ka pakka usool hai:
**MEER ke andar se koi doosra tool kabhi nahi khulega** —
"hum doosron ke tool apne tool me rakhen? Jab open karenge to
unka tool khulega???" Is liye launcher khatam kar diya gaya: ab
ye op koi program NAHI kholta, koi subprocess nahi chalata. ID
is liye barqarar rakha hai taake registry / purani fehrist na
toote; naam par RETIRED saaf likha hai.

Is ki jagah asal kaam MEER ke apne engine se hota hai:
  - "Switch to Diag" + Cert Backup / Cert Restore (SPD tab) —
    Diag session se prodnv (IMEI state) kaam.
  - "SPD FRP PAC Guide" / "SPD PAC Builder" — PAC se FRP ka
    rehnumai rasta (Research Tool bahar se khud kholo, MEER
    ke andar se nahi).

tools/spd/ me rakhi .exe/.pac files ab bhi user ki apni hain —
MEER unhe kholta nahi; Research Tool ko Windows se khud kholo
aur PAC wahan load karo.
"""

OP = {
    "id": "spd_launcher",
    "category": "SPD / Unisoc",
    "name": "SPD Official Tools — RETIRED (MEER Engine istemal karo)",
    "engine": "none",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    ctx.log("SPD Official Tools launcher RETIRED hai — MEER ke andar "
            "se koi doosra tool nahi khulta (Hamza ka usool).",
            "WARN")
    ctx.log("Asal rasta: SPD tab se 'Switch to Diag' + Cert Backup / "
            "Cert Restore (MEER ka apna Diag engine). PAC flash "
            "karna ho to Research Tool ko Windows se khud kholo — "
            "tools/spd/ me rakhi .exe/.pac files wahan se load karo.",
            "INFO")
    return False
