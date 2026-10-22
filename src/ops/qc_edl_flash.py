"""
qc_edl_flash.py — EDL (9008) mode me QFIL firmware flash (rawprogram).

Firmware ka poora folder tools/firmware-qc/ me rakha jata hai
(rawprogram*.xml, patch*.xml aur tamam .img files). Ye asal flash hai —
ghalat firmware ya loader se phone hard-brick ho sakta hai, is liye
shuru me saaf warning aur pehle backup ki hidayat di jati hai.
"""

from core import engines
from core.runner import TOOLS_DIR

OP = {
    "id": "qc_edl_flash",
    "category": "Qualcomm",
    "name": "EDL Flash (QFIL rawprogram)",
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


def run(ctx) -> bool:
    resolved = _resolve_edl(ctx)
    if resolved is None:
        return False
    cmd, cwd, loader = resolved

    fwdir = TOOLS_DIR / "firmware-qc"
    raw_candidates = []
    if fwdir.is_dir():
        raw_candidates = sorted(fwdir.glob("rawprogram*.xml"))
    if not raw_candidates:
        ctx.log("QFIL firmware nahi mila — rawprogram*.xml maujood nahi hai.", "ERROR")
        ctx.log("Guide: QFIL firmware ka poora folder (rawprogram*.xml, "
                "patch*.xml aur tamam .img files) tools/firmware-qc/ "
                "me rakho.", "WARN")
        return False
    raw = None
    for cand in raw_candidates:
        if "unsparse" in cand.name.lower():
            raw = cand
            break
    if raw is None:
        raw = raw_candidates[0]
    ctx.log(f"rawprogram: {raw.name}", "INFO")

    patch_candidates = sorted(fwdir.glob("patch*.xml")) if fwdir.is_dir() else []
    if not patch_candidates:
        ctx.log("patch xml nahi mila — flash aage nahi barhega.", "ERROR")
        ctx.log("Guide: patch xml (aam tor par patch0.xml) firmware ke "
                "saath lazmi hai — use bhi tools/firmware-qc/ me rakho.", "WARN")
        return False
    patch = patch_candidates[0]
    ctx.log(f"patch: {patch.name}", "INFO")

    ctx.log("KHABARDAR: ye asal EDL flash hai — ghalat firmware/loaders "
            "se phone hard-brick ho sakta hai; pehle backup lo.", "WARN")

    ctx.progress(10, "QFIL flash chal raha hai — cable bilkul na hilao...")
    code = ctx.stream(
        cmd + ["qfil", str(raw), str(patch), str(fwdir), f"--loader={loader}"],
        timeout=3600, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "Flash mukammal")
        return True
    ctx.log(f"edl qfil flash fail hua (exit code {code}). Firmware is "
            "model ke liye hai ya nahi, loader aur cable dobara check karo.", "ERROR")
    return False
