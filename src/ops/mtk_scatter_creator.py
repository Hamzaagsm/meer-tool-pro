"""
mtk_scatter_creator.py — Scatter Creator (MTK backup → scatter).

backups/ ke sab se naye MTK backup folder (MTKClient readback:
gpt.bin + <partition>.bin files) ki GPT se SP Flash Tool
wala scatter .txt banata hai — backup ko flashable
dead-boot-repair asset banane ke liye (COMPETITOR-RESEARCH-3
§4 P1). Khalis local file op hai: koi device/engine nahi.

Imaandari: scatter ke start/size GPT ke asal values hain.
Banne ke baad scatter ko is tool ke apne Platforms parser
(core.platforms_mtk.parse_scatter) se dobara parh kar verify
kiya jata hai. Asal flash ki tasdeeq phone + DA ke saath hi
hogi — ye op sirf file banata hai, flash nahi karta.
"""

from core import scatter_build
from core.runner import BACKUPS_DIR

OP = {
    "id": "mtk_scatter_creator",
    "category": "MTK",
    "name": "Scatter Creator (Backup GPT → Scatter)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    folder = scatter_build.find_latest_mtk_backup(BACKUPS_DIR)
    if folder is None:
        ctx.log("backups/ me koi MTK backup folder nahi mila jisme "
                "gpt.bin ho. Pehle MTK 'Full Backup / Readback' op "
                "chalao — us ki readback me gpt.bin + partition "
                "images hote hain, scatter unhi se banta hai.", "ERROR")
        return False
    ctx.log(f"Backup folder: {folder}", "INFO")

    gpt_path = scatter_build.find_gpt_file(folder)
    try:
        partitions = scatter_build.parse_gpt_binary(
            gpt_path.read_bytes())
    except Exception as e:  # noqa: BLE001
        ctx.log(f"GPT parhne me ghalti ({gpt_path.name}): {e}", "ERROR")
        return False
    ctx.log(f"GPT se {len(partitions)} partitions mile:", "INFO")
    for part in partitions:
        ctx.log(f"  {part['name']:20s} start={hex(part['start_bytes'])} "
                f"size={part['size_bytes']:,} bytes", "DATA")

    file_names, warnings = scatter_build.match_files(folder, partitions)
    for warn in warnings:
        ctx.log(warn, "WARN")
    with_files = sum(1 for v in file_names.values() if v)
    ctx.log(f"{with_files}/{len(partitions)} partitions ki image "
            "files folder me maujood hain (baki scatter me "
            "is_download: false hongi).", "INFO")

    ctx.progress(50, "Scatter ban raha hai...")
    text = scatter_build.build_scatter_text(partitions, file_names)
    out_path = folder / f"{folder.name}_scatter.txt"
    try:
        out_path.write_text(text, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Scatter file likhi nahi gayi: {e}", "ERROR")
        return False
    ctx.log(f"Scatter tayyar: {out_path}", "OK")

    ctx.progress(80, "Scatter verify ho raha hai (dobara parh kar)...")
    from core.platforms_mtk import parse_scatter
    parsed = parse_scatter(out_path)
    expected = {name for name, fname in file_names.items() if fname}
    if set(parsed) != expected:
        ctx.log("Verify FAIL: scatter dobara parhne par download "
                f"entries match nahi huin (mile: {sorted(parsed)}, "
                f"expected: {sorted(expected)}).", "ERROR")
        return False
    ctx.log(f"Verify PASS: scatter dobara parhi gayi — "
            f"{len(parsed)} download entries bilkul sahi mile.",
            "OK")
    ctx.log("Note: ye scatter MTK tab ke Flash op / SP Flash Tool "
            "se istemal hoga; asal flash se pehle sahi DA lazmi "
            "hai, aur preloader wali entries par khaas ehtiyat "
            "rakho (ghalat preloader = dead boot).", "INFO")
    ctx.progress(95, "Scatter Creator mukammal")
    return True
