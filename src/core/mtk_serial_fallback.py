"""
mtk_serial_fallback.py — MTK reset/FRP ops ke liye VCOM (serial) fallback.

Wajah (2026-10-24, Vivo Y91i, PD1818HF, MT6765): phone ka preloader
VCOM serial driver se bandha ho to MTKClient ka libusb rasta usay
claim nahi kar pata — log me "USB enumeration error" + port 2 second
me gayab, aur op "Waiting for Preloader VCOM" par atak jata hai.
DFT Pro isi phone par is liye kamyab hua ke wo COM port se baat
karta hai (Preloader + DA, 33 second me Wipe USERDATA + FRP Done).
Ye module wahi rasta MEER ke MTK reset/FRP ops me automatic
fallback ke tor par jorta hai: primary (USB) nakam ho to VCOM COM
port se dobara koshish hoti hai.

Usool (kabhi nahi toota):
- Koi kamyabi farzi nahi: har koshish ka exit code faisla karta hai.
  Dono raste nakam hon to FAIL + dono ki aakhri lines log me.
- Koi hang nahi: COM port ka wait bounded hai (entry 60 s,
  fallback 30 s); COM port bilkul na mile to fallback foran FAIL.
- Entry: button-held BROM lazmi NAHI — band phone sirf cable se
  bhi preloader port pakra jata hai (DFT ka aam tareeqa). Is liye
  op start par device na ho to wait-mode me COM port ka wait hota
  hai; sirf tab FAIL jab waqt par koi preloader COM port na mile.
- Is module ko MTK ke tamam transport ops istemal karte hain
  (reset/FRP, info, backup, flash, bootloader, NV, RPMB, bypass
  chain, platforms workbench) — IMEI ops ki logic ko haath nahi.
- Button vs cable-only farq software se nahi pehchana ja sakta; log
  me wohi likha jata hai jo dekha gaya: "device op start par
  mojood tha" ya "cable insert par preloader COM port mila".
- Serial-first (2026-10-25, Infinix Smart 20 X6840 bench): Hamza
  ne sabit kiya ke driver THEEK hain — DFT/Fenix usi PC par usi
  driver se COM port (VCOM serial) se kaam karte hain. Transport
  pehle USB/libusb try karta tha jo VCOM-bound port claim hi nahi
  kar pata ("USB enumeration error"), aur serial fallback tab
  chalta tha jab 180s timeout zaya ho chuka hota aur phone
  preloader se nikal chuka hota. Is liye: COM port pehle se nazar
  aa raha ho to transport SERIAL se shuru hota hai (USB fallback
  rehta hai); COM port na ho to pehle wala USB-pehle tartib rehta
  hai. Aur USB koshish par transport-failure wali line milte hi
  line-hook usay foran khatam kar deta hai (StreamAbort, exit -3)
  — timeout ka intezaar nahi.
"""

from __future__ import annotations

import sys
import time

from core.runner import StreamAbort

# ---------------------------------------------------------------------------
# MediaTek USB IDs (vendored MTKClient ke default_ids se liye hue, plus
# device_watch / driver pack wale preloader PIDs jo default_ids me nahi:
# 0x2006 (Preloader DA) aur 0x2007 — in ke liye --vid/--pid bhi dena
# parta hai, warna MTKClient ka serial detect unhe nahi dekhta.)
# ---------------------------------------------------------------------------
MTK_VID = 0x0E8D

MTK_SERIAL_PIDS = frozenset({
    0x0003,  # BROM
    0x2000, 0x2001,  # Preloader
    0x2006,  # Preloader (DA)
    0x2007,  # Preloader variant
    0x201D, 0x20FF, 0x3000, 0x6000,  # Preloader variants
})

# MTKClient ke default_ids me mojood PIDs — in ke liye plain
# `--serialport COMx` kaafi hai.
MTK_DEFAULT_PIDS = frozenset({
    0x0003, 0x6000, 0x2000, 0x2001, 0x201D, 0x20FF, 0x3000,
})

