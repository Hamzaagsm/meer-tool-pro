"""
meta_imei.py — META mode se MTK ka asal IMEI parhna / wapas
likhna (MEER ka APNA engine — koi bahari/vendor tool nahi).

RESEARCH NATIJA (2026-10-24 — public sources ki chaan-been):
  1. FT peer protocol ke andar NVRAM-record (LID) read/write
     wale message ids kisi public source me NAHI mile. MediaTek
     ki NVRAM rasai asal me MetaCore / META_DLL ki proprietary
     API hai, aur IMEI record ka LID number har modem project
     ka APNA hota hai — wo number model ki database files
     (AP_DB / MD1_DB, model ke stock firmware se) se milta
     hai. Isi liye SN Writer / Modem META har model ke liye
     pehle DB load karte hain (REPAIR-METHODS-RESEARCH §3.1b).
     Universal sabit LID koi hai hi nahi — andaze se LID par
     likhna MEER kabhi nahi karega.
  2. Lekin IMEI ki AP-side mehfooz surat har modern MTK par
     aik hi public-pehchani jagah par hai: nvdata partition ke
     ext4 file system ke andar file
     `md/NVRAM/NVD_IMEI/MP0B_001` (asal phone par:
     /data/nvram/md/NVRAM/NVD_IMEI/MP0B_001 — XDA / Hovatek
     ki public guides). Aur is file ka codec PUBLIC hai
     (open-source mtk_imei_db_tools — MediaTek imei.c ki
     lineage): har IMEI aik 12-byte record hai — digits
     BCD (nibble-swapped) pack hokar aik XOR mask se bandhe
     hain, byte 8/9 = 0xF3 markers, byte 10/11 = even/odd
     checksum. File size 24 byte = DB v1 (2 records),
     120 byte = DB v2 (10 records; pehle 2 hi IMEI hain).
  3. MEER ke paas FT partition read/write pehle se hai
     (core.meta_patch — GPT-verified, chunked, status-verified).
     Ye module usi par chalta hai: nvdata ka ext4 parho (neeche
     wala PURE parser), MP0B_001 dhoondo, IMEI parho. Likhna
     ho to: gate (core.imei_gate) ke baad, pehle file ka backup,
     phir sirf file ke apne bytes badlo, phir READ-BACK —
     read-back typed number se match na kare to FAIL, asal
     parha hua number log me. Nakli success ka rasta code me
     hai hi nahi.

IMAANDARI ki haddein:
  - ext4 parser sirf aam surat support karta hai: extents
    wali files/dirs, koi inline-data nahi, koi encryption
    flag nahi, linear directory scan. Is se bahir ki surat
    par saaf Ext4Error — wajah ke saath rukna.
  - Codec + ext4 + FT flow software-tested hain; asal phone
    par bench-verification baqi hai (baqi META kaam ki tarah).
"""

from __future__ import annotations

import json
import struct
from datetime import datetime

from core import meta_patch, meta_session
from core.runner import BACKUPS_DIR

MP0B_FILENAME = "MP0B_001"
MP0B_DIRNAME = "NVD_IMEI"
MP0B_PREFERRED_PATH = ("md", "NVRAM", "NVD_IMEI", "MP0B_001")

RECORD_LEN = 12
DB_SIZES = {24: 1, 120: 2}          # file size -> DB version
_XOR_MASK = (0xAB, 0xA0, 0x6F, 0x2F, 0x1F, 0x1E, 0x9A, 0x45)
_MARKER = 0xF3

ZERO_IMEI = "0" * 15


class MetaImeiError(Exception):
    """IMEI file/flow ki har nakami — op ise saaf FAIL banata hai."""


# --------------------------------------------------------------------------
# IMEI bunyadi usool (pure)
# --------------------------------------------------------------------------
def luhn_ok(num) -> bool:
    """IMEI ka Luhn check (15 hindsay lazmi).

    core.mdm_list._luhn_ok / core.spd_diag.luhn_ok wali hi
    shakl — teeno jagah aik hi usool hai."""
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


