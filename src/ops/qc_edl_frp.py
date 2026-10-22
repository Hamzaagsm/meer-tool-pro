"""
qc_edl_frp.py — EDL (9008) mode me FRP erase — **v2: GPT-driven**.

v1 sirf `frp` naam ki partition mitata tha. Lekin FRP ka state
har OEM par usi naam se nahi hota: Samsung Qualcomm par ye
`persistent` me hai, kuch Xiaomi/Oppo builds par `config` me.
Is liye v2 (REPAIR-METHODS-RESEARCH §4 P1#1):

  1. Pehle device ki GPT parhi jati hai (edl `gpt` dump →
     core/gpt_parse se asal partition naam).
  2. GPT ki poori list log me ati hai.
  3. Jo naam milein — frp / persistent / config — sirf wahi
     erase hote hain, aur log me wazeh likha jata hai ke kya mita.
  4. **HARD GUARD:** `persist` kabhi erase nahi hota — QC par
     persist calibration (sensors/fingerprint) hai, FRP nahi.
     GPT me sirf persist mile to op saaf inkaar kar deta hai.
"""

from datetime import datetime

from core import engines, gpt_parse
from core.runner import BACKUPS_DIR

OP = {
    "id": "qc_edl_frp",
    "category": "Qualcomm",
    "name": "EDL FRP Erase v2 (GPT-driven)",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
}


def _resolve_edl(ctx):
    """Guard + engine + loader — (cmd, cwd, loader) ya None (FAIL tayyar)."""
    dev = ctx.device
    if not dev or dev.mode != "EDL":
        ctx.log("Device EDL (9008) mode me nahi mila. Phone band karke "
                "Volume Up+Down dono dabaye hue cable lagao — Device "
                "Manager me 'Qualcomm HS-USB QDLoader 9008' ana chahiye.", "ERROR")
        return None
    cmd, cwd, note = engines.find_edl()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("EDL client"):
                ctx.log(line, "WARN")
        else:
            ctx.log(note, "ERROR")
            ctx.log("Guide: engines/edl/ me edl client ki copy honi chahiye.", "WARN")
        return None
    ctx.log(note, "INFO")
    loader, lnote = engines.pick_qualcomm_loader(dev)
    if loader is None:
        ctx.log(lnote, "ERROR")
        ctx.log("Guide: loaders Loaders Library "
                "(tools/loaders/qualcomm/) se ate hain — pack install "
                "hai ya nahi, 'EDL Loader Library' op se check karo; "
                "apne alag loaders bhi wahan <brand>/ subfolder me "
                "rakh sakte ho, ya 'Loaders Library Import' op se "
                "andar kar sakte ho.", "WARN")
        return None
    if lnote:
        ctx.log(lnote, "INFO")
    ctx.log(f"Loader: {loader}", "INFO")
    return cmd, cwd, loader


def _read_gpt(ctx, cmd, cwd, loader):
    """{lun: [naam]} ya None — GPT dump + parse, nakami par log tayyar."""
    gpt_dir = BACKUPS_DIR / ("qc-gpt-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        gpt_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"GPT dump folder nahi ban saka: {e}", "ERROR")
        return None
    ctx.progress(15, "GPT parhi ja rahi hai (partition naam confirm karne ke liye)...")
    code = ctx.stream(cmd + ["gpt", str(gpt_dir), f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return None
    if code != 0:
        ctx.log(f"GPT dump fail hua (exit code {code}) — baghair GPT "
                "ke partition naam ka andaza NAHI lagega (galat naam = "
                "fail ya ghalat partition ka risk). Loader is model ka "
                "sahi hai ya nahi, pehle 'EDL Read Info / GPT' se "
                "tasdeeq karo.", "ERROR")
        return None
    tables = {}
    for path in sorted(gpt_dir.glob("gpt_main*.bin")):
        lun_txt = path.stem.replace("gpt_main", "")
        try:
            lun = int(lun_txt) if lun_txt else 0
        except ValueError:
            lun = 0
        try:
            names = gpt_parse.parse_gpt(path.read_bytes())
        except (ValueError, OSError) as e:
            ctx.log(f"{path.name} parse nahi hua: {e}", "WARN")
            continue
        tables[lun] = names
    if not tables:
        ctx.log("GPT dump aya lekin koi table parse nahi hua — is "
                "halat me erase nahi hoga. Asal dump yahan mehfooz "
                f"hai: {gpt_dir}", "ERROR")
        return None
    for lun in sorted(tables):
        ctx.log(f"GPT (LUN {lun}) — {len(tables[lun])} partitions: "
                + ", ".join(tables[lun]), "DATA")
    return tables


def run(ctx) -> bool:
    resolved = _resolve_edl(ctx)
    if resolved is None:
        return False
    cmd, cwd, loader = resolved

    tables = _read_gpt(ctx, cmd, cwd, loader)
    if tables is None:
        return False
    if ctx.is_cancelled():
        return False

    # Har LUN ka plan — persist kabhi plan me nahi (gpt_parse guard)
    plans = {}
    refusals = []
    for lun in sorted(tables):
        erase, refusal = gpt_parse.frp_erase_plan(tables[lun])
        if erase:
            plans[lun] = erase
        elif refusal:
            refusals.append((lun, refusal))
    if not plans:
        for lun, (rcode, wajah) in refusals:
            ctx.log(f"LUN {lun}: {wajah}", "ERROR")
        ctx.log("FRP erase NAHI hua — upar wajah wazeh hai.", "ERROR")
        return False
    for lun, (rcode, wajah) in refusals:
        ctx.log(f"LUN {lun}: {wajah} (is LUN par kuch nahi mita)", "WARN")

    erased = []
    total = sum(len(v) for v in plans.values())
    done = 0
    for lun in sorted(plans):
        for name in plans[lun]:
            if ctx.is_cancelled():
                return False
            done += 1
            ctx.progress(30 + int(60 * done / max(total, 1)),
                         f"{name} erase ho raha hai (LUN {lun})...")
            ctx.log(f"Erase: {name} (LUN {lun})", "INFO")
            code = ctx.stream(
                cmd + ["e", name, f"--lun={lun}", f"--loader={loader}"],
                timeout=300, cwd=cwd)
            if code != 0:
                ctx.log(f"{name} erase fail hua (exit code {code}). "
                        f"Ab tak erase hue: "
                        f"{', '.join(erased) if erased else 'koi nahi'}",
                        "ERROR")
                return False
            erased.append(f"{name}@LUN{lun}")
            ctx.log(f"{name} erase ho gaya.", "OK")
    ctx.log("FRP erase mukammal — ye partitions mitaye gaye: "
            + ", ".join(erased), "OK")
    if "persist" in {n.lower() for names in tables.values() for n in names}:
        ctx.log("Note: 'persist' GPT me maujood tha aur use jaan-boojh "
                "kar NAHI chua gaya — wo calibration hai, FRP nahi.",
                "INFO")
    ctx.progress(95, "FRP erase mukammal")
    return True