# ---------------------------------------------------------------------------
# Fallback triggers — SIRF nakam koshish (exit != 0) ki output par
# parakhe jate hain. Janboojh kar tang rakhe hue hain: aam "not
# found" is me NAHI hai, warna partition-missing jaisi asal
# ghaltiyan (metadata/persist ka WARN) bhi fallback chala detin.
# ---------------------------------------------------------------------------
FALLBACK_TRIGGERS = (
    "usb enumeration error",          # vendored Port.py ka lafz
    "waiting for preloader",          # MTKClient preloader wait
    "waiting for device",             # MTKClient device wait (nakami par)
    "no device found",
    "device not found",
    "no device detected",
    "could not find device",
    "failed to connect",
    "could not open",
    "cannot open",
    "operation not supported",        # libusb error (Hamza ka log)
    "unimplemented on this platform",  # libusb error (Hamza ka log)
    "please reconnect",               # MTKClient preloader message
    "libusb",                         # koi bhi libusb error line
)

PORT_MISMATCH_MARKERS = (
    "not in detected ports",  # serial port MTKClient ki list me nahi
)

ENTRY_WAIT_S = 60.0   # op start par preloader COM port ka wait
FALLBACK_WAIT_S = 30.0  # fallback se pehle dobara lagane ka wait


# ---------------------------------------------------------------------------
# COM port detection — pyserial pehle, Windows registry backup.
# Kabhi raise nahi karta; na mile to [].
# ---------------------------------------------------------------------------
def _scan_pyserial():
    """pyserial se MediaTek VCOM ports: [(port, pid), ...]."""
    try:
        from serial.tools import list_ports
    except Exception:
        return None  # pyserial nahi — caller registry fallback karega
    found = []
    try:
        ports = list_ports.comports()
    except Exception:
        return []
    for p in ports:
        try:
            if p.vid == MTK_VID and p.pid in MTK_SERIAL_PIDS:
                found.append((p.device, p.pid))
        except Exception:
            continue
    return sorted(found)


def _scan_winreg():
    """Windows registry se MediaTek USB devices ke COM ports.

    HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB\\VID_0E8D&PID_XXXX... keys
    me FriendlyName + Device Parameters\\PortName hota hai. Sirf
    Windows par chalta hai; baqi par [].
    """
    if not sys.platform.startswith("win"):
        return []
    try:
        import winreg
    except Exception:
        return []
    found = []
    try:
        enum = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Enum\USB")
    except Exception:
        return []
    try:
        i = 0
        while True:
            try:
                vidkey = winreg.EnumKey(enum, i)
            except OSError:
                break
            i += 1
            if not vidkey.upper().startswith("VID_0E8D"):
                continue
            # PID key ke naam se nikalo: VID_0E8D&PID_2000&...
            pid = None
            for part in vidkey.split("&"):
                if part.upper().startswith("PID_"):
                    try:
                        pid = int(part[4:], 16)
                    except Exception:
                        pid = None
            if pid is None or pid not in MTK_SERIAL_PIDS:
                continue
            try:
                sub = winreg.OpenKey(enum, vidkey)
            except Exception:
                continue
            try:
                j = 0
                while True:
                    try:
                        inst = winreg.EnumKey(sub, j)
                    except OSError:
                        break
                    j += 1
                    try:
                        params = winreg.OpenKey(sub, inst + r"\Device Parameters")
                        port, _t = winreg.QueryValueEx(params, "PortName")
                        winreg.CloseKey(params)
                    except Exception:
                        continue
                    if port:
                        found.append((str(port), pid))
            finally:
                winreg.CloseKey(sub)
    finally:
        winreg.CloseKey(enum)
    return sorted(set(found))


def detect_mtk_vcom_ports(scanner=None):
    """MediaTek BROM/Preloader VCOM ports: [(port, pid), ...] (sorted).

    scanner: test ke liye injectable callable () -> [(port, pid)].
    """
    if scanner is not None:
        try:
            return sorted(scanner())
        except Exception:
            return []
    ports = _scan_pyserial()
    if ports is not None:
        return ports
    return _scan_winreg()