# --------------------------------------------------------------------------
# MP0B_001 codec (pure) — public imei.c lineage
# --------------------------------------------------------------------------
def imei_to_record(imei) -> bytes:
    """15-hindsay IMEI -> 12-byte MP0B record.

    Packing: byte i = (digit[2i+1] << 4) | digit[2i] (BCD,
    nibble-swapped — pehla digit low nibble me), phir XOR
    mask; aakhri digit (15th) akela low nibble me. Byte 8/9
    = 0xF3 markers; byte 10 = byte 0..9 ke even-index bytes
    ka jama (mod 256), byte 11 = odd-index wala jama.
    Kharab input par ValueError.
    """
    s = str(imei or "").strip()
    if len(s) != 15 or not s.isdigit():
        raise ValueError(f"IMEI 15 hindsay ka hona chahiye: {imei!r}")
    d = [ord(c) - 48 for c in s]
    out = bytearray(RECORD_LEN)
    for i in range(8):
        b = d[2 * i]
        if i != 7:
            b += d[2 * i + 1] << 4
        out[i] = b ^ _XOR_MASK[i]
    out[8] = _MARKER
    out[9] = _MARKER
    even = odd = 0
    for i in range(10):
        if i & 1:
            odd = (odd + out[i]) & 0xFF
        else:
            even = (even + out[i]) & 0xFF
    out[10] = even
    out[11] = odd
    return bytes(out)


def decode_record(rec):
    """12-byte record -> (imei | None, state).

    state: "ok" (durust number), "zero" (number 000... hai —
    null/kharab NVRAM wali halat), "invalid" (checksum fail
    ya nibble digit nahi — record kharab hai, is par bharosa
    nahi). "invalid" par imei hamesha None hai."""
    rec = bytes(rec or b"")
    if len(rec) != RECORD_LEN:
        return None, "invalid"
    even = sum(rec[i] for i in range(0, 10, 2)) & 0xFF
    odd = sum(rec[i] for i in range(1, 10, 2)) & 0xFF
    if even != rec[10] or odd != rec[11]:
        return None, "invalid"
    digits = []
    for i in range(8):
        dec = rec[i] ^ _XOR_MASK[i]
        lo = dec & 0x0F
        hi = (dec >> 4) & 0x0F
        if lo > 9:
            return None, "invalid"
        digits.append(chr(48 + lo))
        if i != 7:
            if hi > 9:
                return None, "invalid"
            digits.append(chr(48 + hi))
    s = "".join(digits)
    if s == ZERO_IMEI:
        return s, "zero"
    return s, "ok"


def db_version(data) -> int:
    """MP0B file ka DB version (size se). Ghalat size par
    ValueError — ye file asal MP0B shakl ki nahi."""
    n = len(bytes(data or b""))
    if n not in DB_SIZES:
        raise ValueError(
            f"MP0B_001 ka size {n} byte hai — pehchani shaklen "
            "24 byte (DB v1) ya 120 byte (DB v2) hain. Is file "
            "ko is codec se nahi parha ja sakta.")
    return DB_SIZES[n]


def parse_db(data) -> dict:
    """Poori MP0B file -> {version, imei1, state1, imei2, state2}.

    Sirf pehle 2 records IMEI hain (dono DB versions me);
    baqi records (v2 ke 8 filler) haath nahi lagte."""
    data = bytes(data or b"")
    ver = db_version(data)
    i1, s1 = decode_record(data[0:RECORD_LEN])
    i2, s2 = decode_record(data[RECORD_LEN:2 * RECORD_LEN])
    return {"version": ver, "imei1": i1, "state1": s1,
            "imei2": i2, "state2": s2}


def patch_db(data, imei1=None, imei2=None) -> bytes:
    """MP0B file ki NAYI copy — sirf diye gaye IMEI records
    badle jate hain; baqi tamam bytes (filler records samet)
    bilkul waisi hi rehti hain, lambai kabhi nahi badalti.

    Har naya record banate hi decode karke self-check hota
    hai — round-trip barabar na aye to ValueError (andar ki
    ghalti par device ko haath lagana hi nahi)."""
    data = bytes(data or b"")
    db_version(data)
    out = bytearray(data)
    for slot, val in (("IMEI 1", imei1), ("IMEI 2", imei2)):
        if val is None:
            continue
        s = str(val).strip()
        if s == ZERO_IMEI:
            raise ValueError(f"{slot}: 000000000000000 likhna "
                             "restore nahi hai — ye null number "
                             "hai, mana hai.")
        rec = imei_to_record(s)
        chk, _state = decode_record(rec)
        if chk != s:
            raise ValueError(f"{slot}: record self-check fail "
                             f"({s} -> {chk}) — andar ki ghalti, "
                             "write roki gayi.")
        off = 0 if slot == "IMEI 1" else RECORD_LEN
        out[off:off + RECORD_LEN] = rec
    return bytes(out)


