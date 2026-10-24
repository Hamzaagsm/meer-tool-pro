"""
spd_diag.py — Unisoc/SPD Diag channel ka session layer (serial port).

Hamza ki SPD tartib (SPD-EXPANSION.md, 2026-10-24) ka pehla qadam
"Switch to Diag" isi module par khada hai: SPRD Diag port (USB VID
1782, PID 4D00/4D01 — core/device_watch.py ki table bhi yehi kehti
hai) dhoondho, kholo, aur device ki halat PARH KAR sabit karo.

PROTOCOL GROUNDING — imaandari se, jo public hai aur jo nahi:
  - Port ki pehchan PUBLIC hai: SPRD USB composition ke public
    driver INF (sprdvcom.inf / sprd_wvcom.inf) "SPRD Diag" aur
    "SPRD AT" ports ko VID 1782 par list karte hain; MEER ka
    device_watch bhi 1782:4D00/4D01 ko SPD maanta hai.
  - Framing is module me ISO/IEC 13239 HDLC ki hai (0x7E flags,
    0x7D escape, CRC-16/X-25 FCS) — ye ek PUBLIC standard hai aur
    neeche is ka codec pure functions me hai, bench ke baghair
    test shuda. Ye codec sirf transport ki seed hai.
  - IMEI ki halat is build me AT+CGSN se parhi jati hai — 3GPP
    TS 27.007 ka standard command, jiska jawab sakht usool se
    parse hota hai (15 hindsay + Luhn pass lazmi; warna jawab
    qabool hi nahi). Kuch SPRD compositions par diag port AT
    jawab nahi deta — tab session saaf DiagError deta hai, IMEI
    ki halat ka idda'a NAHI kiya jata.
  - **SPRD diag channel ka NV read/write command-set (opcode,
    NV item numbers) kisi public/open source me byte-level
    documented NAHI hai.** WriteIMEI / Research Download jaise
    vendor tools use andar se jante hain; Qualcomm DIAG ka
    protocol public hai lekin wo DOOSRE vendor ka hai — us ke
    opcode yahan istemal karna andaze se protocol banana hoga,
    jo MEER nahi karta. Is liye is build me diag se IMEI WRITE
    execute NAHI hoti: write_imei_via_diag() gate + Luhn ke baad
    imaandar guided-FAIL deta hai aur asal working raste
    (Cert Restore — pura prodnv) ki taraf bhejta hai. Jhooti ya
    baghair-tasdeeq SUCCESS is module me mumkin hi nahi rakhi
    gayi: koi write byte kabhi port par jata hi nahi.
  - Har mustaqbil ke write ke liye verify_readback() is module
    ka lazmi aakhri qadam hai (Hamza ki shart, 2026-10-24):
    likha hua number dobara parho; match na ho, 000000 aye ya
    null aye to natija FAIL hai — "written" ka daawa kabhi nahi.
"""

from __future__ import annotations

import re
import time

# ---------------------------------------------------------------------------
# Port pehchan (device_watch.USB_ID_TABLE se consistent — tests me cross-check)
# ---------------------------------------------------------------------------
SPRD_VID = 0x1782
DIAG_PIDS = (0x4D00, 0x4D01)
DEFAULT_BAUD = 115200          # SPRD AT/Diag ports ka aam baud

# ---------------------------------------------------------------------------
# HDLC framing (ISO/IEC 13239) — pure codec
# ---------------------------------------------------------------------------
HDLC_FLAG = 0x7E
HDLC_ESC = 0x7D
HDLC_ESC_XOR = 0x20


