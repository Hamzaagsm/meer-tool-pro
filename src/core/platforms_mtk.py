"""
platforms_mtk.py — Platforms module, MediaTek workbench ke actions.

Fenix ke Platforms → MediaTek screen jaisa workbench: GPT se bhari
hui partition table + Identify / Backup / Erase / Flash / Reboot.
Tamam actions **wohi engines** istemal karte hain jo ops tree ke MTK
ops karte hain (core/engines.py resolver + ctx.stream) — engine logic
ki koi doosri copy NAHI hai; yahan sirf table ke hisaab se batching
aur GPT parsing hai jo tree-ops ko nahi chahiye thi.

printgpt ka format MTKClient ke source se verify kiya gaya hai
(Library/Partitions/__init__.py -> tostring()):
    boot:   Offset 0x0000000000008000, Length 0x0000000002000000, ...
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core import engines
from core.runner import BACKUPS_DIR, TOOLS_DIR

_GPT_LINE = re.compile(
    r"^\s*(?P<name>[^:\s][^:]*):\s+Offset 0x(?P<off>[0-9a-fA-F]+),"
    r"\s*Length 0x(?P<len>[0-9a-fA-F]+)")


def parse_gpt(text):
    """printgpt ki output se partition list: name/start/size (bytes)."""
    parts = []
    for line in (text or "").splitlines():
        m = _GPT_LINE.match(line)
        if not m:
            continue
        start = int(m.group("off"), 16)
        size = int(m.group("len"), 16)
        parts.append({
            "name": m.group("name").strip(),
            "start": start,
            "size": size,
            "region": "—",
            "block": size // 512 if size else 0,
        })
    return parts


def _op(op_id, name, run):
    return SimpleNamespace(OP={
        "id": op_id, "category": "MTK", "name": name,
        "engine": "mtkclient", "modes": ("BROM", "PRELOADER"),
        "server_required": False,
    }, run=run)


def _engine_or_fail(ctx):
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
        else:
            ctx.log(note, "ERROR")
            ctx.log("Guide: MTKClient app ke engines/mtkclient/ folder "
                    "me hona chahiye.", "WARN")
        return None, None
    return cmd, cwd


def _guard(ctx):
    dev = ctx.device
    if not dev or dev.mode not in ("BROM", "PRELOADER"):
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band "
                "karke Volume dono dabaye hue cable lagao.", "ERROR")
        return False
    return True


def _extra(da):
    if da:
        return ["--loader", str(da)]
    return engines.mtk_extra_args()


def _maybe_crash(ctx, cmd, cwd, extra, opts):
    if opts.get("crash_first"):
        ctx.log("Crash PL To Brom: preloader ko BROM me crash kiya ja "
                "raha hai...", "INFO")
        code = ctx.stream(cmd + ["crash"] + extra, timeout=120, cwd=cwd)
        if code != 0:
            ctx.log("Crash nahi hua — kuch preloader crash hote hi "
                    "nahi; maujooda mode se aage barh rahe hain.",
                    "WARN")


def _maybe_reboot(ctx, cmd, cwd, extra, opts):
    if opts.get("auto_reboot"):
        ctx.log("Auto-Reboot: reset bheja ja raha hai...", "INFO")
        ctx.stream(cmd + ["reset"] + extra, timeout=120, cwd=cwd)


def _auth_note(ctx, opts):
    if opts.get("auth"):
        ctx.log(f"{opts['auth']} Auth muntakhib hai — ye route SERVER "
                "REQUIRED hai: brand ke authorized server ke baghair "
                "auth nahi milta. Free engine wala amal is ke baghair "
                "chalaya ja raha hai; auth lazmi ho to amal yahin ruk "
                "jayega aur wajah log me ayegi.", "WARN")


def identify_op(on_gpt, opts):
    """Identify: (ikhtiyari gettargetconfig + crash) + printgpt parh
    kar table ke liye parsed partitions on_gpt callback ko deta hai."""
    def run(ctx):
        if not _guard(ctx):
            return False
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        extra = _extra(opts.get("da"))
        _auth_note(ctx, opts)
        _maybe_crash(ctx, cmd, cwd, extra, opts)
        if opts.get("android_info"):
            ctx.log("Android Info: target config parha ja raha hai "
                    "(sbc/daa/auth halat)...", "INFO")
            ctx.stream(cmd + ["gettargetconfig"] + extra,
                       timeout=120, cwd=cwd)
        ctx.progress(30, "GPT parha ja raha hai...")
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NO_WINDOW", 0)
        try:
            out = subprocess.run(
                cmd + ["printgpt"] + extra, capture_output=True,
                text=True, timeout=300,
                cwd=cwd if cwd else None, **kwargs)
            text = (out.stdout or "") + "\n" + (out.stderr or "")
            rc = out.returncode
        except Exception as e:  # noqa: BLE001
            ctx.log(f"printgpt chal nahi saka: {e}", "ERROR")
            return False
        for line in text.splitlines():
            if line.strip():
                ctx.log(line, "DATA")
        parts = parse_gpt(text)
        if rc != 0 or not parts:
            ctx.log("GPT parha nahi ja saka — device BROM/Preloader "
                    "me hai ya nahi, DA durust hai ya nahi, check "
                    "karo.", "ERROR")
            return False
        ctx.log(f"{len(parts)} partitions mile — table bhar di gayi "
                "hai.", "OK")
        ctx.progress(95, "GPT tayyar")
        if on_gpt:
            on_gpt(parts)
        return True
    return _op("platforms_mtk_identify", "Identify (Platforms MTK)", run)


def backup_op(names, opts):
    def run(ctx):
        if not names:
            ctx.log("Koi partition select nahi — pehle table me "
                    "partitions tick karo.", "ERROR")
            return False
        if not _guard(ctx):
            return False
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        extra = _extra(opts.get("da"))
        _maybe_crash(ctx, cmd, cwd, extra, opts)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        outdir = BACKUPS_DIR / f"platforms-mtk-{ts}"
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Backup folder nahi ban saka: {e}", "ERROR")
            return False
        files = [str(outdir / f"{n}.bin") for n in names]
        ctx.progress(15, f"{len(names)} partitions ka backup...")
        code = ctx.stream(cmd + ["r", ",".join(names), ",".join(files)]
                          + extra, timeout=3600, cwd=cwd)
        if code != 0:
            ctx.log(f"Backup fail hua (exit code {code}).", "ERROR")
            return False
        done = [f for f in files if Path(f).is_file()
                and Path(f).stat().st_size > 0]
        if not done:
            ctx.log("Koi file nahi bani — backup nakam.", "ERROR")
            return False
        ctx.log(f"Backup tayyar: {outdir} ({len(done)} files)", "OK")
        _maybe_reboot(ctx, cmd, cwd, extra, opts)
        return True
    return _op("platforms_mtk_backup", "Backup (Platforms MTK)", run)


def erase_op(names, opts):
    def run(ctx):
        if not names:
            ctx.log("Koi partition select nahi — pehle table me "
                    "partitions tick karo.", "ERROR")
            return False
        if not _guard(ctx):
            return False
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        extra = _extra(opts.get("da"))
        _maybe_crash(ctx, cmd, cwd, extra, opts)
        failed = []
        for i, name in enumerate(names):
            if ctx.is_cancelled():
                return False
            ctx.progress(10 + int(80 * i / max(1, len(names))),
                         f"{name} erase ho raha hai...")
            code = ctx.stream(cmd + ["e", name] + extra,
                              timeout=300, cwd=cwd)
            if code != 0:
                failed.append(name)
                ctx.log(f"{name} erase FAIL (exit code {code}).",
                        "ERROR")
            else:
                ctx.log(f"{name} erase ho gaya.", "OK")
        if failed:
            ctx.log(f"Ye partitions erase nahi hue: "
                    f"{', '.join(failed)}", "ERROR")
            return False
        _maybe_reboot(ctx, cmd, cwd, extra, opts)
        return True
    return _op("platforms_mtk_erase", "Erase (Platforms MTK)", run)


def flash_op(pairs, opts):
    """pairs: [(partition, filepath)] — sirf jin ke paas file hai."""
    def run(ctx):
        if not pairs:
            ctx.log("Flash ke liye koi partition+file nahi — pehle "
                    "partitions tick karo aur har aik par double-click "
                    "karke file select karo (ya As Scatter istemal "
                    "karo).", "ERROR")
            return False
        if not _guard(ctx):
            return False
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        extra = _extra(opts.get("da"))
        _auth_note(ctx, opts)
        ctx.log("Ye ASAL flash hai — ghalat file phone ko brick kar "
                "sakti hai.", "WARN")
        _maybe_crash(ctx, cmd, cwd, extra, opts)
        for i, (name, path) in enumerate(pairs):
            if ctx.is_cancelled():
                return False
            ctx.progress(10 + int(80 * i / max(1, len(pairs))),
                         f"{name} flash ho raha hai...")
            code = ctx.stream(cmd + ["w", name, str(path)] + extra,
                              timeout=900, cwd=cwd)
            if code != 0:
                ctx.log(f"{name} flash FAIL (exit code {code}) — "
                        "yahan ruk rahe hain.", "ERROR")
                return False
            ctx.log(f"{name} flash ho gaya.", "OK")
        _maybe_reboot(ctx, cmd, cwd, extra, opts)
        return True
    return _op("platforms_mtk_flash", "Flash (Platforms MTK)", run)


def parse_scatter(scatter_path):
    """Scatter text se {partition_name: file_path} — mtk_flash wali
    hi sakht (is_download + file exists wali entries)."""
    path = Path(scatter_path)
    result = {}
    if not path.is_file():
        return result
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return result
    current = {}

    def flush(entry):
        name = entry.get("partition_name", "").strip()
        fname = entry.get("file_name", "").strip()
        dl = entry.get("is_download", "").strip().lower()
        if name and fname and fname.upper() != "NONE" \
                and dl in ("true", "yes", "1"):
            f = path.parent / fname
            if f.is_file():
                result[name] = f

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("partition_name:"):
            if current:
                flush(current)
            current = {"partition_name": line.split(":", 1)[1].strip()}
        elif ":" in line and current is not None:
            key, _, val = line.partition(":")
            current[key.strip()] = val.strip()
    if current:
        flush(current)
    return result


def flash_scatter_op(scatter_path, selected, opts):
    def run(ctx):
        mapping = parse_scatter(scatter_path)
        if not mapping:
            ctx.log("Scatter se koi flashable partition nahi mila — "
                    "file aur us ke saath wali images check karo.",
                    "ERROR")
            return False
        pairs = [(n, mapping[n]) for n in selected if n in mapping]
        skipped = [n for n in selected if n not in mapping]
        for n in skipped:
            ctx.log(f"Skip: {n} — scatter me is ki file nahi hai.",
                    "WARN")
        if not pairs:
            ctx.log("Selected partitions me se koi scatter me nahi "
                    "mila.", "ERROR")
            return False
        return flash_op(pairs, opts).run(ctx)
    return _op("platforms_mtk_flash_scatter",
               "Flash Scatter (Platforms MTK)", run)


def reboot_op(opts):
    def run(ctx):
        if not _guard(ctx):
            return False
        cmd, cwd = _engine_or_fail(ctx)
        if cmd is None:
            return False
        code = ctx.stream(cmd + ["reset"] + _extra(opts.get("da")),
                          timeout=120, cwd=cwd)
        return code == 0
    return _op("platforms_mtk_reboot", "Reboot (Platforms MTK)", run)


def file_manager_guide_op():
    def run(ctx):
        ctx.log("MTK File Manager: MTKClient ke paas 'fs' (FUSE mount) "
                "command hai, lekin wo Linux/macOS par chalta hai — "
                "Windows par is ka koi seedha rasta is build me NAHI "
                "hai.", "WARN")
        ctx.log("Filhal phone ki files ke liye Utility module ka "
                "File Manager (ADB browse/pull/push) istemal karo — "
                "wo asal me chalta hai.", "INFO")
        return False
    return _op("platforms_mtk_file_manager",
               "File Manager Guide (Platforms MTK)", run)