def wait_for_mtk_vcom_port(timeout_s=FALLBACK_WAIT_S, poll_s=1.0,
                           is_cancelled=None, scanner=None):
    """COM port nazar aane tak bounded wait; mile to list, warna [].

    is_cancelled: callable () -> bool (STOP dabane par foran ruko).
    """
    deadline = time.monotonic() + max(0.0, timeout_s)
    while True:
        ports = detect_mtk_vcom_ports(scanner=scanner)
        if ports:
            return ports
        if is_cancelled is not None:
            try:
                if is_cancelled():
                    return []
            except Exception:
                pass
        if time.monotonic() >= deadline:
            return []
        time.sleep(min(poll_s, max(0.0, deadline - time.monotonic())))


def build_serial_prefix(port, pid):
    """MTKClient global args (subcommand se PEHLE lagane ke liye).

    Aam PIDs ke liye plain `--serialport COMx`. default_ids se bahir
    wale PIDs (0x2006/0x2007) ke liye --vid/--pid bhi dena lazmi hai,
    warna MTKClient ka serial detect us port ko nahi dekhta.
    getint() decimal phir hex parse karta hai, is liye 0x- wali
    shakal di gayi hai (warna "2006" decimal samjha jayega).
    """
    if pid in MTK_DEFAULT_PIDS:
        return ["--serialport", port]
    return ["--vid", "0x0e8d", "--pid", "0x%04x" % pid,
            "--serialport", port]


def looks_like_transport_failure(lines, code):
    """Nakam koshish ki output transport ki wajah se lagi ya nahi.

    lines: output lines (list[str]); code: exit code (None ho to sirf
    lines dekhi jati hain). Timeout par mara hua process (code < 0)
    bhi transport failure hai — cancel case caller pehle hi alag
    karta hai, is liye yahan code < 0 = timeout kill.
    """
    if code is not None and code < 0:
        return True
    blob = "\n".join(lines).lower()
    return any(t in blob for t in FALLBACK_TRIGGERS)


def last_lines(lines, n=3):
    """Aakhri ghair-khali lines (FAIL summary ke liye)."""
    tail = [ln for ln in lines if ln.strip()][-n:]
    return " | ".join(tail) if tail else "(koi output nahi)"


# ---------------------------------------------------------------------------
# Entry: op start par device na ho to wait-mode (cable-only entry).
# ---------------------------------------------------------------------------
def ensure_mtk_entry(ctx, modes=("BROM", "PRELOADER"),
                     wait_s=ENTRY_WAIT_S, scanner=None):
    """(ok, entry_note) — entry tasdeeq ya wait ke baad nakami.

    Fast path: ctx.device pehle se BROM/PRELOADER me ho to foran True.
    Warna COM port ka wait (cable-only entry): port mil jaye to True.
    Na mile to False — caller phir asal _guard chalata hai (us ki
    ERROR rehnumai + False barkarar rehti hai).
    """
    dev = getattr(ctx, "device", None)
    if dev is not None and getattr(dev, "mode", None) in modes:
        return True, "entry: device op start par BROM/Preloader me mojood tha"
    ports = detect_mtk_vcom_ports(scanner=scanner)
    if ports:
        return True, ("entry: preloader COM port pehle se mojood "
                      "(%s) — COM port se tasdeeq" % ports[0][0])
    try:
        ctx.log("Device abhi BROM/Preloader me nahi — wait mode: band "
                "phone cable se lagao (button zaroori nahi; preloader "
                "port khud pakra jayega). ROKNA ho to STOP dabao.",
                "WARN")
    except Exception:
        pass
    is_cancelled = getattr(ctx, "is_cancelled", None)
    ports = wait_for_mtk_vcom_port(timeout_s=wait_s,
                                   is_cancelled=is_cancelled,
                                   scanner=scanner)
    if ports:
        try:
            ctx.log("Preloader COM port mil gaya: %s — entry: cable "
                    "insert par pakra gaya" % ports[0][0], "OK")
        except Exception:
            pass
        return True, ("entry: cable insert par preloader COM port mila "
                      "(%s)" % ports[0][0])
    return False, ""


