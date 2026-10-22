"""
qc_sector_read.py — Qualcomm EDL Raw Sector Read (edl `rs`).

TSM/UAT class ke tools raw sector access advertise karte
hain; vendored edl ke paas `rs`/`ws` commands hamare paas
pehle se hain — sirf ops nahi bane thay (TSM-UAT-RESEARCH
§5 G-B).

Inputs GUI ke neeche wale PARAMS bar se atay hain:
  LUN (default 0), Start Sector (default 0),
  Sectors (khali = default 256), Sector Size (khali = auto).
Loader LAZMI hai: brand-signed firehose loader ke baghair
EDL me kuch nahi hota — loader na ho to saaf guided FAIL
(ye SERVER/ASAL hadd hai, tool loaders bundle nahi karta).

Tasdeeq: exit code 0 AUR file ka size count x sector-size
se match (sector size na diya ho to 512 ya 4096 — jo match
ho wahi log me likha jata hai). Aik bhi na mile to FAIL.
"""

from datetime import datetime

from core import engines
from core.runner import BACKUPS_DIR

OP = {
    "id": "qc_sector_read",
    "category": "Qualcomm",
    "name": "Raw Sector Read (EDL rs)",
    "engine": "edl",
    "modes": ("EDL",),
    "server_required": False,
    "params": ("lun", "start_sector", "sectors", "sector_size"),
}

DEFAULT_SECTORS = 256


def parse_sector_params(params, default_sectors=None):
    """GUI params -> dict | (None, err).

    Keys: lun (0), start_sector (0), sectors (default_sectors),
    sector_size (None = auto; sirf 512 ya 4096 qabool).
    Hex (0x..) bhi chalega. Galat value = saaf err.
    """
    params = params or {}

    def _num(key):
        raw = params.get(key)
        if raw is None:
            return None
        raw = str(raw).strip()
        if not raw:
            return None
        return int(raw, 0)

    try:
        lun = _num("lun")
        start = _num("start_sector")
        sectors = _num("sectors")
        ssize = _num("sector_size")
    except (TypeError, ValueError):
        return None, ("PARAMS bar me sirf number (ya 0x.. hex) "
                      "likhen — galat value ki wajah se op roka "
                      "gaya hai.")
    lun = 0 if lun is None else lun
    start = 0 if start is None else start
    sectors = default_sectors if sectors is None else sectors
    if lun < 0:
        return None, "LUN manfi (negative) nahi ho sakta."
    if start < 0:
        return None, "Start Sector manfi (negative) nahi ho sakta."
    if sectors is not None and sectors <= 0:
        return None, "Sectors ki tadaad 0 se bari honi chahiye."
    if ssize is not None and ssize not in (512, 4096):
        return None, ("Sector Size sirf 512 ya 4096 ho sakta hai "
                      "(UFS aksar 4096, eMMC 512) — ya khali "
                      "chhoren (auto).")
    return {"lun": lun, "start_sector": start, "sectors": sectors,
            "sector_size": ssize}, None


def expected_file_sizes(sectors, sector_size):
    """File ke mumkin durust sizes ka set — tasdeeq ke liye
    (pure function). Size diya ho to sirf wahi; na ho to 512
    aur 4096 dono mumkin."""
    if sector_size:
        return {sectors * sector_size}
    return {sectors * 512, sectors * 4096}


def resolve_edl(ctx):
    """(loader:Path) ya None — EDL device + engine + loader
    ka mushtaraka resolver (qc_edl_* ops wali hi shakal)."""
    dev = ctx.device
    if not dev or dev.mode != "EDL":
        ctx.log("Device EDL (9008) mode me nahi mila. Phone band "
                "karke dono volume dabaye cable lagao, ya "
                "test-point / EDL cable istemal karo.", "ERROR")
        return None
    found = engines.find_edl()
    if found is None:
        ctx.log("edl engine nahi mila (app ko dubara extract / "
                "install karo — engines/edl folder ghayab hai).",
                "ERROR")
        return None
    ctx.log(f"EDL engine tayyar: {found[2]}", "INFO")
    loader = engines.pick_qualcomm_loader(dev)
    if loader is None:
        ctx.log("Is brand/model ka firehose loader nahi mila "
                "(tools/loaders/qualcomm/<brand>/ me rakho). "
                "Loader ke baghair EDL me AIK bhi command nahi "
                "chal sakti — loader server-signed hota hai, "
                "tool bundle nahi karta.", "ERROR")
        return None
    ctx.log(f"Loader: {loader}", "INFO")
    return loader


def run(ctx) -> bool:
    loader = resolve_edl(ctx)
    if loader is None:
        return False
    p, err = parse_sector_params(getattr(ctx, "params", {}),
                                 default_sectors=DEFAULT_SECTORS)
    if err:
        ctx.log(err, "ERROR")
        return False
    cmd, cwd = engines.find_edl()
    outdir = BACKUPS_DIR / ("qc-sector-" +
                            datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
        return False
    outfile = outdir / (f"lun{p['lun']}-start{p['start_sector']}"
                        f"-count{p['sectors']}.bin")
    args = ["rs", str(p["start_sector"]), str(p["sectors"]),
            str(outfile), f"--lun={p['lun']}",
            f"--loader={loader}"]
    if p["sector_size"]:
        args.append(f"--sectorsize={p['sector_size']}")
    else:
        ctx.log("Sector Size khali hai — firehose apni default "
                "size istemal karega; tasdeeq 512/4096 dono par "
                "hogi.", "INFO")
    if not str((getattr(ctx, "params", {}) or {})
               .get("sectors") or "").strip():
        ctx.log(f"Note: Sectors khali tha — default "
                f"{DEFAULT_SECTORS} sectors parhe ja rahe hain. "
                "Poora partition parhna ho to PARAMS bar me "
                "tadaad likhen.", "INFO")
    ctx.log(f"LUN {p['lun']}, sector {p['start_sector']} se "
            f"{p['sectors']} sectors parhe ja rahe hain...",
            "INFO")
    ctx.progress(30, "Raw sectors parhe ja rahe hain (EDL)...")
    code = ctx.stream(cmd + args, cwd=cwd, timeout=600)
    if ctx.is_cancelled():
        return False
    if code != 0:
        ctx.log(f"edl rs nakam (exit {code}) — upar ke log me "
                "wajah hai (loader / connection / range).", "ERROR")
        return False
    if not outfile.is_file():
        ctx.log("edl ne 0 kaha lekin output file bani hi nahi — "
                "SUCCESS nahi diya ja raha.", "ERROR")
        return False
    size = outfile.stat().st_size
    possible = expected_file_sizes(p["sectors"], p["sector_size"])
    if size not in possible:
        ctx.log(f"Size mismatch: file {size} bytes hai, mumkin "
                f"durust sizes {sorted(possible)} thay — data "
                "mashkook hai, SUCCESS nahi.", "ERROR")
        return False
    matched = size // p["sectors"]
    ctx.log(f"Sector file: {size} bytes (sector size {matched}) "
            f"— {outfile}", "DATA")
    ctx.log("Raw sector read mukammal — exit code + size, dono "
            "se verify shuda.", "OK")
    ctx.progress(95, "Raw sector read mukammal")
    return True
