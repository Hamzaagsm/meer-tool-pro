"""
engine_refresh.py — Engine Refresh Check (MTKClient / DA / Penumbra).

Vendored engines ki freshness report karta hai:
  (a) MTKClient vendored version vs upstream latest release,
  (b) DA .bin files ki inventory (size + sha256),
  (c) Penumbra runnable binary maujood hai ya nahi.

DEFAULT DRY-RUN HAI — is op se koi file change NAHI hoti, na
engine code badalta hai, na version file likhi jati hai. Asal
refresh (version snapshot likhna) ke liye environment variable
MEER_ENGINE_REFRESH_APPLY=1 set karke chalao — tab bhi engine
code khud replace NAHI hota, sirf tools/engine-versions.json
snapshot likha jata hai. Engine ki replacement hamesha manual
re-vendor se hoti hai (insan ki nazar se).
"""

import os

from core import engine_refresh

OP = {
    "id": "engine_refresh",
    "category": "Utility",
    "name": "Engine Refresh Check (MTKClient / DA / Penumbra)",
    "engine": "utility",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    apply = os.environ.get("MEER_ENGINE_REFRESH_APPLY", "") == "1"
    ctx.log("Engine refresh check shuru — "
            + ("APPLY mode (version snapshot likha jayega; engine "
               "code phir bhi replace NAHI hoga)."
               if apply else
               "DRY-RUN mode (sirf report — koi file change nahi)."),
            "INFO")
    try:
        result = engine_refresh.apply_refresh(dry_run=not apply)
    except engine_refresh.RefreshError as e:
        ctx.log(str(e), "ERROR")
        return False
    report = result["report"]
    mc = report["mtkclient"]
    ctx.log(f"MTKClient: vendored {mc['vendored_version'] or '?'} vs "
            f"upstream {mc['latest_tag'] or '?'} "
            f"({mc['upstream_source']}) — status: {mc['status']}",
            "OK" if mc["status"] in ("up_to_date", "ahead_of_release")
            else "WARN")
    if not mc["upstream_reachable"]:
        ctx.log("Upstream live nahi pohancha — fallback (last verified "
                "value) istemal hui: "
                + (mc["upstream_unreachable_reason"] or ""), "WARN")
    da = report["da"]
    ctx.log(f"DA inventory: {da['count']} files "
            f"({da['vendored_count']} vendored, {da['user_count']} user) "
            f"— kul {da['total_bytes']} bytes.", "DATA")
    for f in da["files"]:
        ctx.log(f"  DA {f['name']} [{f['location']}] "
                f"{f['size_bytes']} bytes sha256 "
                f"{f['sha256'][:16]}…", "DATA")
    pen = report["penumbra"]
    ctx.log(f"Penumbra: sources v{pen['sources_version'] or '?'} — "
            f"status: {pen['status']} — {pen['note']}",
            "OK" if pen["status"] == "binary_present" else "WARN")
    ctx.log(f"Penumbra upstream latest: {pen['latest_tag'] or '?'} "
            f"({pen['upstream_source']})", "DATA")
    for action in result["actions"]:
        ctx.log("Action: " + action, "INFO")
    if result["changed_files"]:
        ctx.log("Changed files: " + ", ".join(result["changed_files"]),
                "OK")
    ctx.log("Engine refresh check mukammal — upar wali report hi "
            "asal natija hai; 'update available' ka matlab manual "
            "re-vendor hai, is op se engine khud update NAHI hota.",
            "OK")
    return True