# ---------------------------------------------------------------------------
# Transport: har step par USB pehle, trigger par VCOM; kamyab rasta
# sticky (baqi steps usi se), lekin agla step phir trigger de to
# doosra rasta aik dafa azmaya jata hai (DA mode me USB dobara
# chal sakta hai). Har step par zyada se zyada 2 koshishen (+
# port-mismatch par aik DETECT koshish) — koi infinite loop nahi.
# ---------------------------------------------------------------------------
class MtkTransport:
    """MTKClient step runner: USB primary, VCOM fallback, sticky mode."""

    def __init__(self, ctx, cmd, cwd, extra, entry_note="",
                 scanner=None, fallback_wait_s=FALLBACK_WAIT_S):
        self.ctx = ctx
        self.cmd = list(cmd)
        self.cwd = cwd
        self.extra = list(extra) if extra else []
        self.entry_note = entry_note
        self.scanner = scanner
        self.fallback_wait_s = fallback_wait_s
        self.mode = "usb"          # "usb" ya "serial"
        self.serial_port = None    # "COMx" ya "DETECT"
        self.serial_pid = None
        # Serial-first (Smart 20 bench, 2026-10-25): COM port pehle
        # se nazar aa raha ho to USB/libusb ki koshish zaya mat
        # karo — VCOM-bound port libusb claim hi nahi kar pata.
        # Port na ho to USB-pehle (pehle wala bartao).
        try:
            _ports = detect_mtk_vcom_ports(scanner=scanner)
        except Exception:  # noqa: BLE001 — scan kabhi init nahi rokta
            _ports = []
        if _ports:
            self.mode = "serial"
            self.serial_port, self.serial_pid = _ports[0]
        self._logged_path = False

    # -- andarooni helpers -------------------------------------------------
    def _log(self, msg, level="INFO"):
        try:
            self.ctx.log(msg, level)
        except Exception:
            pass

    def _cancelled(self):
        fn = getattr(self.ctx, "is_cancelled", None)
        try:
            return bool(fn()) if fn else False
        except Exception:
            return False

    def _run(self, full_cmd, timeout, label, line_hook=None):
        lines = []

        def _hook(line):
            lines.append(line)
            if line_hook is not None:
                try:
                    line_hook(line)
                except Exception:  # noqa: BLE001 — caller hook kabhi stream nahi rokta
                    pass
            # Early abort (Smart 20 bench, 2026-10-25): transport-
            # failure wali line milte hi koshish foran khatam karo —
            # MTKClient ki apni retry loop me 180s zaya mat karo.
            # StreamAbort par runner stream -3 wapas karta hai;
            # FakeCtx jaisi ctx ise propagate kare to neeche pakar
            # kar wahi -3 banaya jata hai.
            if looks_like_transport_failure([line], None):
                raise StreamAbort(line)

        try:
            code = self.ctx.stream(full_cmd, timeout=timeout, cwd=self.cwd,
                                   line_hook=_hook)
        except StreamAbort:
            return -3, lines
        return code, lines

    def _serial_prefix(self, port, pid):
        if port == "DETECT":
            return ["--serialport", "DETECT"]
        return build_serial_prefix(port, pid)

    def _run_serial(self, args, timeout, label, line_hook=None):
        """Serial koshish (+ port-mismatch par aik DETECT koshish)."""
        port, pid = self.serial_port, self.serial_pid
        prefix = self._serial_prefix(port, pid)
        code, lines = self._run(self.cmd + prefix + args + self.extra,
                                timeout, label, line_hook=line_hook)
        if (code != 0 and not self._cancelled() and port != "DETECT"
                and any(m in "\n".join(lines).lower()
                        for m in PORT_MISMATCH_MARKERS)):
            self._log("Serial port %s MTKClient ki list me nahi — "
                      "DETECT se dobara koshish..." % port, "WARN")
            self.serial_port, self.serial_pid = "DETECT", None
            code, lines = self._run(
                self.cmd + ["--serialport", "DETECT"] + args + self.extra,
                timeout, label, line_hook=line_hook)
        return code, lines

    def _switch_to_serial(self, args, timeout, label, primary_code,
                          primary_lines, line_hook=None):
        """VCOM fallback: port dhoondo (bounded wait) phir serial chalao."""
        why = ("line-hook early-abort (transport error line mili, "
               "timeout ka intezaar nahi kiya)" if primary_code == -3
               else "exit %s" % primary_code)
        self._log("USB rasta nakam (%s) — VCOM (COM port) rasta "
                  "azmaya ja raha hai: %s"
                  % (why, last_lines(primary_lines)), "WARN")
        ports = detect_mtk_vcom_ports(scanner=self.scanner)
        if not ports and not self._cancelled():
            self._log("VCOM COM port abhi nahi mila — phone dobara "
                      "preloader mode me lagao (band + cable, button "
                      "zaroori nahi) — %.0f second wait ho raha hai..."
                      % FALLBACK_WAIT_S, "WARN")
            ports = wait_for_mtk_vcom_port(
                timeout_s=self.fallback_wait_s,
                is_cancelled=getattr(self.ctx, "is_cancelled", None),
                scanner=self.scanner)
        if self._cancelled():
            return primary_code, primary_lines
        if not ports:
            self._log("VCOM COM port nahi mila — fallback nahi ho saka. "
                      "USB aakhri line: %s"
                      % last_lines(primary_lines), "ERROR")
            return primary_code, primary_lines
        self.serial_port, self.serial_pid = ports[0]
        self._log("VCOM rasta: Preloader (VCOM %s) — COM port se "
                  "tasdeeq" % self.serial_port, "INFO")
        code, lines = self._run_serial(args, timeout, label,
                                       line_hook=line_hook)
        if code == 0:
            self.mode = "serial"
            self._log("VCOM rasta kamyab — baqi steps bhi isi raste "
                      "se honge.", "OK")
        else:
            self._log("VCOM rasta bhi nakam (exit %s): %s"
                      % (code, last_lines(lines)), "ERROR")
        return code, lines

    # -- bahar wala API ------------------------------------------------------
    def stream_step(self, args, timeout=180, label="", line_hook=None):
        """Aik MTKClient step: exit code. Cancel par foran wapas.

        line_hook: har output line par caller ka hook bhi chale
        (masalan mtk_info ki CPU parse) — runner ki live DATA
        logging waisi hi rehti hai.
        """
        code, _lines = self.stream_step_capture(
            args, timeout=timeout, label=label, line_hook=line_hook)
        return code

    def stream_step_capture(self, args, timeout=180, label="",
                            line_hook=None):
        """stream_step jaisa, lekin (exit code, output lines) dono de.

        Jin ops ko jawab ka MATAN chahiye hota hai (printgpt parse,
        gettargetconfig, GPT tasdeeq) wo yahi istemal karen — warna
        unhen VCOM fallback kabhi nahi milta tha (seedha subprocess
        ya ctx.stream wala rasta). Lines wahi hain jo runner ne
        live DATA ke tor par log me bhi likhi hain; dobara log
        karne ki zaroorat nahi.
        """
        if not self._logged_path:
            self._logged_path = True
            if self.mode == "serial":
                self._log("MTK rasta: VCOM (serial %s) — %s"
                          % (self.serial_port,
                             self.entry_note or "entry: guard se tasdeeq"),
                          "INFO")
            else:
                self._log("MTK rasta: BROM (USB) — %s"
                          % (self.entry_note or "entry: guard se tasdeeq"),
                          "INFO")
        order = [self.mode, "serial" if self.mode == "usb" else "usb"]
        last_code, last_lines_out = None, []
        for mode in order:
            if mode == "usb":
                code, lines = self._run(self.cmd + args + self.extra,
                                        timeout, label,
                                        line_hook=line_hook)
            else:
                # Serial seedha sirf tab jab pehle se port maloom ho
                # (sticky mode); warna _switch_to_serial wait karta hai.
                if self.serial_port is not None:
                    code, lines = self._run_serial(args, timeout, label,
                                                   line_hook=line_hook)
                else:
                    code, lines = self._switch_to_serial(
                        args, timeout, label, last_code, last_lines_out,
                        line_hook=line_hook)
            if self._cancelled():
                return code, lines
            if code == 0:
                self.mode = mode
                return 0, lines
            last_code, last_lines_out = code, lines
            # Genuine (ghair-transport) failure: dobara koshish bekar.
            if not looks_like_transport_failure(lines, code):
                return code, lines
            # Transport trigger: doosra rasta azmao (loop sirf 2
            # koshishon tak — order ki list hi had hai).
            self._log("Rasta %s par transport masla — doosra rasta "
                      "azmaya jayega." % mode, "WARN")
        self._log("Dono raste nakam — aakhri line: %s"
                  % last_lines(last_lines_out), "ERROR")
        return last_code, last_lines_out
