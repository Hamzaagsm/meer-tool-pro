"""
util_repair_intel.py — Repair Intelligence (Error Library).

tools/repair-intel.json ki tamam entries live log me saaf
fehrist ki surat me deta hai — error code/pattern, wajah aur
hal ke steps. GUI wala search Firmware Center ke Repair
Intelligence khane me hai; ye op bina GUI ke poori library
aik nazar me dikhata hai (aur ye bhi ke runner har FAIL hue
op ke aakhir me inhi patterns se log scan karke hint khud
jor deta hai).

Seed entries vendored engines ke asal error strings/codes
se grounded hain (har entry ka source darj hai) +
public documented SP Flash Tool errors. Device ki zaroorat
nahi (modes ()).
"""

from __future__ import annotations

from core import repair_intel

OP = {
    "id": "util_repair_intel",
    "category": "Utility",
    "name": "Repair Intelligence (Error Code / Wajah / Hal Library)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    entries = repair_intel.load_entries()
    if not entries:
        ctx.log("Repair Intelligence ki library nahi mili ya "
                "khaali hai (tools/repair-intel.json).", "ERROR")
        ctx.log("Guide: app ke tools/ folder me repair-intel.json "
                "hona chahiye — app dobara extract karke dekho.",
                "WARN")
        return False
    ctx.log(f"Repair Intelligence — {len(entries)} maloom "
            "error patterns (har aik ka source darj hai):", "INFO")
    for i, e in enumerate(entries, 1):
        head = f"{i}. {e['title']}"
        if e["code"]:
            head += f"  [{e['code']}]"
        ctx.log(head, "INFO")
        if e["wajah"]:
            ctx.log(f"   Wajah: {e['wajah']}", "DATA")
        for step in e["hal_steps"]:
            ctx.log(f"   Hal: {step}", "DATA")
        if e["source"]:
            ctx.log(f"   Source: {e['source']}", "DATA")
    ctx.log("Note: koi op FAIL ho to runner us ke log ko inhi "
            "patterns se khud scan karta hai — match mile to "
            "'💡 Repair Intelligence' hint aakhir me khud ajata "
            "hai. GUI search: FIRMWARE module ke Repair "
            "Intelligence khane me.", "INFO")
    return True