def compare_readback(expected, actual):
    """Read-back tasdeeq (Hamza ka binding usool) — pure.

    expected/actual parse_db wale dicts hain; expected me jis
    slot ka imei None ho wo check nahi hota. Returns
    (True, "match") ya (False, wajah) — wajah me asal parha
    hua number lazmi hota hai. Read-back zero/invalid/mismatch
    — teeno FAIL hain; SUCCESS sirf pure match par."""
    problems = []
    for slot in ("1", "2"):
        exp = expected.get(f"imei{slot}")
        if exp is None:
            continue
        act = actual.get(f"imei{slot}")
        state = actual.get(f"state{slot}")
        if state == "zero" or act == ZERO_IMEI:
            problems.append(
                f"IMEI {slot}: read-back me number NULL "
                "(000000000000000) mila — write qabool nahi hua")
        elif state != "ok" or act is None:
            problems.append(
                f"IMEI {slot}: read-back record kharab/invalid "
                "parha gaya — write ki tasdeeq nahi ho saki")
        elif act != exp:
            problems.append(
                f"IMEI {slot}: read-back mismatch — likhna tha "
                f"{exp}, parha gaya {act}")
    if problems:
        return False, "; ".join(problems)
    return True, "match"


# --------------------------------------------------------------------------
# ext4 reader (pure) — read_at(offset, length) callable par
# --------------------------------------------------------------------------
_EXT4_MAGIC = 0xEF53
_EXTENT_MAGIC = 0xF30A
_INCOMPAT_64BIT = 0x80
_IFMT = 0xF000
_IFREG = 0x8000
_IFDIR = 0x4000
_FLAG_EXTENTS = 0x00080000
_FLAG_ENCRYPT = 0x00000800
_FLAG_INLINE = 0x10000000


class Ext4Error(Exception):
    """ext4 parse ki har nakami — wajah ke saath."""


