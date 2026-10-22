"""
runner.py — Operation runner.

Har operation aik plugin hai (src/ops/*.py) jo `OP` dict aur `run(ctx)`
function deta hai. Runner:
  - operation ko alag thread me chalata hai (GUI freeze nahi hoti)
  - engine subprocess ki output LINE-BY-LINE log console me stream karta hai
  - progress callback deta hai (0-100)
  - STOP asal me subprocess ko terminate karta hai
  - timeout par saaf error; natija hamesha asal SUCCESS / FAIL

Log levels: INFO (safed) · OK (hara) · WARN (peela) · ERROR (laal) ·
CMD (neela — chalne wali command) · DATA (halka — engine ki raw output)
"""

from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller onefile EXE: __file__ temp folder me hota hai — asal
    # jagah EXE ke saath wala folder hai (tools/ wahin rehta hai).
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parents[2]   # hamza-tool-pro/
TOOLS_DIR = APP_ROOT / "tools"
ENGINES_DIR = APP_ROOT / "engines"
BACKUPS_DIR = APP_ROOT / "backups"

LEVELS = ("INFO", "OK", "WARN", "ERROR", "CMD", "DATA")


@dataclass
class OpContext:
    """Har operation ko milne wali sahulaten — log, progress, device, helpers."""
    device: object = None                       # DeviceInfo | None
    _log_fn: object = None                      # callable(msg, level)
    _progress_fn: object = None                 # callable(percent, label)
    cancelled: threading.Event = field(default_factory=threading.Event)
    _proc: object = None                        # chalta hua subprocess (STOP ke liye)
    update_device: object = None                # callable(DeviceInfo) — panel refresh

    # -- operation apni taraf se ye istemal karega -------------------------
    def log(self, msg, level="INFO"):
        if self._log_fn:
            self._log_fn(str(msg), level)

    def progress(self, percent, label=""):
        if self._progress_fn:
            self._progress_fn(max(0, min(100, int(percent))), label)

    def is_cancelled(self):
        return self.cancelled.is_set()

    def stream(self, cmd, timeout=600, cwd=None):
        """Subprocess chalao aur output line-by-line log me bhejo.

        Return: process ka exit code (int). Cancel/timeout par -1 / -2 aur
        log me wajah pehle hi likh di jati hai.
        """
        self.log(" ".join(str(c) for c in cmd), "CMD")
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(
                [str(c) for c in cmd],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=str(cwd) if cwd else None, **kwargs,
            )
        except FileNotFoundError:
            self.log(f"Engine nahi mila: {cmd[0]}", "ERROR")
            self.log("Guide: ye engine app ke tools/ folder me ya PATH me "
                     "hona chahiye. Engine setup ke baghair operation nahi "
                     "chal sakta.", "WARN")
            return -1
        except Exception as e:  # noqa: BLE001
            self.log(f"Process shuru nahi ho saka: {e}", "ERROR")
            return -1
        self._proc = proc

        def _watchdog():
            if timeout:
                proc.wait()
            # cancel polling neeche read loop me hoti hai

        try:
            timer = None
            if timeout:
                timer = threading.Timer(timeout, proc.kill)
                timer.daemon = True
                timer.start()
            assert proc.stdout is not None
            for line in proc.stdout:
                if self.is_cancelled():
                    proc.terminate()
                    self.log("User ne operation rok diya (STOP).", "WARN")
                    break
                line = line.rstrip("\n")
                if line.strip():
                    self.log(line, "DATA")
            proc.wait()
            if timer:
                timer.cancel()
            if proc.returncode and proc.returncode < 0 and timeout:
                pass  # killed — cancel/timeout dono oper handle ho chuke
            return proc.returncode if proc.returncode is not None else -1
        finally:
            self._proc = None


@dataclass
class OpResult:
    ok: bool
    op_id: str
    message: str = ""


class Runner:
    """GUI se istemal: runner.start(op_module, device) — callback based."""

    def __init__(self, log_fn, progress_fn, done_fn, update_device_fn=None):
        self._log = log_fn
        self._progress = progress_fn
        self._done = done_fn
        self._update_device = update_device_fn
        self._thread = None
        self._ctx = None

    @property
    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, op_module, device):
        if self.busy:
            self._log("Aik operation pehle se chal raha hai — pehle usay "
                      "khatam ya STOP karo.", "WARN")
            return False
        self._ctx = OpContext(
            device=device,
            _log_fn=self._log,
            _progress_fn=self._progress,
            update_device=self._update_device,
        )
        self._thread = threading.Thread(
            target=self._work, args=(op_module,), daemon=True,
            name=f"op-{getattr(op_module, 'OP', {}).get('id', 'op')}",
        )
        self._thread.start()
        return True

    def stop(self):
        if self._ctx:
            self._ctx.cancelled.set()
            proc = self._ctx._proc
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    def _work(self, op_module):
        op = getattr(op_module, "OP", {})
        op_id = op.get("id", "unknown")
        name = op.get("name", op_id)
        ctx = self._ctx
        self._log(f"▶ Operation started: {name}", "INFO")
        ctx.progress(0, name)
        ok = False
        msg = ""
        try:
            ok = bool(op_module.run(ctx))
        except Exception as e:  # noqa: BLE001 — crash kabhi GUI tak nahi
            ctx.log(f"Operation ke doran ghalti: {e}", "ERROR")
            ok = False
            msg = str(e)
        if ctx.is_cancelled():
            self._log(f"⛔ Operation roka gaya: {name}", "WARN")
            ok = False
        elif ok:
            ctx.progress(100, "Done")
            self._log(f"✔ SUCCESS — {name} mukammal hua.", "OK")
        else:
            self._log(f"✖ FAIL — {name} mukammal nahi hua. "
                      "Upar ke log me wajah dekho.", "ERROR")
        if self._done:
            self._done(OpResult(ok=ok, op_id=op_id, message=msg))
