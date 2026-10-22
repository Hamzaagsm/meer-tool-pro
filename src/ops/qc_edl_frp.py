"""
qc_edl_frp.py — EDL (9008) mode me FRP partition erase karna.

bkerler edl ke `e frp` se sirf frp partition erase hota hai. Kuch models
me is partition ka naam alag hota hai — fail hone par pehle GPT se asal
naam confirm karne ki hidayat log me di jati hai.
"""

from core import engines

OP = {
    "id": "qc_edl_frp",
    "category": "Qualcomm",
    "name": "EDL FRP Erase",
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
        ctx.log("Guide: koi firehose loader bundle NAHI kiya gaya "
                "(brand-signed files hoti hain) — apne loaders app ke "
                "tools/loaders/qualcomm/<brand>/ folder me rakho.", "WARN")
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
    ctx.progress(20, "FRP partition erase ho raha hai...")
    code = ctx.stream(cmd + ["e", "frp", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "FRP erase mukammal")
        return True
    ctx.log(f"edl FRP erase fail hua (exit code {code}).", "ERROR")
    ctx.log("Note: kuch models me partition ka naam alag hota hai — "
            "pehle 'EDL Read Info / GPT' se GPT me FRP partition ka "
            "asal naam confirm karo.", "INFO")
    return False