class Ext4Reader:
    """Read-only ext4 walker.

    Usool: sirf aam surat — extents wali files/dirs, inline
    data nahi, encryption flag nahi, directory ki linear
    scan. In se bahir koi bhi surat Ext4Error deti hai;
    andaze wala rasta code me hai hi nahi."""

    def __init__(self, read_at):
        self._read_at = read_at
        sb = self._read(1024, 1024, "superblock")
        if struct.unpack_from("<H", sb, 56)[0] != _EXT4_MAGIC:
            raise Ext4Error("ext4 signature (0xEF53) superblock "
                            "me nahi mila — ye partition ext4 "
                            "nahi lagta (ya FT read durust nahi "
                            "aya).")
        self.block_size = 1024 << struct.unpack_from("<I", sb, 24)[0]
        if self.block_size not in (1024, 2048, 4096, 65536):
            raise Ext4Error(f"ext4 block size ghair-mamooli hai: "
                            f"{self.block_size}")
        self.inodes_per_group = struct.unpack_from("<I", sb, 40)[0]
        if not self.inodes_per_group:
            raise Ext4Error("superblock me inodes/group 0 hai — "
                            "parse roka gaya.")
        self.inode_size = struct.unpack_from("<H", sb, 88)[0] or 128
        incompat = struct.unpack_from("<I", sb, 100)[0]
        desc = struct.unpack_from("<H", sb, 254)[0]
        self.desc_size = desc if (incompat & _INCOMPAT_64BIT) \
            and desc >= 32 else 32
        self._gdt_off = 2048 if self.block_size == 1024 \
            else self.block_size
        self._desc_cache = {}

    # -- bunyadi read -------------------------------------------------
    def _read(self, off, n, what="data"):
        data = bytes(self._read_at(int(off), int(n)) or b"")
        if len(data) < n:
            raise Ext4Error(f"ext4 {what}: {n} bytes mange, "
                            f"mile {len(data)} (@{off}) — adhoora "
                            "data qabool nahi.")
        return data[:n]

    def _group_inode_table(self, group):
        if group not in self._desc_cache:
            raw = self._read(self._gdt_off + group * self.desc_size,
                             self.desc_size, "group descriptor")
            lo = struct.unpack_from("<I", raw, 8)[0]
            hi = 0
            if self.desc_size >= 64:
                hi = struct.unpack_from("<I", raw, 40)[0]
            self._desc_cache[group] = lo | (hi << 32)
        return self._desc_cache[group]

    # -- inode --------------------------------------------------------
    def inode(self, ino):
        """Inode ki bunyadi maloomat: {mode, size, flags, block_raw}."""
        if ino < 1:
            raise Ext4Error(f"inode number durust nahi: {ino}")
        group = (ino - 1) // self.inodes_per_group
        index = (ino - 1) % self.inodes_per_group
        table = self._group_inode_table(group)
        off = table * self.block_size + index * self.inode_size
        raw = self._read(off, self.inode_size, f"inode {ino}")
        mode = struct.unpack_from("<H", raw, 0)[0]
        size_lo = struct.unpack_from("<I", raw, 4)[0]
        flags = struct.unpack_from("<I", raw, 32)[0]
        size = size_lo
        if (mode & _IFMT) == _IFREG:
            size |= struct.unpack_from("<I", raw, 108)[0] << 32
        return {"mode": mode, "size": size, "flags": flags,
                "block_raw": raw[40:100]}

    def _check_file_flags(self, node, what):
        if not (node["flags"] & _FLAG_EXTENTS):
            raise Ext4Error(f"{what}: extents flag nahi hai "
                            "(purani indirect-block shakl) — ye "
                            "reader use support nahi karta, FAIL.")
        if node["flags"] & _FLAG_INLINE:
            raise Ext4Error(f"{what}: inline-data flag hai — "
                            "data inode ke andar hai, ye reader "
                            "use support nahi karta, FAIL.")
        if node["flags"] & _FLAG_ENCRYPT:
            raise Ext4Error(f"{what}: encryption flag hai — "
                            "file encrypted hai, IMEI is se "
                            "nahi parha ja sakta, FAIL.")

    def _extent_map(self, node, what):
        """Inode ke extent tree -> [(file_block, phys_off, length)]
        file_block ki tartib me, byte offsets ke saath."""
        raw = node["block_raw"]
        out = []
        self._walk_extents(raw, 0, out, what, depth_guard=0)
        out.sort(key=lambda t: t[0])
        return out

    def _walk_extents(self, block_bytes, base_off, out, what, depth_guard):
        if depth_guard > 5:
            raise Ext4Error(f"{what}: extent tree bohat gehra hai "
                            "— parse roka gaya.")
        magic, entries, _max, depth = struct.unpack_from(
            "<HHHH", block_bytes, 0)
        if magic != _EXTENT_MAGIC:
            raise Ext4Error(f"{what}: extent header magic durust "
                            "nahi (0x%04X) — data kharab hai."
                            % magic)
        if depth == 0:
            for i in range(entries):
                ee_block, ee_len, ee_hi, ee_lo = struct.unpack_from(
                    "<IHHI", block_bytes, 12 + i * 12)
                if ee_len > 32768:      # uninitialized extent
                    length_blocks = ee_len - 32768
                    continue            # data hai hi nahi — skip
                length_blocks = ee_len
                phys = (ee_hi << 32 | ee_lo) * self.block_size
                out.append((ee_block, phys,
                            length_blocks * self.block_size))
        else:
            for i in range(entries):
                ei_lo, ei_hi = struct.unpack_from(
                    "<IH", block_bytes, 12 + i * 12 + 4)
                leaf = (ei_hi << 32 | ei_lo) * self.block_size
                child = self._read(leaf, self.block_size,
                                   f"{what} extent leaf")
                self._walk_extents(child, base_off, out, what,
                                   depth_guard + 1)

    def read_file(self, ino):
        """(content_bytes, segments) — segments = file ki tartib
        me [(partition_offset, length)] (write ke liye wahi
        hisse jin me file ka data rehta hai)."""
        node = self.inode(ino)
        if (node["mode"] & _IFMT) != _IFREG:
            raise Ext4Error(f"inode {ino} regular file nahi hai.")
        self._check_file_flags(node, f"file inode {ino}")
        extents = self._extent_map(node, f"file inode {ino}")
        size = node["size"]
        parts = []
        segments = []
        done = 0
        for _fb, phys, length in extents:
            if done >= size:
                break
            take = min(length, size - done)
            parts.append(self._read(phys, take, "file data"))
            segments.append((phys, take))
            done += take
        if done < size:
            raise Ext4Error(f"file ka data mukammal nahi parha "
                            f"ja saka ({done}/{size} bytes) — "
                            "extent map adhoora hai.")
        return b"".join(parts), segments

    # -- directory ----------------------------------------------------
    def _dir_entries(self, ino):
        node = self.inode(ino)
        if (node["mode"] & _IFMT) != _IFDIR:
            raise Ext4Error(f"inode {ino} directory nahi hai.")
        self._check_file_flags(node, f"dir inode {ino}")
        extents = self._extent_map(node, f"dir inode {ino}")
        entries = []
        for _fb, phys, length in extents:
            block = self._read(phys, length, "directory block")
            pos = 0
            while pos + 8 <= len(block):
                child, rec_len, name_len = struct.unpack_from(
                    "<IHB", block, pos)
                if rec_len < 8 or pos + rec_len > len(block):
                    break
                if child != 0 and name_len:
                    raw_name = block[pos + 8:pos + 8 + name_len]
                    try:
                        name = raw_name.decode("utf-8")
                    except UnicodeDecodeError:
                        name = raw_name.decode("utf-8", "replace")
                    if name not in (".", ".."):
                        entries.append((name, child))
                pos += rec_len
        return entries

    def _child(self, dir_ino, name):
        entries = self._dir_entries(dir_ino)
        for nm, child in entries:
            if nm == name:
                return child
        low = name.lower()
        for nm, child in entries:
            if nm.lower() == low:
                return child
        return None

    def find_path(self, parts):
        """Root se descend karke aakhri component ka inode —
        na mile to Ext4Error (kis hisse par ruka, us ke saath)."""
        ino = 2
        walked = []
        for part in parts:
            nxt = self._child(ino, part)
            if nxt is None:
                raise Ext4Error(
                    f"rasta nahi mila: '/'.join(walked) ke andar "
                    f"'{part}' maujood nahi.")
            walked.append(part)
            ino = nxt
        return ino

    def find_mp0b(self):
        """(path_str, inode) — pehle pehchana rasta
        (md/NVRAM/NVD_IMEI/MP0B_001), phir poori directory
        walk me NVD_IMEI ke andar wali MP0B_001."""
        try:
            ino = self.find_path(MP0B_PREFERRED_PATH)
            return "/".join(MP0B_PREFERRED_PATH), ino
        except Ext4Error:
            pass
        candidates = []
        stack = [(2, "")]
        seen_dirs = 0
        while stack and seen_dirs < 512:
            dir_ino, prefix = stack.pop()
            seen_dirs += 1
            try:
                entries = self._dir_entries(dir_ino)
            except Ext4Error:
                continue
            for name, child in entries:
                path = f"{prefix}/{name}" if prefix else name
                try:
                    node = self.inode(child)
                except Ext4Error:
                    continue
                fmt = node["mode"] & _IFMT
                if fmt == _IFDIR:
                    stack.append((child, path))
                elif fmt == _IFREG and name == MP0B_FILENAME:
                    parent = path.rsplit("/", 1)[0] \
                        if "/" in path else ""
                    if parent.rsplit("/", 1)[-1].upper() == \
                            MP0B_DIRNAME:
                        candidates.append((path, child))
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            for path, child in candidates:
                if path.startswith("md/NVRAM/"):
                    return path, child
            raise Ext4Error(
                f"MP0B_001 aik se zyada jaga mili "
                f"({len(candidates)}) — konsi asal hai, andaze "
                "se nahi chuna jayega, FAIL.")
        raise Ext4Error("MP0B_001 file nvdata ke andar kahin "
                        "nahi mili — is device ka IMEI shayad "
                        "is shakl me mehfooz hi nahi hai.")


