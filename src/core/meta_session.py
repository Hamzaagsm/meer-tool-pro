"""
meta_session.py — META mode (USB CDC serial port) par asal FT session.

Transsion/MTK phones META mode me aik USB CDC serial port dete hain
(MediaTek VID 0x0E8D). Paid/free tools (Pandora 9.24, Android Utility
Tool) isi port par MediaTek ke FT (factory-test) peer-message protocol
se Read Info / Factory Reset / Enable ADB chalate hain. Ye module usi
rasty ka basic tier deta hai:

  - Port discovery: pyserial se VID 0x0E8D wale ports; "META" wali
    description ko tarjeeh. VID na mile (kuch driver bindings VID
    expose nahi karti) to description/manufacturer me
    "meta"/"mediatek" bhi kaafi hai, aur Windows registry backup
    se chhoote hue ports bhi milte hain (Smart 20 bench, 2026-10-25:
    META port "foran khtam" isi liye dikha — tool use dekh hi nahi
    pata tha, jab ke baqi tools usi driver par COM port se kaam
    karte hain).
  - FT frame codec (PURE functions — bench ke baghair test ho sakte
    hain): build_frame() / parse_frames().
  - MetaSession: aik request/response ka sakht-verified session —
    jawab tabhi qabool hota hai jab frame ka checksum durust ho,
    msg_id bheji hui request se match kare, aur status token 0x00 ho
    (ops is status ko khud check karte hain). Unparseable jawab,
    checksum garbage ya khamoshi = saaf FAIL / MetaError — nakli
    success kabhi nahi.

FT framing (MediaTek FT peer transport, META CDC port par):
    STX byte 0xF0
    src peer id   (1 byte — host = 0x01)
    dest peer id  (1 byte — FT task = 0x02)
    msg_id        (uint16 LE)
    payload length(uint16 LE)
    payload       (length bytes)
    checksum      (1 byte = STX ke BAAD wale tamam bytes ka XOR)

Response frames me src/dest ulta hota hai, aur payload ka pehla byte
status hota hai (0x00 = success token); baqi payload asal data hai.

Ye constants aur msg-id values neeche wale block me PUBLIC FT message
table se liye gaye hain. IMAANDARI: codec ka round-trip software test
is build me hua hai, lekin kisi asal phone par bench-verification
abhi baqi hai (BUILD-REPORT discipline ke mutabiq) — is liye har op
jawab ki sakht tasdeeq ke baghair success nahi deta, aur naye-security
Dimensity chips par new-algorithm META FRP SERVER-REQUIRED hi rehta
hai (guard ops me hai, core.mdm_list.NEW_AUTH_TOKENS se).
"""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace

# ==========================================================================
# FT protocol constants — PUBLIC FT message table se.
# Bench-verification: codec software-tested hai; asal phone par
# verification baqi hai (module docstring dekho).
# ==========================================================================
FT_STX = 0xF0            # frame ki shuruaat wali byte
FT_PEER_HOST = 0x01      # src peer id jab host (PC) bhejta hai
FT_PEER_TASK = 0x02      # dest peer id — phone ki FT task
FT_STATUS_OK = 0x00      # response payload ka pehla byte — success token

META_VID = 0x0E8D        # MediaTek USB vendor id (META/Preloader ports)

# FT message ids (public FT table values)
FT_VERSION_INFO = 0x0001   # Read Info query — version/device maloomat
FT_FACTORY_RESET = 0x0002  # Factory Reset (userdata-level META reset)
FT_SET_ADB = 0x0003        # Enable ADB — payload 1 byte set-value (0x01 = on)

# --- Round-7 izafa (SEPT-SEC-RESEARCH §4-B) -------------------------------
# Ye msg-ids usi public FT table ki agli class se hain jo upar wale
# teen ids se shuru hoti hai. IMAANDARI (module docstring wala hi
# usool): codec software-tested hai, lekin in naye ids ki asal phone
# par bench-verification abhi baqi hai — is liye in par mabni har op
# jawab ki sakht tasdeeq (checksum + msg echo + status 0x00) ke
# baghair SUCCESS nahi deta; firmware in ids ko support na kare to
# op saaf FAIL dega, nakli success kabhi nahi.
FT_ERASE_PARTITION = 0x0004  # FRP Erase (B1) — payload: partition naam
                             # ASCII + NUL (masalan b"frp\x00"). Pandora
                             # 9.24 ke "META FRP new algorithm" wali
                             # class; entry khuli ho to local kaam hai.
FT_REBOOT = 0x0005           # Session completion (B5) — payload 1 byte:
                             # neeche wale REBOOT_* targets
