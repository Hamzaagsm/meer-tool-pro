"""
qc_edl_info.py — EDL (9008) mode me bkerler edl se GPT / partition info parhna.

Device EDL mode me hona lazmi hai, edl client engines/edl/ se milta hai
aur firehose loader user ki apni library (tools/loaders/qualcomm/) se
uthaya jata hai — koi loader bundle nahi kiya gaya.
"""

from core import engines

OP = {
    "id": "qc_edl_info",
    "category": "Qualcomm",
    "name": "EDL Read Info / GPT",
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
    ctx.progress(20, "GPT parhi ja rahi hai...")
    code = ctx.stream(cmd + ["printgpt", f"--loader={loader}"],
                      timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.progress(95, "GPT parh li gayi")
        return True
    ctx.log(f"edl printgpt fail hua (exit code {code}). Aam wajahen: "
            "loader is model/chip ka nahi hai; 9008 driver (Qualcomm "
            "HS-USB) nahi laga; ya cable/port ka masla hai.", "ERROR")
    return False
