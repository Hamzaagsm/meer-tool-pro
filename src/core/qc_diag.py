"""
qc_diag.py — Qualcomm DIAG protocol ka native session layer (serial port).

Round 2 — Group 2: SERVER-REQUIRED-ROUTES-RESEARCH-2 §8.8 / §9.6.
QPST v2.7.497 (Qualcomm ka apna free tool) QCN backup/restore +
EFS karta hai; MEER wahi kaam DIAG protocol se NATIVELY karta
hai — koi vendor tool MEER ke andar nahi khulta.

PROTOCOL GROUNDING — public sources:
  - Framing: HDLC (0x7E flags, 0x7D escape, CRC-16/X-25) — DMSS
    Serial Data protocol (Qualcomm doc 80-V1294-1), XDA R&D
    thread "Using QDL, EHostDL and DIAG interfaces" — wahi codec
    jo core/spd_diag.py me hai, yahan dobara istemal hota hai.
  - Command codes (open-source diag_qcdm, jni/dm-commands.h):
    DIAG_VERNO_F = 0 (version info), DIAG_ESN_F = 1,
    DIAG_NV_READ_F = 38, DIAG_NV_WRITE_F = 39, DIAG_CONTROL_F = 41.
  - NV read jawab ki shakal (open-source libmmi sample, iopenv):
    reply[0] == 38 (DIAG_NV_READ_F), reply[1] == item ka low
    byte, data reply[3:] se — matlab jawab = [38, item_lo,
    item_hi, data...]. Request = [38, item_lo, item_hi].
  - NV write: request = [39, item_lo, item_hi, data...]; jawab
    = [39, item_lo, item_hi, status] (status 0 = kamyab).
    Status byte ki position bench-verified nahi hai — is liye
    write ki ASAL tasdeeq hamesha read-back hai (dobara parh
    kar bytes milao); status sirf pehli rok hai.
  - NV item numbers (public XDA "Complete List of NV Items"):
    NV_ESN_I = 0, NV_IMEI_I = 550. NV_FACTORY_DATA_1_I = 2497
    (libmmi sample se). In ke ilawa koi item number andaze se
    NAHI likha gaya — technician apne items `nv_items` param
    se de sakta hai.
  - Diag port: USB VID 05c6, PID 900e ("Qualcomm Diag 900E") —
    core/device_watch.py ki table se consistent.
  - Diag-enable dialer codes (report §8.8): *#*#13491#*#*
    (Xiaomi), *#801# (OnePlus), *#*#73694364#*#* (HyperOS 2.0);
    adb: `setprop sys.usb.config diag,adb` (aksar root chahiye).

QCN FILE FORMAT — MEER QCN v1 (MEER ki apni, documented):
  Binary records, koi header nahi: har record = [item u16 LE]
  [length u16 LE] [data bytes]. Strict parser: truncated record,
  trailing garbage, duplicate item ya zero-length item par file
  REJECT hoti hai. QPST ki .qcn ke saath interchange is build
  me verify NAHI hua — MEER ki backup file se MEER restore
  karta hai; QPST wali file ke liye QPST guide op me hai.

IMEI KI HAD (sakht): NV item 550 (IMEI) is module me SIRF
PARHA jata hai (backup me, read-only) — KABHI NAHI LIKHA jata.
Restore har file se item 550 ko SKIP karta hai aur log me
likhta hai. IMEI restore sirf existing META restore op ka kaam
hai (original box/sticker only, warning gate, backup-first,
read-back). Is module me koi IMEI-write rasta hai hi nahi.
"""

from __future__ import annotations

import time

from core.spd_diag import hdlc_encode, hdlc_parse

# ---------------------------------------------------------------------------
# Port pehchan (device_watch.USB_ID_TABLE se consistent)
# ---------------------------------------------------------------------------
QC_DIAG_VID = 0x05C6
QC_DIAG_PIDS = (0x900E,)
DEFAULT_BAUD = 115200