FT_PART_READ = 0x0006        # Partition read (B3 framework) — payload:
                             # naam ASCII+NUL + offset u32 LE + len u32 LE;
                             # jawab ka payload = parha hua data
FT_PART_WRITE = 0x0007       # Partition write (B3 framework) — payload:
                             # naam ASCII+NUL + offset u32 LE + data

# FT_REBOOT ke targets
REBOOT_NORMAL = 0x00         # normal Android boot
REBOOT_FASTBOOT = 0x01       # fastboot mode me reboot
REBOOT_POWEROFF = 0x02       # power off

_FRAME_HEADER_LEN = 7    # STX + src + dest + msg_id(2) + length(2)
_FRAME_MIN_LEN = _FRAME_HEADER_LEN + 1  # + checksum (payload khali ho to)


class MetaError(Exception):
    """META session ki har nakami — ops ise saaf FAIL me badalte hain."""


# --------------------------------------------------------------------------
# Port discovery
# --------------------------------------------------------------------------
# Description/manufacturer markers — un ports ke liye jin ki VID pyserial
# se nahi milti (kuch driver bindings VID expose nahi karti — Smart 20
# bench: META port "foran khtam" isi liye dikha). Sirf ye do markers:
# aam "USB Serial" wale ghair-MediaTek ports is me nahi ate.
META_DESC_MARKERS = ("meta", "mediatek")


def _port_matches_meta(p):
    """pyserial port object META candidate hai ya nahi.

    Pehle VID 0x0E8D; VID na mile (None) to description/manufacturer
    me 'meta'/'mediatek' bhi kaafi hai.
    """
    try:
        if getattr(p, "vid", None) == META_VID:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        hay = " ".join([getattr(p, "description", "") or "",
                        getattr(p, "manufacturer", "") or ""]).lower()
    except Exception:  # noqa: BLE001
        return False
    return any(m in hay for m in META_DESC_MARKERS)


def _scan_winreg_meta():
    """Windows registry se VID_0E8D devices ke COM ports.

    HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB\\VID_0E8D&PID_XXXX...
    keys me FriendlyName + Device Parameters\\PortName hota hai.
    Sirf Windows par chalta hai; baqi par []. PID se filter NAHI
    (META port ka PID mukhtalif ho sakta hai) — preference scoring
    find_meta_port me hoti hai. pyserial se chhoote hue ports ka
    backup hai (jaise mtk_serial_fallback._scan_winreg).
    Returns [SimpleNamespace(device, description, manufacturer,
    vid, pid), ...].
    """
    if not sys.platform.startswith("win"):
        return []
    try:
        import winreg
    except Exception:  # noqa: BLE001
        return []
    found = []
    try:
        enum = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Enum\USB")
    except Exception:  # noqa: BLE001
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
            pid = None
            for part in vidkey.split("&"):
                if part.upper().startswith("PID_"):
                    try:
                        pid = int(part[4:], 16)
                    except Exception:  # noqa: BLE001
                        pid = None
            try:
                sub = winreg.OpenKey(enum, vidkey)
            except Exception:  # noqa: BLE001
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
                        inst_key = winreg.OpenKey(sub, inst)
                    except Exception:  # noqa: BLE001
                        continue
                    try:
                        try:
                            friendly, _t = winreg.QueryValueEx(
                                inst_key, "FriendlyName")
                        except Exception:  # noqa: BLE001
                            friendly = ""
                        try:
                            params = winreg.OpenKey(
                                inst_key, "Device Parameters")
                            port, _t = winreg.QueryValueEx(
                                params, "PortName")
                            winreg.CloseKey(params)
                        except Exception:  # noqa: BLE001
                            continue
                    finally:
                        winreg.CloseKey(inst_key)
                    if port:
                        found.append(SimpleNamespace(
                            device=str(port),
                            description=str(friendly or ""),
                            manufacturer="",
                            vid=META_VID, pid=pid))
            finally:
                winreg.CloseKey(sub)
    finally:
        winreg.CloseKey(enum)
    return found


def _candidate_ports():
    """Tamam META candidate ports (pyserial objects / registry entries).

    pyserial na ho to registry backup azmaya jata hai; dono khali hon
    to MetaError (install note ke saath) — caller isay guided FAIL
    me badal sakta hai.
    """
    found = []
    list_ports = None
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        list_ports = None
    if list_ports is not None:
        try:
            ports = list_ports.comports()
        except Exception as e:  # noqa: BLE001
            raise MetaError(f"Serial ports ki fehrist nahi mil saki: {e}")
        found = [p for p in ports if _port_matches_meta(p)]
    try:
        for reg in _scan_winreg_meta():
            if all(getattr(reg, "device", None)
                   != getattr(p, "device", None) for p in found):
                found.append(reg)
    except Exception:  # noqa: BLE001 — registry backup kabhi scan nahi rokta
        pass
    if list_ports is None and not found:
        raise MetaError(
            "pyserial nahi mila — META port scan nahi ho sakta. "
            "Install: python -m pip install pyserial (EXE build me "
            "pyserial shamil hota hai).")
    return found