def crc16_x25(data: bytes) -> int:
    """CRC-16/X-25 (reflected poly 0x8408, init/xorout 0xFFFF).

    Public check value: crc16_x25(b"123456789") == 0x906E.
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def hdlc_encode(payload: bytes) -> bytes:
    """payload -> 0x7E + escaped(payload + FCS lo,hi) + 0x7E."""
    fcs = crc16_x25(payload)
    body = bytes(payload) + bytes((fcs & 0xFF, (fcs >> 8) & 0xFF))
    out = bytearray((HDLC_FLAG,))
    for b in body:
        if b in (HDLC_FLAG, HDLC_ESC):
            out.append(HDLC_ESC)
            out.append(b ^ HDLC_ESC_XOR)
        else:
            out.append(b)
    out.append(HDLC_FLAG)
    return bytes(out)


def hdlc_parse(buffer: bytes):
    """Stream buffer se mukammal, FCS-durust frames nikalo.

    Returns (payloads, rest): payloads = [bytes, ...] (FCS hata
    kar), rest = aakhri flag se aage ka na-mukammal hissa (flag
    samet) jo caller agle chunk ke aage jor kar dobara de. FCS
    kharab frame chup chaap giraya jata hai — kharab data kabhi
    payload nahi banta. Pehle flag se pehle ka kachra (garbage)
    bhi giraya jata hai; sirf flag-delimited hissa hi frame ban
    sakta hai. Koi flag hi na ho to rest khali (sab kachra tha).
    """
    payloads = []
    start = None          # maujooda frame ke pehle content byte ka index
    last_flag = None      # aakhri flag ka index (rest yahin se banta hai)
    for i, b in enumerate(buffer):
        if b == HDLC_FLAG:
            if start is not None and i > start:
                raw = _hdlc_unescape(buffer[start:i])
                if raw is not None and len(raw) >= 2:
                    body, lo, hi = raw[:-2], raw[-2], raw[-1]
                    if crc16_x25(body) == (lo | (hi << 8)):
                        payloads.append(body)
                # FCS fail / ulta escape: frame giraya gaya
            start = i + 1
            last_flag = i
    if last_flag is None:
        return payloads, b""
    return payloads, buffer[last_flag:]


def _hdlc_unescape(chunk: bytes):
    """Escape hatao. Ghair-qanooni escape par None (frame kachra)."""
    out = bytearray()
    i = 0
    while i < len(chunk):
        b = chunk[i]
        if b == HDLC_ESC:
            if i + 1 >= len(chunk):
                return None
            out.append(chunk[i + 1] ^ HDLC_ESC_XOR)
            i += 2
        elif b == HDLC_FLAG:
            return None
        else:
            out.append(b)
            i += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# IMEI qeemti usool — pure helpers (offline test shuda)
# ---------------------------------------------------------------------------
_DIGITS15_RE = re.compile(r"\d{15}")


def luhn_ok(num) -> bool:
    """IMEI ka Luhn check (15 hindsay lazmi)."""
    s = str(num or "").strip()
    if len(s) != 15 or not s.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(s)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _digits_of(raw):
    """raw (str/bytes) se pehla 15-hindsay run, warna None."""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        text = bytes(raw).decode("ascii", errors="ignore")
    else:
        text = str(raw)
    m = _DIGITS15_RE.search(text)
    return m.group(0) if m else None


def decode_imei_bcd(chunk: bytes):
    """NV-style BCD (nibble-swapped, 0xF filler) se 15-hindsay IMEI.

    8 bytes: har byte me pehle low nibble, phir high nibble aik
    hindsay hai; aakhri high nibble 0xF filler hota hai. 15
    hindsay na banein ya darmiyan me ghair-hindsay nibble aye
    to None — andaza kabhi nahi.
    """
    if not chunk or len(chunk) != 8:
        return None
    digits = []
    for b in chunk:
        for nib in (b & 0x0F, (b >> 4) & 0x0F):
            if nib == 0x0F:
                continue
            if nib > 9:
                return None
            digits.append(chr(48 + nib))
    s = "".join(digits)
    return s if len(s) == 15 else None


def extract_imei(payload) -> str | None:
    """Payload se Luhn-durust IMEI nikalo (ASCII run ya BCD window).

    Kuch na mile to None — ye function kabhi andaze se number
    NAHI banata; Luhn gate har raste par hai.
    """
    if payload is None:
        return None
    if isinstance(payload, str):
        payload = payload.encode("ascii", errors="ignore")
    data = bytes(payload)
    text = data.decode("ascii", errors="ignore")
    for m in _DIGITS15_RE.finditer(text):
        if luhn_ok(m.group(0)):
            return m.group(0)
    for off in range(0, max(0, len(data) - 7)):
        cand = decode_imei_bcd(data[off:off + 8])
        if cand and luhn_ok(cand):
            return cand
    return None


def classify_imei_state(raw) -> str:
    """IMEI ki halat: 'ok' | 'zero' | 'null' | 'invalid'.

    Hamza ki field halat (phone me 000000/null) ko pehchanne ke
    liye: 'zero' = 15 hindsay lekin sab sifar (modem ne write
    qabool nahi ki); 'null' = kuch hai hi nahi; 'invalid' = kuch
    aya lekin IMEI ki shakal/Luhn durust nahi.
    """
    if raw is None:
        return "null"
    if isinstance(raw, (bytes, bytearray)) and len(raw) == 0:
        return "null"
    if isinstance(raw, str) and raw.strip() == "":
        return "null"
    digits = _digits_of(raw)
    if digits is None:
        # ASCII/BCD me chhupa IMEI phir bhi ho sakta hai
        if extract_imei(raw) is not None:
            return "ok"
        return "invalid"
    if set(digits) == {"0"}:
        return "zero"
    return "ok" if luhn_ok(digits) else "invalid"


def verify_readback(expected: str, read_raw):
    """WRITE KE BAAD KI TASDEEQ (Hamza ki shart) — (bool, wajah).

    expected = jo asal IMEI likha gaya tha; read_raw = device se
    dobara parha gaya jawab (str/bytes jo bhi ho). Sirf exact
    match par True. 000000 / null / mismatch / parse-na-hona —
    sab FAIL hai, wajah ke saath.
    """
    exp = str(expected or "").strip()
    if not luhn_ok(exp):
        return False, ("tasdeeq shuru hi nahi ho sakti: likha gaya "
                       "number khud durust IMEI nahi (Luhn fail).")
    state = classify_imei_state(read_raw)
    if state == "ok":
        got = extract_imei(read_raw) or _digits_of(read_raw)
        if got == exp:
            return True, "read-back match — number device par sabit hai."
        return False, (f"read-back MISMATCH: likha {exp}, device se "
                       f"parha {got} — write qabool nahi hui.")
    if state == "zero":
        return False, ("read-back 000000000000000 hai — modem ne "
                       "write qabool nahi ki (yehi Hamza wali field "
                       "halat hai). Natija FAIL hai.")
    if state == "null":
        return False, ("read-back khali/null hai — device par koi "
                       "IMEI sabit nahi hua. Natija FAIL hai.")
    return False, ("read-back ka jawab IMEI ki shakal me parse "
                   "nahi hua — tasdeeq na-mumkin, natija FAIL hai.")


def parse_cgsn_response(text: str):
    """AT+CGSN jawab (3GPP TS 27.007) -> (state, value|None).

    Qabool shakalain: '+CGSN: <15 digits>' ya akeli line me 15
    hindsay, aakhir me OK. state classify_imei_state wali hi
    hai; OK-wala jawab lekin koi hindsay na ho -> 'null'.
    """
    if not text:
        return "null", None
    digits = _digits_of(text)
    if digits is None:
        return "null", None
    state = classify_imei_state(digits)
    return state, (digits if state in ("ok", "zero") else None)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class DiagError(Exception):
    """Diag session ki har nakami — ops ise saaf FAIL me badalte hain."""


def find_diag_ports():
    """SPRD Diag ports: [(device, description, pid), ...].

    pyserial na ho to DiagError (install note ke saath) — meta
    session wala hi pattern.
    """
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        raise DiagError(
            "pyserial nahi mila — Diag port scan nahi ho sakta. "
            "Install: python -m pip install pyserial (EXE build me "
            "pyserial shamil hota hai).")
    try:
        ports = list_ports.comports()
    except Exception as e:  # noqa: BLE001
        raise DiagError(f"Serial ports ki fehrist nahi mil saki: {e}")
    out = []
    for p in ports:
        if getattr(p, "vid", None) == SPRD_VID and \
                getattr(p, "pid", None) in DIAG_PIDS:
            out.append((getattr(p, "device", "") or "",
                        getattr(p, "description", "") or "",
                        getattr(p, "pid", None)))
    return out


class DiagSession:
    """Aik SPRD Diag/AT serial port par sakht-verified session.

    transport inject ho sakta hai (offline tests ke liye) —
    asal istemal me pyserial ka Serial banta hai. Jawab tabhi
    qabool hota hai jab wo apni shakal (OK/ERROR token, phir
    parse + Luhn) par poora utre; khamoshi ya kachra = DiagError.
    """

    def __init__(self, port_name, baud=DEFAULT_BAUD, transport=None):
        self.port_name = str(port_name)
        self.baud = int(baud)
        self._ser = transport

    def open(self):
        if self._ser is not None:
            return self
        try:
            import serial
        except Exception:  # noqa: BLE001
            raise DiagError(
                "pyserial nahi mila — Diag session nahi khul sakta. "
                "Install: python -m pip install pyserial (EXE build "
                "me pyserial shamil hota hai).")
        try:
            self._ser = serial.Serial(self.port_name, self.baud,
                                      timeout=0.25, write_timeout=5)
        except Exception as e:  # noqa: BLE001
            raise DiagError(
                f"Diag port {self.port_name} khul nahi saka: {e} — "
                "port kisi aur program me khula ho sakta hai, ya "
                "SPRD driver ka masla hai.")
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

    # -- AT channel (3GPP TS 27.007) --------------------------------
    def at_command(self, cmd: str, timeout=3.0) -> str:
        """Aik AT command bhejo, OK/ERROR tak ka jawab wapas karo.

        Timeout par jo kuch aya ho wo NA-mukammal hai — DiagError.
        Khamoshi bhi DiagError. Kabhi jhoota jawab nahi.
        """
        if self._ser is None:
            raise DiagError("Diag session khula hi nahi — pehle open() karo.")
        try:
            try:
                self._ser.reset_input_buffer()
            except Exception:  # noqa: BLE001
                pass
            self._ser.write((cmd.strip() + "\r").encode("ascii"))
        except Exception as e:  # noqa: BLE001
            raise DiagError(f"AT command bhejna fail hua ({cmd}): {e}")
        buf = bytearray()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = self._ser.read(4096)
            except Exception as e:  # noqa: BLE001
                raise DiagError(f"Diag port parhna fail hua: {e}")
            if chunk:
                buf += chunk
                if b"\r\nOK\r\n" in bytes(buf) or b"\nOK" in bytes(buf) \
                        or b"ERROR" in bytes(buf):
                    break
        text = bytes(buf).decode("utf-8", errors="replace")
        if not buf:
            raise DiagError(
                f"{cmd} par device ne koi jawab nahi diya "
                f"({timeout:.0f}s) — is composition par diag port "
                "AT jawab nahi deta, ya device diag me hi nahi.")
        if "ERROR" in text:
            raise DiagError(f"{cmd} par device ne ERROR diya: "
                            f"{text.strip()[:120]}")
        if "OK" not in text:
            raise DiagError(
                f"{cmd} ka jawab na-mukammal aya (OK token nahi "
                f"mila): {text.strip()[:120]}")
        return text

    def read_imei_state(self, timeout=3.0):
        """AT+CGSN se IMEI 1 ki halat: (state, value|None).

        state: 'ok' (value = 15 hindsay, Luhn pass), 'zero'
        (000000... — modem ke paas IMEI nahi), 'null' (jawab
        aya lekin koi IMEI nahi). Jawab hi na aye ya parse na
        ho to DiagError — halat ka idda'a baghair saboot nahi.
        """
        text = self.at_command("AT+CGSN", timeout=timeout)
        state, value = parse_cgsn_response(text)
        if state == "invalid":
            raise DiagError(
                "AT+CGSN ka jawab aya lekin IMEI durust shakal/"
                f"Luhn par poora nahi utra: {text.strip()[:120]}")
        return state, value


# ---------------------------------------------------------------------------
# IMEI WRITE — is build me execute NAHI hoti (module docstring dekho)
# ---------------------------------------------------------------------------
WRITE_VIA_DIAG_AVAILABLE = False

WRITE_UNAVAILABLE_NOTE = (
    "Diag channel se IMEI write is build me execute NAHI hoti: "
    "SPRD diag ke NV write commands public tor par documented "
    "nahi hain, aur baghair read-back tasdeeq ke koi write MEER "
    "kabhi nahi karega. Asal working rasta CERT RESTORE hai — "
    "pura prodnv (IMEI apni asal jagah aur hifazat samet) FDL se "
    "wapas likha jata hai: 'Unisoc Cert Restore (prodnv, FDL)' op "
    "chalao. Backup na ho to pehle Cert Backup lazmi hai.")


def write_imei_via_diag(ctx, session, imei1, imei2="") -> bool:
    """Gate ke baad imaandar guided-FAIL — koi byte port par NAHI jata.

    Tartib jaan boojh kar yahi hai: pehle IMEI GATE (warning +
    tasdeeq + audit), phir Luhn — taake technician ko har dafa
    wahi mehfooz tartib mile jo asal write par milegi. Gate na
    mile to ye function yahin ruk jata hai (guided STOP).
    `session` sirf mustaqbil ke verified write ke liye hai; is
    build me use chhua hi nahi jata.
    """
    from core import imei_gate
    if not imei_gate.imei_write_gate(ctx):
        return False
    imei1 = (imei1 or "").strip()
    imei2 = (imei2 or "").strip()
    if not imei1:
        ctx.log("IMEI 1 khali hai — dabbe/sticker wala asal IMEI "
                "likho.", "ERROR")
        return False
    for label, val in (("IMEI 1", imei1), ("IMEI 2", imei2)):
        if val and not luhn_ok(val):
            ctx.log(f"{label} durust nahi lagta (15 hindsay + "
                    f"checksum fail): {val}", "ERROR")
            return False
    ctx.log(f"IMEI 1 (original): {imei1}", "DATA")
    if imei2:
        ctx.log(f"IMEI 2 (original): {imei2}", "DATA")
    ctx.log(WRITE_UNAVAILABLE_NOTE, "WARN")
    return False
