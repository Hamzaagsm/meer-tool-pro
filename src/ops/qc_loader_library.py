"""
qc_loader_library.py — Qualcomm firehose loaders ki library dekhna / match karna.

Loaders brand-signed files hoti hain, is liye app ke saath koi loader
bundle NAHI kiya gaya — user apne loaders tools/loaders/qualcomm/<brand>/
folders me rakhta hai aur EDL ops wahin se uthate hain. Ye op library ki
fehrist dikhata hai aur, agar device EDL mode me ho, to us ke liye sahi
loader match karke bhi batata hai.
"""

from core import engines
from core.runner import TOOLS_DIR

OP = {
    "id": "qc_loader_library",
    "category": "Qualcomm",
    "name": "EDL Loader Library (List / Match)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    loaders = engines.scan_qualcomm_loaders()
    if not loaders:
        ctx.log("Loader library khali hai — koi firehose loader nahi mila.", "ERROR")
        ctx.log("Firehose loaders (.elf/.mbn) brand-signed files hoti hain, "
                "is liye koi loader bundle NAHI kiya gaya.", "WARN")
        ctx.log("Apne loaders app ke tools/loaders/qualcomm/<brand>/ "
                "(masalan xiaomi/, oppo/, vivo/) folders me rakho — "
                "EDL ops khud wahan se uthayengi.", "WARN")
        return False

    base = TOOLS_DIR / "loaders" / "qualcomm"
    total_bytes = 0
    for loader in loaders:
        try:
            rel_parent = loader.parent.relative_to(base)
            brand = str(rel_parent) if str(rel_parent) != "." else "(root)"
        except ValueError:
            brand = loader.parent.name
        try:
            size = loader.stat().st_size
        except OSError:
            size = 0
        total_bytes += size
        ctx.log(f"[{brand}] {loader.name} — {size / (1024 * 1024):.2f} MB", "DATA")

    ctx.log(f"Total: {len(loaders)} loader(s), "
            f"{total_bytes / (1024 * 1024):.2f} MB.", "INFO")

    dev = ctx.device
    if dev and dev.mode == "EDL":
        pick, note = engines.pick_qualcomm_loader(dev)
        if pick is not None:
            if note:
                ctx.log(note, "INFO")
            ctx.log(f"Device ke liye loader match: {pick.name}", "OK")
        else:
            ctx.log(note, "WARN")
    return True