def find_meta_ports():
    """Tamam META candidate ports: [(device, description, pid), ...]."""
    out = []
    for p in _candidate_ports():
        out.append((getattr(p, "device", "") or "",
                    getattr(p, "description", "") or "",
                    getattr(p, "pid", None)))
    return out


def _meta_preference(p):
    """Chhota number = behtar. 'META' naam pehle; phir MediaTek
    (non-Preloader) USB port; phir baqi VID match; Preloader sab se
    aakhir (wo META session nahi, BROM/Preloader hai)."""
    hay = " ".join([getattr(p, "description", "") or "",
                    getattr(p, "manufacturer", "") or ""]).lower()
    if "meta" in hay:
        return 0
    if "preloader" in hay:
        return 3
    if "mediatek" in hay:
        return 1
    return 2


def find_meta_port():
    """Sab se munasib META port object, warna None.

    Candidates VID 0x0E8D wale hain (ya description me
    'meta'/'mediatek'); preference: "META" naam > MediaTek USB
    Port > baqi VID match > Preloader.
    """
    candidates = _candidate_ports()
    if not candidates:
        return None
    return min(candidates, key=_meta_preference)


# --------------------------------------------------------------------------
# FT frame codec — PURE functions (koi I/O nahi)
# --------------------------------------------------------------------------
def _xor_checksum(data: bytes) -> int:
    chk = 0
    for b in data:
        chk ^= b
    return chk


def build_frame(msg_id: int, payload: bytes = b"") -> bytes:
    """Host -> FT task frame banao (STX, peers, msg_id, len, payload, XOR)."""
    payload = bytes(payload or b"")
    if not (0 <= int(msg_id) <= 0xFFFF):
        raise ValueError(f"msg_id range se bahir hai: {msg_id!r}")
    if len(payload) > 0xFFFF:
        raise ValueError("payload bohat lamba hai (max 65535 bytes).")
    body = bytes([FT_PEER_HOST, FT_PEER_TASK])
    body += int(msg_id).to_bytes(2, "little")
    body += len(payload).to_bytes(2, "little")
    body += payload
    return bytes([FT_STX]) + body + bytes([_xor_checksum(body)])


