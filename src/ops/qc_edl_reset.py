"""
qc_edl_reset.py — EDL (9008) mode me factory reset (userdata + metadata erase).

Tarteeb: pehle userdata erase (fail = FAIL), phir metadata erase (har
model me ye partition nahi hota — fail sirf WARN), aakhir me device reset.
"""

from core import engines

OP = {
    "id": "qc_edl_reset",
    "category": "Qualcomm",
    "name": "EDL Factory Reset (userdata/metadata)",
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

    ctx.progress(20, "userdata erase ho raha hai...")
    code = ctx.stream(cmd + ["e", "userdata", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"userdata erase fail hua (exit code {code}) — reset "
                "aage nahi barhega.", "ERROR")
        return False
    ctx.log("userdata erase ho gaya.", "OK")

    if ctx.is_cancelled():
        return False
    ctx.progress(55, "metadata erase ho raha hai...")
    code = ctx.stream(cmd + ["e", "metadata", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"metadata erase nahi hua (exit code {code}) — har model "
                "me ye partition nahi hota, is liye aage barh rahe hain.", "WARN")
    else:
        ctx.log("metadata erase ho gaya.", "OK")

    if ctx.is_cancelled():
        return False
    ctx.progress(85, "Device reset ho raha hai...")
    code = ctx.stream(cmd + ["reset", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if code != 0:
        ctx.log(f"Reset ka hukum nahi gaya (exit code {code}) — erase ho "
                "chuka hai, phone ko manual on kar lo.", "WARN")
    else:
        ctx.log("Reset ka hukum bhej diya.", "OK")
    ctx.progress(95, "Factory reset mukammal")
    return True