# ---------------------------------------------------------------------------
# DIAG command codes (public — diag_qcdm / DMSS)
# ---------------------------------------------------------------------------
DIAG_VERNO_F = 0
DIAG_ESN_F = 1
DIAG_NV_READ_F = 38
DIAG_NV_WRITE_F = 39
DIAG_CONTROL_F = 41

# ---------------------------------------------------------------------------
# NV items (public — XDA complete NV list / libmmi sample)
# ---------------------------------------------------------------------------
NV_ESN_I = 0
NV_IMEI_I = 550
NV_FACTORY_DATA_1_I = 2497
IMEI_NV_ITEM = NV_IMEI_I  # kabhi write nahi hota — neeche dekho

# Backup ki curated list: sirf sourced items. Technician apne
# items `nv_items` param se jor sakta hai (0..70212, validate hote hain).
BACKUP_NV_ITEMS = (NV_ESN_I, NV_IMEI_I, NV_FACTORY_DATA_1_I)
MAX_NV_ITEM = 70212
MAX_QCN_BYTES = 1024 * 1024   # 1 MB — QCN backup is se bari nahi hoti
MAX_NV_DATA_LEN = 4096


class QcDiagError(Exception):
    """QC Diag session ki har nakami — ops ise saaf FAIL me badalte hain."""


# ---------------------------------------------------------------------------
# MEER QCN v1 — pure build/parse
# ---------------------------------------------------------------------------
def build_qcn_bytes(items: dict) -> bytes:
    """{item_id: data} -> MEER QCN v1 bytes (item u16 LE, len u16 LE, data).

    Item 0..70212, data 1..4096 bytes — bahir ho to ValueError.
    Tartib item number ke hisaab se (deterministic file).
    """
    out = bytearray()
    for item in sorted(items):
        if not (0 <= int(item) <= MAX_NV_ITEM):
            raise ValueError(f"NV item {item} range se bahir hai.")
        data = bytes(items[item])
        if not (1 <= len(data) <= MAX_NV_DATA_LEN):
            raise ValueError(f"NV item {item} ka data size ghalat hai "
                             f"({len(data)} bytes).")
        out += int(item).to_bytes(2, "little")
        out += len(data).to_bytes(2, "little")
        out += data
    return bytes(out)


def parse_qcn_bytes(data: bytes):
    """MEER QCN v1 bytes -> ({item: data}, None) ya (None, wajah).

    Strict: khali file, truncated record, trailing garbage,
    duplicate item, zero-length item — sab reject. QPST ki file
    is layout par poori na utre to bhi reject (interchange
    bench-pending hai — jhoota parse kabhi nahi).
    """
    if not data:
        return None, "QCN file khali hai."
    if len(data) > MAX_QCN_BYTES:
        return None, (f"QCN file bohat bari hai ({len(data)} bytes "
                      f"— had {MAX_QCN_BYTES}).")
    items = {}
    off = 0
    while off < len(data):
        if off + 4 > len(data):
            return None, (f"QCN record offset {off} par kata hua hai "
                          "(item/length adhoora) — file kharab hai.")
        item = int.from_bytes(data[off:off + 2], "little")
        size = int.from_bytes(data[off + 2:off + 4], "little")
        off += 4
        if size < 1 or size > MAX_NV_DATA_LEN:
            return None, (f"NV item {item} ki length ghalat hai "
                          f"({size}) — file kharab hai.")
        if off + size > len(data):
            return None, (f"NV item {item} ka data kata hua hai "
                          f"({size} bytes chahiye, {len(data) - off} "
                          "mile) — file kharab hai.")
        if item in items:
            return None, (f"NV item {item} file me do dafa hai — "
                          "file kharab hai.")
        items[item] = bytes(data[off:off + size])
        off += size
    if not items:
        return None, "QCN file me koi NV item nahi mila."
    return items, None


# ---------------------------------------------------------------------------
# Response parsers — pure (offline test shuda)
# ---------------------------------------------------------------------------
def parse_version_response(payload) -> str | None:
    """VERNO jawab [0, ASCII version...] -> version string ya None.

    Pehla byte 0 lazmi; baqi printable ASCII (kam az kam 1 char).
    """
    if not payload:
        return None
    data = bytes(payload)
    if data[0] != DIAG_VERNO_F or len(data) < 2:
        return None
    text = data[1:].decode("ascii", errors="ignore").strip("\x00 \t\r\n")
    if not text or not all(32 <= ord(c) < 127 for c in text):
        return None
    return text