def parse_frames(buffer: bytes):
    """Buffer se mukammal, checksum-durust frames nikalo.

    Returns ([(msg_id, status, payload), ...], remaining_bytes).
    status = payload ka pehla byte (response convention); baqi bytes
    asal payload hain. Khali payload par status -1 hota hai.
    Checksum ghalat frame REJECT hota hai (list me nahi ata) — us ka
    STX skip karke aage scan jaari rehta hai. Adhoora frame
    remaining_bytes me wapas jata hai taake agla read usay poora kare.
    """
    frames = []
    buf = bytes(buffer or b"")
    i = 0
    n = len(buf)
    while True:
        # Agla STX dhoondo
        while i < n and buf[i] != FT_STX:
            i += 1
        if i >= n:
            return frames, b""
        if n - i < _FRAME_MIN_LEN:
            return frames, buf[i:]  # header hi adhoora hai — intezaar karo
        payload_len = int.from_bytes(buf[i + 5:i + 7], "little")
        frame_len = _FRAME_HEADER_LEN + payload_len + 1
        if n - i < frame_len:
            return frames, buf[i:]  # payload adhoora hai — intezaar karo
        frame = buf[i:i + frame_len]
        body = frame[1:-1]
        if _xor_checksum(body) != frame[-1]:
            # Checksum garbage — is STX ko reject karke aage scan karo
            i += 1
            continue
        msg_id = int.from_bytes(frame[3:5], "little")
        payload = frame[_FRAME_HEADER_LEN:-1]
        if payload:
            status, rest = payload[0], payload[1:]
        else:
            status, rest = -1, b""
        frames.append((msg_id, status, rest))
        i += frame_len


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------
class MetaSession:
    """Aik META port par khula hua FT session (request/response).

    Istemal:
        with MetaSession("COM7") as s:
            status, payload = s.request(FT_VERSION_INFO)
    Ya open_session(ctx) helper se (ops wahi istemal karte hain).
    """

    def __init__(self, port_name, baud=115200):
        self.port_name = str(port_name)
        self.baud = int(baud)
        self._ser = None

    def open(self):
        """Port kholo. pyserial/port ki nakami par MetaError."""
        if self._ser is not None:
            return self
        try:
            import serial
        except Exception:  # noqa: BLE001
            raise MetaError(
                "pyserial nahi mila — META session nahi khul sakta. "
                "Install: python -m pip install pyserial (EXE build me "
                "pyserial shamil hota hai).")
        try:
            self._ser = serial.Serial(self.port_name, self.baud,
                                      timeout=0.25, write_timeout=5)
        except Exception as e:  # noqa: BLE001
            raise MetaError(
                f"META port {self.port_name} khul nahi saka: {e} — "
                "port kisi aur program me khula ho sakta hai, ya "
                "driver (MediaTek VCOM) ka masla hai.")
        return self

    def close(self):
        ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def request(self, msg_id: int, payload: bytes = b"", timeout=10):
        """Aik FT request bhejo, matching jawab ka intezaar karo.

        Returns (status:int, payload:bytes) — payload status byte ke
        BAAD wala hissa hai. Timeout, checksum garbage hi garbage, ya
        port ki ghalti par MetaError — kabhi jhoota jawab nahi.
        """
        if self._ser is None:
            raise MetaError("META session khula hi nahi — pehle open() karo.")
        frame = build_frame(msg_id, payload)
        try:
            # Purana kachra saaf karke bhejo
            try:
                self._ser.reset_input_buffer()
            except Exception:  # noqa: BLE001
                pass
            self._ser.write(frame)
            self._ser.flush()
        except Exception as e:  # noqa: BLE001
            raise MetaError(f"META port par likha nahi ja saka: {e}")
        deadline = time.monotonic() + max(1.0, float(timeout))
        buffer = b""
        saw_garbage = False
        while time.monotonic() < deadline:
            try:
                waiting = getattr(self._ser, "in_waiting", 0) or 0
                chunk = self._ser.read(waiting if waiting else 1)
            except Exception as e:  # noqa: BLE001
                raise MetaError(f"META port se parha nahi ja saka: {e}")
            if not chunk:
                continue
            buffer += chunk
            frames, buffer = parse_frames(buffer)
            for got_id, status, rest in frames:
                if got_id == int(msg_id):
                    return status, rest
            if chunk and not frames:
                saw_garbage = True
        detail = (" — kuch bytes aye lekin koi durust FT frame nahi "
                  "bana (checksum/protocol mismatch)" if saw_garbage else "")
        raise MetaError(
            f"META jawab ka timeout ({timeout}s) — msg_id "
            f"0x{int(msg_id):04X} ka koi verified jawab nahi aya{detail}.")


# --------------------------------------------------------------------------
# Ops ke liye helper
# --------------------------------------------------------------------------
def _wait_for_meta_port(ctx, wait_s=10):
    """META port mile to object, warna None (MetaError propagate).

    Pehli scan me na mile to bounded wait — phone META mode me
    janay ke baad re-enumeration me aik do second lag sakte hain
    (port "foran khtam" wali shikayat ka aik hissa yahi race thi).
    """
    port = find_meta_port()
    if port is not None or wait_s <= 0:
        return port
    ctx.log("META port abhi nazar nahi aa raha — %.0f second tak "
            "dobara dhoondha ja raha hai (phone META mode me janay "
            "ke baad port banne me waqt lag sakta hai)..." % wait_s,
            "WARN")
    deadline = time.monotonic() + float(wait_s)
    while time.monotonic() < deadline:
        if ctx.is_cancelled():
            return None
        time.sleep(1.0)
        port = find_meta_port()
        if port is not None:
            return port
    return None


