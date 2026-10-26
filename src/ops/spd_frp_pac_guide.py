"""
spd_frp_pac_guide.py — SPD / Unisoc ke liye FRP.pac banane ki guide.

Ye public documented method hai (androidmtk "create FRP SPD research
tool"): stock PAC firmware se Research Download ke andar aik chhota sa
FRP.pac packet banta hai, aur wahi packet flash karne se FRP erase ho
jata hai. Ye op khud packet NAHI banata — steps batata hai aur
prerequisites (Research Download exe + stock PAC) check karta hai.
Research Download ko Windows se khud kholna hota hai — MEER ke andar
se koi doosra tool NAHI khulta (Hamza ka usool; 2026-10-25 audit A4 —
pehle ye op tool khol deta tha, ab retired).
"""

from core.runner import TOOLS_DIR

OP = {
    "id": "spd_frp_pac_guide",
    "category": "SPD / Unisoc",
    "name": "FRP.pac Guide (Research Tool khud kholo)",
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
        ctx.log("Research Download nahi mila — SPD Official Tools ki "
                "copy tools/spd/ me rakho, phir Windows se khud kholo "
                "(MEER ke andar se koi tool nahi khulta).", "ERROR")
        missing = True
    if missing:
        return False

    ctx.log(f"Research Download mila: {research_exe.name}", "INFO")
    ctx.log(f"PAC firmware mila: {pac.name}", "INFO")
    ctx.log("Sab tayyar hai — Research Download ko Windows se khud "
            "kholo (tools/spd/ folder se); upar wale steps se pehle "
            "FRP.pac packet banao, phir usi ko flash karo.", "WARN")
    ctx.log("Ye op guide de kar rukta hai — FRP erase ka asal kaam "
            "Research Download ke andar hota hai, MEER ke andar nahi.",
            "INFO")
    return False