def parse_nv_read_response(payload, item: int):
    """NV-read jawab -> data bytes ya None.

    Lazmi: [38, item_lo, item_hi, data...] — cmd + item echo
    milna chahiye, data kam az kam 1 byte.
    """
    if not payload:
        return None
    data = bytes(payload)
    if len(data) < 4 or data[0] != DIAG_NV_READ_F:
        return None
    if data[1] != (int(item) & 0xFF) or data[2] != ((int(item) >> 8) & 0xFF):
        return None
    return data[3:]


def parse_nv_write_response(payload, item: int) -> bool:
    """NV-write jawab ki pehli tasdeeq — True/False.

    Lazmi: [39, item_lo, item_hi] echo; 4th byte (status) ho to
    0 lazmi. Ye sirf pehli rok hai — asal tasdeeq read-back hai.
    """
    if not payload:
        return False
    data = bytes(payload)
    if len(data) < 3 or data[0] != DIAG_NV_WRITE_F:
        return False
    if data[1] != (int(item) & 0xFF) or data[2] != ((int(item) >> 8) & 0xFF):
        return False
    if len(data) >= 4 and data[3] != 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------
def find_diag_ports():
    """Qualcomm Diag ports: [(device, description, pid), ...]."""
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        raise QcDiagError(
            "pyserial nahi mila — Diag port scan nahi ho sakta. "
            "Install: python -m pip install pyserial (EXE build me "
            "pyserial shamil hota hai).")
    try:
        ports = list_ports.comports()
    except Exception as e:  # noqa: BLE001
        raise QcDiagError(f"Serial ports ki fehrist nahi mil saki: {e}")
    out = []
    for p in ports:
        if getattr(p, "vid", None) == QC_DIAG_VID and \
                getattr(p, "pid", None) in QC_DIAG_PIDS:
            out.append((getattr(p, "device", "") or "",
                        getattr(p, "description", "") or "",
                        getattr(p, "pid", None)))
    return out


