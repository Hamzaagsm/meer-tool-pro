"""
spd_pac_builder.py — PAC Builder (Unisoc readback → .pac).

backups/ ke sab se naye Unisoc readback folder (partition
images) se public PAC format me .pac banata hai — Cheetah
v192 / CM2 wale "PAC File Builder" ki free parity
(COMPETITOR-RESEARCH-3 §2.1). Khalis local file op hai: koi
device nahi chahiye.

Imaandari:
  - FDL1 na ho to pac NAHI banti — saaf wajah ke saath FAIL
    (FDL ke baghair pac flash ho hi nahi sakti).
  - Banne ke baad pac ko apne parser se dobara parh kar
    verify kiya jata hai (header + item table + har file ka
    CRC) — verify pass hue baghair SUCCESS nahi.
  - Structure public PAC layout par hai; kisi asal pac ki
    pehli pakki tasdeeq official Upgrade/Research tool me
    "Load Packet" karke hogi.
"""

from core import pac_builder
from core.runner import BACKUPS_DIR

OP = {
    "id": "spd_pac_builder",
    "category": "SPD / Unisoc",
    "name": "PAC Builder (Readback → .pac)",
    "engine": "pac",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    folder = pac_builder.find_readback_folder(BACKUPS_DIR)
    if folder is None:
        ctx.log("backups/ me koi Unisoc readback folder nahi mila. "
                "Pehle Research Download se kisi Unisoc phone ka "
                "readback lo aur us ke partition images (.bin) wala "
                "folder backups/ me rakho — jisme fdl1.bin shamil "
                "ho.", "ERROR")
        return False
    ctx.log(f"Readback folder: {folder}", "INFO")

    items, errors, warnings = pac_builder.validate_readback(folder)
    for warn in warnings:
        ctx.log(warn, "WARN")
    if errors:
        for err in errors:
            ctx.log(err, "ERROR")
        ctx.log("PAC NAHI bani — upar ki kamiyan poori karke dobara "
                "try karo.", "ERROR")
        return False

    ctx.log(f"{len(items)} partition images mile:", "INFO")
    for it in items:
        ctx.log(f"  {pac_builder.file_id_for(it['name']):12s} "
                f"{it['name']:24s} {it['size']:>12,} bytes", "DATA")

    product = folder.name
    out_path = BACKUPS_DIR / f"{product}.pac"
    ctx.progress(40, "PAC ban rahi hai...")
    try:
        summary = pac_builder.build_pac(items, out_path, product)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"PAC banane me ghalti: {e}", "ERROR")
        return False
    ctx.log(f"PAC tayyar: {out_path} "
            f"({summary['total_size']:,} bytes, "
            f"{summary['file_count']} files)", "OK")

    ctx.progress(75, "PAC verify ho rahi hai (dobara parh kar)...")
    try:
        parsed = pac_builder.parse_pac(out_path)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Verify FAIL — bani hui PAC dobara parhi nahi gayi: {e}",
                "ERROR")
        return False
    problems = []
    if parsed["total_size"] != parsed["file_size_actual"]:
        problems.append("header ka dwSize asal file size se match "
                        "nahi karta")
    if parsed["file_count"] != summary["file_count"]:
        problems.append("file count match nahi karta")
    if not parsed["crc1_ok"] or not parsed["crc2_ok"]:
        problems.append("PAC CRC match nahi karta")
    for ent in parsed["entries"]:
        if not ent["crc_ok"]:
            problems.append(f"{ent['file_name']} ka data CRC match "
                            "nahi karta")
    if problems:
        for prob in problems:
            ctx.log(f"Verify FAIL: {prob}", "ERROR")
        return False
    ctx.log("Verify PASS: header + item table + tamam files ke CRC "
            "dobara parh kar match ho gaye.", "OK")
    ctx.log("Note: structure public PAC layout par bani hai — pehli "
            "asal tasdeeq official Upgrade/Research tool me is pac "
            "ko 'Load Packet' karke hogi (SPD Official Tools "
            "launcher is tool me maujood hai).", "INFO")
    ctx.progress(95, "PAC Builder mukammal")
    return True
