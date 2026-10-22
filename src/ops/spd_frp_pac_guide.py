"""
spd_frp_pac_guide.py — SPD / Unisoc ke liye FRP.pac banane ki guide + launcher.

Ye public documented method hai (androidmtk "create FRP SPD research
tool"): stock PAC firmware se Research Download ke andar aik chhota sa
FRP.pac packet banta hai, aur wahi packet flash karne se FRP erase ho
jata hai. Ye op khud packet NAHI banata — steps batata hai, prerequisites
(Research Download exe + stock PAC) check karta hai, aur sab tayyar ho
to Research Download tool khol deta hai.
"""

import subprocess

from core.runner import TOOLS_DIR

OP = {
    "id": "spd_frp_pac_guide",
    "category": "SPD / Unisoc",
    "name": "FRP.pac Guide (SPD Research Tool)",
    "engine": "guide",
    "modes": (),
    "server_required": False,
}

_GUIDE_STEPS = [
    "Tareeqa: 1) Us model ka STOCK PAC firmware Research Download me load karo.",
    "2) Settings (gear) kholo aur tamam partitions UNTICK kar do.",
    "3) Sirf FDL1 + FDL2 (ye default rehne do) ke saath EraseRuntimeNV aur Persist partitions select rakho.",
    "4) Packet button dabao — aik chhota sa tayyar FRP.pac ban jayega.",
    "5) Ab usi FRP.pac ko Research/Upgrade tool me flash karne se FRP erase ho jata hai.",
    "(Advanced surat me Userdata, Cache, EraseMisc, Uboot_Loader bhi packet me shamil kiye jate hain.)",
]


def run(ctx) -> bool:
    for step in _GUIDE_STEPS:
        ctx.log(step, "INFO")

    spd_dir = TOOLS_DIR / "spd"

    research_exe = None
    pac = None
    if spd_dir.is_dir():
        exes = sorted(p for p in spd_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".exe")
        for exe in exes:
            if "research" in exe.name.lower():
                research_exe = exe
                break
        pacs = sorted(p for p in spd_dir.rglob("*")
                      if p.is_file() and p.suffix.lower() == ".pac")
        if pacs:
            pac = pacs[0]

    missing = False
    if pac is None:
        ctx.log("Stock PAC firmware nahi mila — pehle us model ka stock PAC "
                "firmware tools/spd/ me rakho (baghair sahi PAC ke FDL files "
                "nahi milengi — galat PAC = phone brick).", "ERROR")
        missing = True
    if research_exe is None:
        ctx.log("Research Download nahi mila — pehle SPD Official Tools wala "
                "op dekho, Research Download ki copy tools/spd/ me chahiye.",
                "ERROR")
        missing = True
    if missing:
        return False

    ctx.log(f"Research Download mila: {research_exe.name}", "INFO")
    ctx.log(f"PAC firmware mila: {pac.name}", "INFO")
    ctx.progress(50, f"Research Download khola ja raha hai: {research_exe.name}")
    try:
        subprocess.Popen([str(research_exe)], cwd=str(research_exe.parent))
    except Exception as exc:
        ctx.log(f"Research Download khul nahi saka ({research_exe.name}): {exc}",
                "ERROR")
        return False
    ctx.progress(90, "Research Download khul gaya")
    ctx.log("Sab tayyar hai — Research Download khul gaya hai; upar wale "
            "steps se pehle FRP.pac packet banao, phir usi ko flash karo.", "OK")
    return True