class QcDiagSession:
    """Aik Qualcomm Diag serial port par sakht-verified session.

    transport inject ho sakta hai (offline tests ke liye) —
    asal istemal me pyserial ka Serial banta hai. Har jawab ki
    shakal (cmd echo + item echo) verify hoti hai; khamoshi ya
    ghalat echo = QcDiagError. Koi jhoota jawab kabhi nahi.
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
            raise QcDiagError(
                "pyserial nahi mila — QC Diag session nahi khul sakta. "
                "Install: python -m pip install pyserial (EXE build "
                "me pyserial shamil hota hai).")
        try:
            self._ser = serial.Serial(self.port_name, self.baud,
                                      timeout=0.25, write_timeout=5)
        except Exception as e:  # noqa: BLE001
            raise QcDiagError(
                f"Diag port {self.port_name} khul nahi saka: {e} — "
                "port kisi aur program me khula ho sakta hai, ya "
                "Qualcomm driver ka masla hai.")
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

    def command(self, payload: bytes, timeout=3.0) -> bytes:
        """Aik DIAG command bhejo, pehla FCS-durust jawab lo.

        Jawab ka pehla byte request wale cmd se milna chahiye —
        warna QcDiagError (ghalat jawab kabhi payload nahi banta).
        """
        if self._ser is None:
            raise QcDiagError("QC Diag session khula hi nahi — pehle open() karo.")
        if not payload:
            raise QcDiagError("Diag command khali hai — bhejne ko kuch nahi.")
        frame = hdlc_encode(bytes(payload))
        try:
            try:
                self._ser.reset_input_buffer()
            except Exception:  # noqa: BLE001
                pass
            self._ser.write(frame)
        except Exception as e:  # noqa: BLE001
            raise QcDiagError(f"Diag command bhejna fail hua: {e}")
        buf = bytearray()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = self._ser.read(4096)
            except Exception as e:  # noqa: BLE001
                raise QcDiagError(f"Diag port parhna fail hua: {e}")
            if chunk:
                buf += chunk
                payloads, _rest = hdlc_parse(bytes(buf))
                if payloads:
                    resp = payloads[0]
                    if not resp or resp[0] != payload[0]:
                        raise QcDiagError(
                            "Diag jawab ka command code request se "
                            f"nahi mila (bheja {payload[0]}, aya "
                            f"{resp[0] if resp else 'khali'}) — "
                            "jawab qabool nahi.")
                    return resp
        raise QcDiagError(
            f"Diag command {payload[0]} par device ne koi "
            f"FCS-durust jawab nahi diya ({timeout:.0f}s) — Diag "
            "port jawab nahi de raha, ya device diag me hi nahi.")

    def read_version(self, timeout=3.0) -> str:
        """DIAG_VERNO_F probe — version string, warna QcDiagError."""
        resp = self.command(bytes((DIAG_VERNO_F,)), timeout=timeout)
        version = parse_version_response(resp)
        if version is None:
            raise QcDiagError(
                "VERNO jawab aya lekin version ki shakal durust "
                f"nahi: {bytes(resp)[:32].hex() or '-'}")
        return version

    def nv_read(self, item: int, timeout=3.0) -> bytes:
        """DIAG_NV_READ_F — item ka data, warna QcDiagError.

        Item read na ho (restricted item, ghalat echo) to error —
        caller faisla karta hai skip karna hai ya FAIL.
        """
        item = int(item)
        req = bytes((DIAG_NV_READ_F, item & 0xFF, (item >> 8) & 0xFF))
        resp = self.command(req, timeout=timeout)
        data = parse_nv_read_response(resp, item)
        if data is None:
            raise QcDiagError(
                f"NV item {item} ka jawab durust shakal me nahi aya "
                f"(echo mismatch ya khali data): "
                f"{bytes(resp)[:32].hex() or '-'}")
        return data

    def nv_write(self, item: int, data: bytes, timeout=3.0) -> bool:
        """DIAG_NV_WRITE_F — likho, jawab-echo check karo.

        IMEI item (550) yahan KABHI nahi likha jata — call se
        pehle hi QcDiagError (defense in depth; op bhi skip
        karta hai). Asal tasdeeq read-back hai — ye sirf pehli
        rok hai; poori tasdeeq ke liye nv_write_verified use karo.
        """
        item = int(item)
        if item == IMEI_NV_ITEM:
            raise QcDiagError(
                "NV item 550 (IMEI) Diag se KABHI nahi likha jata — "
                "IMEI restore sirf META restore op ka kaam hai "
                "(original box/sticker only).")
        req = bytes((DIAG_NV_WRITE_F, item & 0xFF,
                     (item >> 8) & 0xFF)) + bytes(data)
        resp = self.command(req, timeout=timeout)
        return parse_nv_write_response(resp, item)

    def nv_write_verified(self, item: int, data: bytes,
                          timeout=3.0) -> tuple:
        """Write + read-back — (True, wajah) ya (False, wajah).

        Sirf tab True jab (a) write ka jawab-echo durust ho AUR
        (b) dobara parha gaya data byte-ba-byte barabar ho.
        """
        item = int(item)
        data = bytes(data)
        try:
            ok = self.nv_write(item, data, timeout=timeout)
        except QcDiagError as e:
            return False, f"NV item {item} write fail: {e}"
        if not ok:
            return False, (f"NV item {item} ka write-jawab durust "
                           "nahi (echo/status mismatch) — write "
                           "qabool nahi hui.")
        try:
            back = self.nv_read(item, timeout=timeout)
        except QcDiagError as e:
            return False, (f"NV item {item} write ke baad read-back "
                           f"nahi ho saka: {e}")
        if back != data:
            return False, (f"NV item {item} read-back MISMATCH: "
                           f"likha {len(data)} bytes, parha "
                           f"{len(back)} bytes — write qabool nahi hui.")
        return True, f"NV item {item} write + read-back match."