# --------------------------------------------------------------------------
# Session flow (FT partition IO par)
# --------------------------------------------------------------------------
def session_read_at(session, partition="nvdata"):
    """Ext4Reader ke liye read_at — FT_PART_READ se (chunked,
    verified; core.meta_patch)."""
    def read_at(off, n):
        return meta_patch.ft_part_read(session, partition, off, n)
    return read_at


def locate_imei(session, partition="nvdata"):
    """META session se MP0B_001 dhoondh kar parho.

    Returns dict: {path, ino, content, segments, parsed}.
    Har nakami MetaImeiError / meta_session.MetaError /
    Ext4Error — caller teeno ko saaf FAIL banata hai."""
    reader = Ext4Reader(session_read_at(session, partition))
    try:
        path, ino = reader.find_mp0b()
        content, segments = reader.read_file(ino)
    except Ext4Error as e:
        raise MetaImeiError(str(e))
    try:
        parsed = parse_db(content)
    except ValueError as e:
        raise MetaImeiError(
            f"File '{path}' mili lekin MP0B codec se parse "
            f"nahi hui: {e}")
    return {"reader": reader, "path": path, "ino": ino,
            "content": content, "segments": segments,
            "parsed": parsed}


def save_file_backup(ctx, found, partition="nvdata"):
    """Write se pehle file ki ASAL halat mehfooz karo:
    content ki .bin copy + extent map/parsed JSON record
    backups/meta-imei/ me. Returns (bin_path, json_path).
    Nakami par MetaImeiError — backup ke baghair write
    NAHI hoga (neighboring ops wala backup-first usool)."""
    try:
        folder = BACKUPS_DIR / "meta-imei"
        folder.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bin_path = folder / f"MP0B_001-{ts}.bin"
        bin_path.write_bytes(found["content"])
        dev = getattr(ctx, "device", None)
        meta = {
            "when": datetime.now().isoformat(timespec="seconds"),
            "partition": partition,
            "path_in_partition": found["path"],
            "inode": found["ino"],
            "segments": [[off, ln] for off, ln in found["segments"]],
            "parsed": found["parsed"],
            "device_serial": getattr(dev, "serial", "") or "",
            "device_model": getattr(dev, "model", "") or "",
            "backup_file": bin_path.name,
        }
        json_path = folder / f"MP0B_001-{ts}.json"
        json_path.write_text(json.dumps(meta, indent=2),
                             encoding="utf-8")
        return bin_path, json_path
    except MetaImeiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise MetaImeiError(f"Backup record nahi ban saka: {e}")


