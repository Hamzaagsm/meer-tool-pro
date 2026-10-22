"""
mdm_library.py — Transsion MDM pack: MDM backup library ki fehrist.

tools/mdm-backups/ ke andar har model ke subfolder me jo backups
pare hain, un ki list size aur tareekh ke saath dikhata hai. Ye
sirf local file listing hai — koi subprocess, koi engine nahi.
Library waqt ke saath tumhare apne backups se bharti hai; tool
kisi model ka patch pehle se andar nahi rakhta.
"""

from datetime import datetime

from core.runner import TOOLS_DIR

OP = {
    "id": "mdm_library",
    "category": "MDM / Transsion",
    "name": "MDM Backup Library (List)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}

_SKIP_NAMES = {"README.md", ".gitkeep"}


def _human_size(n) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def run(ctx) -> bool:
    base = TOOLS_DIR / "mdm-backups"
    if not base.is_dir():
        ctx.log("Library abhi khali hai — tools/mdm-backups/ folder "
                "hi maujood nahi.", "INFO")
        ctx.log("Guide: 'Proinfo Backup' op se har model ka pehla "
                "backup lo; yahi library waqt ke saath tumhari asal "
                "MDM files banegi.", "INFO")
        return False

    model_dirs = sorted(p for p in base.iterdir() if p.is_dir())
    # Subfolders ke andar ki asal files (README/.gitkeep shumar nahi)
    grouped = []
    total_files = 0
    total_size = 0
    for folder in model_dirs:
        files = sorted(
            p for p in folder.rglob("*")
            if p.is_file() and p.name not in _SKIP_NAMES)
        if files:
            grouped.append((folder, files))
            total_files += len(files)
            total_size += sum(p.stat().st_size for p in files)

    if total_files == 0:
        ctx.log("Library abhi khali hai — koi backup file nahi mili.", "INFO")
        ctx.log("Guide: 'Proinfo Backup' op se har model ka pehla "
                "backup lo; yahi library waqt ke saath tumhari asal "
                "MDM files banegi.", "INFO")
        return False

    ctx.progress(30, "Library parhi ja rahi hai...")
    for folder, files in grouped:
        ctx.log(folder.name, "DATA")
        for f in files:
            try:
                size = f.stat().st_size
                when = datetime.fromtimestamp(
                    f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size, when = 0, "-"
            ctx.log(f"  {f.name} — {_human_size(size)} — {when}", "DATA")

    ctx.progress(90, "Fehrist mukammal")
    ctx.log(f"Library: {len(grouped)} model(s), {total_files} file(s), "
            f"kul size {_human_size(total_size)}.", "INFO")
    return True