def open_session(ctx, wait_s=10):
    """META port dhoondh kar khula hua MetaSession wapas karo, warna None.

    Har nakami par ctx me guided wajah pehle hi log ho jati hai:
    pyserial missing → install note; port na mile → phone META mode
    me nahi / driver (VCOM) check. Port pehli scan me na mile to
    wait_s second tak dobara dhoondha jata hai (re-enumeration race).
    """
    try:
        port = _wait_for_meta_port(ctx, wait_s=wait_s)
    except MetaError as e:
        ctx.log(str(e), "ERROR")
        return None
    if port is None:
        ctx.log("META port nahi mila — phone META mode me nahi hai. "
                "Pehle BINA button: phone ON + ADB se 'Enter META "
                "Mode (ADB)' chalao, ya band phone sirf cable se "
                "lagao (META/Preloader port Device Manager me ana "
                "chahiye). Vol combo sirf BROM ke liye hai, META "
                "ke liye nahi.",
                "ERROR")
        ctx.log("Guide: MediaTek VCOM/USB driver laga hona lazmi hai — "
                "driver na ho to META port nazar hi nahi ayega, aur "
                "yeh session bhi nahi khulega.", "WARN")
        return None
    try:
        candidates = find_meta_ports()
    except MetaError:
        candidates = []
    for device, desc, pid in candidates:
        pid_txt = f", PID 0x{pid:04X}" if isinstance(pid, int) else ""
        ctx.log(f"META candidate port: {device} — {desc or 'MediaTek'}"
                f"{pid_txt}", "DATA")
    session = MetaSession(port.device)
    try:
        session.open()
    except MetaError as e:
        ctx.log(str(e), "ERROR")
        return None
    ctx.log(f"META session khul gaya: {port.device}", "OK")
    return session


def ft_checked(ctx, msg_id, payload=b"", timeout=15, what="FT request"):
    """Aik FT request bhejo aur verified jawab par hi True do.

    Round-7 ke chhote session ops (B5 completion set waghera) ka
    mushtaraka rasta: session kholo → request → status token 0x00
    ho tabhi True. Timeout / ghalat status / port ki nakami par
    wajah log karke False — nakli success ka koi rasta nahi.
    """
    session = open_session(ctx)
    if session is None:
        return False
    try:
        with session:
            status, _payload = session.request(msg_id, payload=payload,
                                               timeout=timeout)
    except MetaError as e:
        ctx.log(str(e), "ERROR")
        return False
    if ctx.is_cancelled():
        return False
    if status != FT_STATUS_OK:
        ctx.log(f"{what}: FT jawab aya lekin status token theek nahi "
                f"(status=0x{status & 0xFF:02X}) — amal qabool nahi hua "
                "mana jayega. Kuch firmwares ye FT command support hi "
                "nahi karte.", "ERROR")
        return False
    return True


def reboot_to_normal(ctx, timeout=15, already_gone_ok=True):
    """Verified kaam ke baad phone ko META mode se normal boot par bhejo.

    META session ops (FRP erase, factory reset, ADB set) ka aakhri
    qadam: pehle ye nahi hota tha aur phone META mode me atka rehta
    tha jab tak restart/disconnect na karo (Smart 20 bench flaw,
    2026-10-25). Ab op khud FT_REBOOT normal bhejta hai.

    already_gone_ok=True (completion step): META port pehle hi gayab
    ho (phone khud reboot ho raha ho) to bhi True — phone META se
    nikal chuka hai, wahi maqsad tha. False (standalone Reboot op):
    port na ho to FAIL (phone META me hai hi nahi).

    Returns True jab phone normal boot ki taraf ja raha ho (verified
    reboot ya port pehle hi gayab); False jab port mojood ho lekin
    reboot qabool na hua ho — caller phir manual reboot ki hidayat
    de (helper khud WARN log karta hai). Reboot ki nakami kabhi
    main amal ki kamyabi ko FAIL nahi banati — wo alag faisla hai.
    """
    try:
        ports = find_meta_ports()
    except MetaError:
        ports = []
    if not ports:
        if already_gone_ok:
            ctx.log("META port pehle hi nazar nahi aa raha — phone "
                    "shayad khud reboot ho raha hai (META se nikal "
                    "chuka hai).", "INFO")
            return True
        ctx.log("META port nahi mila — phone META mode me nahi hai, "
                "is liye normal boot par bheja nahi ja sakta.", "ERROR")
        return False
    ctx.log("Phone ko META mode se normal boot par bheja ja raha hai...",
            "INFO")
    ok = ft_checked(ctx, FT_REBOOT, payload=bytes([REBOOT_NORMAL]),
                    timeout=timeout, what="Reboot (Normal)")
    if ok:
        ctx.log("Reboot ka verified jawab (status OK) mil gaya — "
                "phone ab normal boot hona chahiye; boot hone me "
                "thoda waqt lag sakta hai.", "OK")
        return True
    # Reboot request nakam — kya phone khud META se nikal chuka hai?
    try:
        ports = find_meta_ports()
    except MetaError:
        ports = []
    if already_gone_ok and not ports:
        ctx.log("META port ab nazar nahi aa raha — phone shayad khud "
                "reboot ho raha hai (META se nikal chuka hai).", "INFO")
        return True
    ctx.log("Phone ko normal boot par bheja nahi ja saka — power "
            "button 10-15 second dabaye rakho ya 'Reboot to Normal "
            "(META Mode)' op chalao.", "WARN")
    return False
