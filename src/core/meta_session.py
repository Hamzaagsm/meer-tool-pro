"""
meta_session.py — META mode (USB CDC serial port) par asal FT session.

Transsion/MTK phones META mode me aik USB CDC serial port dete hain
(MediaTek VID 0x0E8D). Paid/free tools (Pandora 9.24, Android Utility
Tool) isi port par MediaTek ke FT (factory-test) peer-message protocol
se Read Info / Factory Reset / Enable ADB chalate hain. Ye module usi
rasty ka basic tier deta hai:

  - Port discovery: pyserial se VID 0x0E8D wale ports; "META" wali
    description ko tarjeeh.
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

import time

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

_FRAME_HEADER_LEN = 7    # STX + src + dest + msg_id(2) + length(2)
_FRAME_MIN_LEN = _FRAME_HEADER_LEN + 1  # + checksum (payload khali ho to)


class MetaError(Exception):
    """META session ki har nakami — ops ise saaf FAIL me badalte hain."""


# --------------------------------------------------------------------------
# Port discovery
# --------------------------------------------------------------------------
def _candidate_ports():
    """VID 0x0E8D wale tamam serial port objects (pyserial).

    pyserial na ho to MetaError (install note ke saath) — caller isay
    guided FAIL me badal sakta hai.
    """
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        raise MetaError(
            "pyserial nahi mila — META port scan nahi ho sakta. "
            "Install: python -m pip install pyserial (EXE build me "
            "pyserial shamil hota hai).")
    try:
        ports = list_ports.comports()
    except Exception as e:  # noqa: BLE001
        raise MetaError(f"Serial ports ki fehrist nahi mil saki: {e}")
    return [p for p in ports if getattr(p, "vid", None) == META_VID]


def find_meta_ports():
    """Tamam META candidate ports: [(device, description, pid), ...]."""
    out = []
    for p in _candidate_ports():
        out.append((getattr(p, "device", "") or "",
                    getattr(p, "description", "") or "",
                    getattr(p, "pid", None)))
    return out


def find_meta_port():
    """Sab se munasib META port object, warna None.

    Candidates VID 0x0E8D wale hain; jis ki description/manufacturer
    me "META" ayega use tarjeeh milegi.
    """
    candidates = _candidate_ports()
    if not candidates:
        return None
    for p in candidates:
        hay = " ".join([getattr(p, "description", "") or "",
                        getattr(p, "manufacturer", "") or ""]).lower()
        if "meta" in hay:
            return p
    return candidates[0]


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
def open_session(ctx):
    """META port dhoondh kar khula hua MetaSession wapas karo, warna None.

    Har nakami par ctx me guided wajah pehle hi log ho jati hai:
    pyserial missing → install note; port na mile → phone META mode
    me nahi / driver (VCOM) check.
    """
    try:
        candidates = find_meta_ports()
    except MetaError as e:
        ctx.log(str(e), "ERROR")
        return None
    for device, desc, pid in candidates:
        pid_txt = f", PID 0x{pid:04X}" if isinstance(pid, int) else ""
        ctx.log(f"META candidate port: {device} — {desc or 'MediaTek'}"
                f"{pid_txt}", "DATA")
    try:
        port = find_meta_port()
    except MetaError as e:
        ctx.log(str(e), "ERROR")
        return None
    if port is None:
        ctx.log("META port nahi mila — phone META mode me nahi hai. "
                "Phone band karke Volume dono dabaye hue cable lagao "
                "(META/Preloader port Device Manager me ana chahiye).",
                "ERROR")
        ctx.log("Guide: MediaTek VCOM/USB driver laga hona lazmi hai — "
                "driver na ho to META port nazar hi nahi ayega, aur "
                "yeh session bhi nahi khulega.", "WARN")
        return None
    session = MetaSession(port.device)
    try:
        session.open()
    except MetaError as e:
        ctx.log(str(e), "ERROR")
        return None
    ctx.log(f"META session khul gaya: {port.device}", "OK")
    return session