def write_imei_content(session, found, new_content,
                       partition="nvdata"):
    """File ke sirf wohi hisse likho jo asal me badle hain.

    segments file ki tartib wale hain; new_content ki lambai
    purani ke barabar honi lazmi hai (patch_db lambai kabhi
    nahi badalta — yahan phir check hai). Har chunk
    FT_PART_WRITE se status-verified likha jata hai
    (core.meta_patch); darmiyan me nakami par MetaError —
    jo hisse likhe gaye wo likhe gaye, caller read-back par
    hi FAIL dega aur backup se wapsi ki hidayat dega.
    Returns likhe gaye chunks ki tadaad."""
    old = found["content"]
    new_content = bytes(new_content or b"")
    if len(new_content) != len(old):
        raise MetaImeiError(
            f"Naye content ki lambai purani se mukhtalif hai "
            f"({len(new_content)} vs {len(old)}) — write roki "
            "gayi (file ki shakl badalna mana hai).")
    written = 0
    pos = 0
    for off, length in found["segments"]:
        chunk_new = new_content[pos:pos + length]
        chunk_old = old[pos:pos + length]
        if chunk_new != chunk_old:
            meta_patch.ft_part_write(session, partition, off,
                                     chunk_new)
            written += 1
        pos += length
    if pos != len(old):
        raise MetaImeiError("Segment map content se match nahi "
                            "karta — write roki gayi.")
    return written
