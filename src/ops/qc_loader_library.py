"""
qc_loader_library.py — Loaders Library ki halat, fehrist aur match.

Library = index (tools/loaders-index.json — 465 verified loaders)
+ asal files (tools/loaders/mtk|qualcomm/<Brand>/), jo Loaders pack
(MEERToolPro-Loaders.zip) se install hoti hain. Ye op:
  - index count vs installed count ki report deta hai,
  - brand ke hisaab se installed loaders ka khulasa dikhata hai,
  - self-match demo chalata hai (Infinix MT6789 / Samsung QC)
    taake baghair device ke hi matching ki tasdeeq ho jaye,
  - device EDL mode me ho to us ke liye asal pick bhi batata hai.

Matching ka asal engine core/loader_library.py hai — EDL ops bhi
wahi istemal karti hain.
"""

from collections import Counter

from core import engines, loader_library
from core.runner import TOOLS_DIR

OP = {
    "id": "qc_loader_library",
    "category": "Qualcomm",
    "name": "EDL Loader Library (Halat / Match)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}


def _demo(ctx, title, ranked):
    if not ranked:
        ctx.log(f"Demo {title}: koi match nahi (library me is brand/"
                "chip ka installed loader nahi).", "WARN")
        return
    top = ranked[0]
    ctx.log(f"Demo {title}: {top['path'].name} — {top['why']}", "DATA")
    if len(ranked) > 1:
        ctx.log(f"Demo {title}: kul {len(ranked)} candidates "
                f"(top tier {top['tier']}).", "INFO")


def run(ctx) -> bool:
    st = loader_library.library_state()
    ctx.log(f"Loaders Library index: {st['index_count']} loaders "
            f"(MTK DA + firehose mila kar).", "INFO")
    ctx.log(f"Install shuda: {st['installed_count']} "
            f"(MTK DA: {st['mtk_installed']}, firehose: "
            f"{st['qc_installed']}).", "INFO")

    if st["installed_count"] == 0:
        note = loader_library.not_installed_note()
        if note:
            ctx.log(note, "ERROR")
        ctx.log("Loaders pack lagne ke baad EDL/DA ops khud sahi "
                "loader chunti hain — 'Loaders Library Import' op "
                "se apne alag loaders bhi andar kar sakte ho.",
                "WARN")
        return False

    inst = loader_library.installed_entries()
    total_bytes = 0
    for e in inst:
        try:
            total_bytes += int(e.get("size", 0))
        except Exception:  # noqa: BLE001
            pass
    by_brand = Counter(
        f"{'MTK' if e.get('type') == 'mtk-da' else 'QC'} · "
        f"{e.get('brand')}" for e in inst)
    for label in sorted(by_brand):
        ctx.log(f"[{label}] {by_brand[label]} loader(s)", "DATA")
    ctx.log(f"Total installed: {st['installed_count']} loader(s), "
            f"{total_bytes / (1024 * 1024):.1f} MB.", "INFO")
    missing = st["index_count"] - st["installed_count"]
    if missing > 0:
        ctx.log(f"Note: index ke {missing} loaders abhi install "
                "nahi (pack adhoora extract hua ho sakta hai, ya "
                "kuch files local index ki hain).", "WARN")

    _demo(ctx, "Infinix MT6789 (MTK DA)",
          loader_library.match_mtk("Infinix", "MT6789"))
    _demo(ctx, "Samsung Snapdragon SM6225 (firehose)",
          loader_library.match_qc("Samsung", "SM6225"))

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
