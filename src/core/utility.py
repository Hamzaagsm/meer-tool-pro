"""
utility.py — Utility module ke File Manager actions (ADB browse /
pull / push).

Fenix ke Utility module me File Manager hota hai. Hamara version ADB
par asal me chalta hai: `adb shell ls` se directory ki fehrist
(capture karke GUI ki table ko callback se), `adb pull` se file PC
par, `adb push` se file phone par. Koi nakli browsing nahi — jo
device deta hai wahi nazar ata hai.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from core import engines
from core.runner import APP_ROOT

DOWNLOADS_DIR = APP_ROOT / "downloads"


def _op(op_id, name, run):
    return SimpleNamespace(OP={
        "id": op_id, "category": "ADB / Fastboot", "name": name,
        "engine": "adb", "modes": ("ADB",), "server_required": False,
    }, run=run)


def _guard(ctx):
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai — phone on karke USB "
                "debugging ON karo.", "ERROR")
        return False
    return True


def _capture(adb, serial, args, timeout=30):
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([adb, "-s", serial] + args,
                             capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        return out.stdout or "", out.returncode
    except Exception:
        return "", -1


def parse_ls(text):
    """`ls -la` ki output se entries: (name, is_dir, size_str)."""
    entries = []
    for line in (text or "").splitlines():
        line = line.rstrip()
        if not line or line.startswith("total "):
            continue
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        perms, _links, _owner, _group, size, date, time_, name = parts
        if name in (".", ".."):
            continue
        entries.append({
            "name": name,
            "is_dir": perms.startswith("d"),
            "is_link": perms.startswith("l"),
            "size": size,
            "when": f"{date} {time_}",
        })
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries


def list_op(path, on_entries):
    """Directory ki fehrist — entries on_entries callback ko (GUI
    thread-safe queue ke zariye table bharne ke liye)."""
    def run(ctx):
        if not _guard(ctx):
            return False
        adb = engines.find_platform_tool("adb")
        ctx.progress(30, f"{path} ki fehrist aa rahi hai...")
        text, rc = _capture(adb, ctx.device.serial,
                            ["shell", "ls", "-la", path])
        if rc != 0 or not text.strip():
            ctx.log(f"Directory parhi nahi ja saki: {path} — rasta "
                    "durust hai ya nahi, aur phone par permission hai "
                    "ya nahi, check karo.", "ERROR")
            return False
        entries = parse_ls(text)
        for e in entries:
            kind = "DIR " if e["is_dir"] else "FILE"
            ctx.log(f"{kind} {e['name']}  ({e['size']})", "DATA")
        ctx.log(f"{path}: {len(entries)} items.", "OK")
        if on_entries:
            on_entries(path, entries)
        ctx.progress(95, "Fehrist tayyar")
        return True
    return _op("utility_fm_list", "File Manager List (Utility)", run)


def pull_op(remote_path, dest_dir=None):
    def run(ctx):
        if not _guard(ctx):
            return False
        adb = engines.find_platform_tool("adb")
        dest = Path(dest_dir) if dest_dir else DOWNLOADS_DIR
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Downloads folder nahi ban saka: {e}", "ERROR")
            return False
        ctx.progress(30, f"Pull ho raha hai: {remote_path}")
        code = ctx.stream([adb, "-s", ctx.device.serial, "pull",
                           remote_path, str(dest)], timeout=900)
        if code == 0:
            ctx.log(f"File mehfooz: {dest} ke andar (phone wale naam "
                    "se).", "OK")
            return True
        ctx.log(f"Pull fail hua (exit code {code}).", "ERROR")
        return False
    return _op("utility_fm_pull", "File Manager Pull (Utility)", run)


def push_op(local_path, remote_dir):
    def run(ctx):
        if not _guard(ctx):
            return False
        if not local_path or not Path(local_path).is_file():
            ctx.log("Local file nahi mili — pehle file select karo.",
                    "ERROR")
            return False
        adb = engines.find_platform_tool("adb")
        remote = (remote_dir or "/sdcard/").rstrip("/") + "/" \
            + Path(local_path).name
        ctx.progress(30, f"Push ho raha hai: {remote}")
        code = ctx.stream([adb, "-s", ctx.device.serial, "push",
                           str(local_path), remote], timeout=900)
        if code == 0:
            ctx.log(f"File phone par bheji gayi: {remote}", "OK")
            return True
        ctx.log(f"Push fail hua (exit code {code}).", "ERROR")
        return False
    return _op("utility_fm_push", "File Manager Push (Utility)", run)
