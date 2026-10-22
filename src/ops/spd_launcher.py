"""
spd_launcher.py — SPD / Unisoc ke official tools ka launcher.

Spreadtrum/Unisoc ke official Upgrade Download aur Research Download
tools free hain, lekin is package me bundle NAHI kiye gaye — user apni
copy ke .exe files app ke tools/spd/ folder me rakhta hai, aur ye op
unhi ko yahin se khol deta hai.

GUI tools ko ctx.stream se NAHI kholte (wo block kar dega) —
subprocess.Popen istemal hota hai taake tool alag khul jaye aur
ye op foran wapas aa jaye.
"""

import subprocess

from core.runner import TOOLS_DIR

OP = {
    "id": "spd_launcher",
    "category": "SPD / Unisoc",
    "name": "SPD Official Tools (Upgrade/Research) Launcher",
    "engine": "launcher",
    "modes": (),
    "server_required": False,
}


def _pick_exe(exes):
    """Preference ke hisaab se exe chuno: Upgrade pehle, phir Research."""
    def _rank(path):
        name = path.name.lower()
        if "upgradedownload" in name or "upgrade" in name:
            return 0
        if "researchdownload" in name or "research" in name:
            return 1
        return 2

    return sorted(exes, key=lambda p: (_rank(p), p.name.lower()))[0]


def run(ctx) -> bool:
    spd_dir = TOOLS_DIR / "spd"

    exes = []
    pacs = []
    if spd_dir.is_dir():
        exes = sorted(p for p in spd_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".exe")
        pacs = sorted(p for p in spd_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".pac")

    for pac in pacs:
        try:
            size_mb = pac.stat().st_size / (1024 * 1024)
            ctx.log(f"PAC file mili: {pac.name} ({size_mb:.1f} MB)", "INFO")
        except OSError:
            ctx.log(f"PAC file mili: {pac.name}", "INFO")

    if not exes:
        ctx.log("tools/spd/ folder me koi .exe nahi mila.", "ERROR")
        ctx.log("Spreadtrum/Unisoc ke official Upgrade Download / Research "
                "Download tools free hain lekin is package me bundle NAHI "
                "kiye gaye — apni copy ke .exe files app ke tools/spd/ "
                "folder me rakho, phir ye op unhe yahin se kholega.", "WARN")
        return False

    exe = _pick_exe(exes)
    ctx.progress(40, f"SPD tool khola ja raha hai: {exe.name}")
    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
    except Exception as exc:
        ctx.log(f"SPD tool khul nahi saka ({exe.name}): {exc}", "ERROR")
        return False
    ctx.progress(90, "SPD tool khul gaya")
    ctx.log(f"SPD tool khul gaya hai: {exe.name} — apna kaam wahan se karo "
            "(PAC load karke download/start dabana wahan hota hai).", "OK")
    return True
