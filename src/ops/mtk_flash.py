"""
mtk_flash.py — MTKClient se stock firmware flash karna (scatter file se).

User apna poora stock firmware folder tools/firmware/ me rakhta hai.
Ye op scatter file (.txt, naam me 'scatter') dhoondhta hai, us ke
`is_download: true` wale partitions aik-aik karke `w` se likhta hai.

Ye ASAL flash hai — ghalat firmware phone ko brick kar sakta hai.
Is liye queue khali ho, file ghayab ho ya koi partition fail ho to
saaf FAIL milta hai; adhoora kaam success nahi kaha jata. Flash se
pehle Backup op se backup lena sab se behtareen hifazat hai.
"""

from core import engines
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_flash",
    "category": "MTK",
    "name": "Flash Firmware (Scatter)",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}

FIRMWARE_DIR = TOOLS_DIR / "firmware"


def _engine(ctx):
    """(cmd_prefix, cwd) ya (None, None) — nakami par guided log de chuka hoga."""
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke engines/mtkclient/ "
                "folder me rakho, ya system me 'mtk' command install karo. "
                "Engine ke baghair ye operation chal hi nahi sakta — "
                "ye nakami nahi, setup ki kami hai.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def _guard(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band karke "
                "Volume dono dabaye hue cable lagao (kuch models par "
                "test-point lagta hai).", "ERROR")
        return False
    return True


def _find_scatter():
    """tools/firmware/ me scatter file — zyada se zyada 2 level gehrai tak."""
    if not FIRMWARE_DIR.is_dir():
        return None
    found = []
    for p in FIRMWARE_DIR.rglob("*"):
        if not p.is_file():
            continue
        depth = len(p.relative_to(FIRMWARE_DIR).parts) - 1
        if depth > 2:
            continue
        name = p.name.lower()
        if "scatter" in name and name.endswith(".txt"):
            found.append(p)
    found.sort()
    return found[0] if found else None


def _parse_scatter(text):
    """Scatter text se partition blocks ki fehrist: dicts ki list.

    Har block me partition_name / file_name / is_download keys hoti
    hain. Naya block 'partition_index:' wali line se ya, wo na ho to,
    naye 'partition_name:' se pehchana jata hai.
    """
    blocks = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        key, sep, val = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        val = val.strip()
        if key == "partition_index":
            if current:
                blocks.append(current)
            current = {}
        elif key == "partition_name":
            if current is not None and "partition_name" in current:
                blocks.append(current)
                current = {}
            if current is None:
                current = {}
            current["partition_name"] = val
        elif key in ("file_name", "is_download"):
            if current is None:
                current = {}
            current[key] = val
    if current:
        blocks.append(current)
    return blocks


def run(ctx) -> bool:
    if not _guard(ctx):
        return False
    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False

    scatter = _find_scatter()
    if scatter is None:
        ctx.log("Scatter file nahi mili (naam me 'scatter', .txt).", "ERROR")
        ctx.log("Guide: stock firmware ka poora folder (scatter + tamam "
                ".img/.bin files) tools/firmware/ me rakho — scatter file "
                "usi folder me honi chahiye jahan us ki tamam image files "
                "hain.", "WARN")
        return False
    ctx.log(f"Scatter file mili: {scatter}", "INFO")

    try:
        text = scatter.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Scatter file parhi nahi ja saki: {e}", "ERROR")
        return False

    blocks = _parse_scatter(text)
    queue = []
    for block in blocks:
        part = (block.get("partition_name") or "").strip()
        fname = (block.get("file_name") or "").strip()
        is_dl = (block.get("is_download") or "").strip().lower() == "true"
        if not part:
            continue
        if not is_dl:
            ctx.log(f"Skip: {part} — scatter me is_download false hai.", "WARN")
            continue
        if fname in ("", "NONE"):
            ctx.log(f"Skip: {part} — scatter me koi file nahi di gayi "
                    f"(file_name: {fname or 'khali'}).", "WARN")
            continue
        fpath = scatter.parent / fname
        if not fpath.is_file():
            ctx.log(f"Skip: {part} — file nahi mili: {fpath}", "WARN")
            continue
        queue.append((part, fpath))

    if not queue:
        ctx.log("Flash queue khali hai — aik bhi partition likhne ke "
                "qabil nahi mila. Scatter aur us ki files dobara check "
                "karo (upar skipped wali warnings dekho).", "ERROR")
        return False

    ctx.log(f"Flash queue tayyar: {len(queue)} partitions likhe jayenge.",
            "INFO")
    for part, fpath in queue:
        ctx.log(f"  • {part}  ←  {fpath.name}", "DATA")
    ctx.log("KHABARDAR: Ye asal flash hai — ghalat firmware phone ko "
            "brick kar sakta hai. Pehle Backup op se backup lo, aur "
            "tasdeeq karo ke ye firmware bilkul isi model ke liye hai. "
            "Flash ke doran cable bilkul mat hatana.", "WARN")

    extra = engines.mtk_extra_args()
    if extra:
        ctx.log("User ka DA (loader) istemal hoga jo tools/loaders/mtk/ "
                "me rakha hai.", "INFO")

    total = len(queue)
    for idx, (part, fpath) in enumerate(queue, start=1):
        if ctx.is_cancelled():
            return False
        if part.lower() == "preloader":
            ctx.log("KHAS KHABARDAR: Preloader likha ja raha hai — ghalat "
                    "preloader phone ko bilkul band (hard brick) kar sakta "
                    "hai. Sirf tab aage barho jab firmware pakka isi model "
                    "ka ho.", "WARN")
        pct = 5 + int(90 * (idx - 1) / total)
        ctx.progress(pct, f"Flash ho raha hai: {part} ({idx}/{total})")
        ctx.log(f"Flash {idx}/{total}: {part} likha ja raha hai...", "INFO")
        code = ctx.stream(cmd + ["w", part, str(fpath)] + extra,
                          timeout=900, cwd=cwd)
        if ctx.is_cancelled():
            return False
        if code != 0:
            ctx.log(f"Flash FAIL: {part} nahi likha gaya (exit code "
                    f"{code}) — operation yahin ruk gaya hai. Phone adhoori "
                    "halat me hai; dobara flash ya backup restore se pehle "
                    "use on karne ki koshish mat karo.", "ERROR")
            return False
        ctx.log(f"{part} likha gaya ({idx}/{total}).", "OK")

    ctx.progress(95, "Flash mukammal")
    ctx.log("Tamam partitions kamyabi se likhe gaye — phone ab reset / "
            "on karke check karo, pehli boot lambi ho sakti hai.", "OK")
    return True
