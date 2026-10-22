"""
pac_builder.py — Unisoc/Spreadtrum .pac builder (public PAC
format; Cheetah/CM2 ke "PAC File Builder" ki free parity —
COMPETITOR-RESEARCH-3 §2.1/§2.5/§4 P1).

Readback folder (partition images) se aik structurally valid
.pac banta hai jo standard PAC parsers parh saken:

  PAC_HEADER — 2120 bytes (public layout):
    szVersion WCHAR[24] ("BP_R1.0.0"), dwSize (kul pac size),
    szPrdName WCHAR[256], szPrdVersion WCHAR[256],
    dwFileCount, dwFileOffset (= HEADER_SIZE), dwMode,
    dwFlashType, dwNandStrategy, dwIsNvBackup, dwNandPageType,
    szPrdAlias WCHAR[100], dwOmaDmProductFlag, dwIsOmaDm,
    dwIsPreload, byRes[800], wPacCRC1, wPacCRC2.

  FILE_T_ITEM — 2580 bytes har file par:
    dwSize (=2580), szFileID WCHAR[256], szFileName WCHAR[256],
    szFileVersion WCHAR[256], dwFileSize, dwMaxDownSize,
    dwDownLoadPos (pac ke andar data ka offset), reserved
    (zero), aakhir me wFileCRC (us file ke data ka CRC16).

  CRC: Spreadtrum ka CRC-16 (poly 0x1021, init 0x0000,
  MSB-first — FDL/BinPack wala maroof algorithm).
  wPacCRC1 = header ke pehle 2116 bytes par; wPacCRC2 = item
  table + file data (header ke baad ki tamam bytes) par.

IMAANDARI: ye builder public-documented layout ke mutabiq
structure banata hai. Kisi asal .pac ki pehli pakki tasdeeq
official Upgrade/Research tool me "Load Packet" karke hogi —
op us note ke saath hi natija deta hai. FDL ke baghair .pac
download mode se flash ho hi nahi sakta, is liye FDL1 ghayab
ho to builder saaf ERROR deta hai, nakli pac nahi banata.
"""

import struct
from pathlib import Path

HEADER_SIZE = 2120
ITEM_SIZE = 2580
PAC_VERSION = "BP_R1.0.0"

# Readback file stem -> PAC FileID (ResearchDownload ke maroof IDs)
_FILE_ID_MAP = {
    "fdl1": "FDL",
    "fdl": "FDL",
    "fdl2": "FDL2",
    "uboot": "UBOOT",
    "u-boot": "UBOOT",
    "splloader": "SPL",
    "spl": "SPL",
}

_IMAGE_SUFFIXES = (".bin", ".img")


# ---------------------------------------------------------------------------
# CRC-16 (Spreadtrum) — poly 0x1021, init 0, MSB-first
# ---------------------------------------------------------------------------
def _build_crc_table():
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                else (crc << 1) & 0xFFFF
        table.append(crc)
    return table


_CRC_TABLE = _build_crc_table()


def crc16(data, crc=0):
    for byte in data:
        crc = ((crc << 8) ^ _CRC_TABLE[((crc >> 8) ^ byte) & 0xFF]) & 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _wchar(text, count):
    """UTF-16LE fixed-width field (count WCHARs), zero-padded."""
    raw = (text or "").encode("utf-16-le")[: (count - 1) * 2]
    return raw + b"\x00" * (count * 2 - len(raw))


def file_id_for(filename):
    stem = Path(filename).stem.lower()
    if stem in _FILE_ID_MAP:
        return _FILE_ID_MAP[stem]
    return stem.upper().replace("-", "_")


def scan_readback(folder):
    """Folder ke partition images ki list — [{path, name, size}].
    Sirf .bin/.img files, naam ke hisaab se tartib."""
    folder = Path(folder)
    items = []
    if not folder.is_dir():
        return items
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
            items.append({"path": path, "name": path.name,
                          "size": path.stat().st_size})
    return items


def validate_readback(folder):
    """(items, errors, warnings) — pac banane ke qabil hai ya nahi.
    Errors hon to pac NAHI banna chahiye (op guided FAIL karega)."""
    items = scan_readback(folder)
    errors, warnings = [], []
    if not items:
        errors.append(
            "Is folder me koi partition image (.bin/.img) nahi mili — "
            "readback folder ghalat hai ya khali hai.")
        return items, errors, warnings
    stems = {Path(it["name"]).stem.lower() for it in items}
    if not ({"fdl1", "fdl"} & stems):
        errors.append(
            "FDL1 (fdl1.bin) NAHI mila — FDL ke baghair .pac download "
            "mode se flash ho hi nahi sakta, is liye aisi pac banana "
            "be-kaar hai. Pehle Research Download se mukammal "
            "readback lo jis me fdl1/fdl2 shamil hon.")
    if "fdl2" not in stems:
        warnings.append(
            "FDL2 (fdl2.bin) nahi mila — kuch models par FDL2 ke "
            "baghair download aage nahi barhta; readback dobara "
            "check kar lo.")
    for it in items:
        if it["size"] <= 0:
            errors.append(f"{it['name']} khali (0 bytes) hai — "
                          "readback na-mukammal hai.")
    return items, errors, warnings


def find_readback_folder(backups_dir):
    """BACKUPS_DIR me sab se naya Unisoc readback folder dhoondo.
    Pehchan: fdl*.bin ki maujoodgi, ya gpt.bin ke baghair >=3
    images (gpt.bin wale folder MTK ke hain — wo shamil nahi)."""
    base = Path(backups_dir)
    if not base.is_dir():
        return None
    candidates = []
    for sub in base.iterdir():
        if not sub.is_dir():
            continue
        names = {p.name.lower() for p in sub.iterdir() if p.is_file()}
        if "gpt.bin" in names:
            continue  # MTK backup hai
        has_fdl = any(n.startswith("fdl") and n.endswith(".bin")
                      for n in names)
        n_images = sum(1 for n in names
                       if n.endswith(_IMAGE_SUFFIXES))
        if has_fdl or n_images >= 3:
            candidates.append(sub)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# Build / parse
# ---------------------------------------------------------------------------
def build_pac(items, out_path, product_name, product_version="1.0"):
    """items: scan_readback wali list. .pac likh kar summary dict
    wapas karo: {path, total_size, file_count, entries:[...]}."""
    items = list(items)
    entries = []
    offset = HEADER_SIZE + ITEM_SIZE * len(items)
    for it in items:
        data_len = it["size"]
        entries.append({
            "file_id": file_id_for(it["name"]),
            "file_name": it["name"],
            "file_size": data_len,
            "max_down_size": data_len,
            "download_pos": offset,
            "path": it["path"],
        })
        offset += data_len
    total_size = offset

    header = bytearray(HEADER_SIZE)
    header[0:48] = _wchar(PAC_VERSION, 24)
    struct.pack_into("<I", header, 48, total_size)
    header[52:564] = _wchar(product_name, 256)
    header[564:1076] = _wchar(product_version, 256)
    struct.pack_into("<I", header, 1076, len(entries))   # dwFileCount
    struct.pack_into("<I", header, 1080, HEADER_SIZE)    # dwFileOffset
    # dwMode .. dwIsPreload tamam 0 (offsets 1084..1332) — default
    header[1332:1532] = _wchar(product_name, 100)        # szPrdAlias

    items_blob = bytearray()
    data_blobs = []
    for ent in entries:
        item = bytearray(ITEM_SIZE)
        struct.pack_into("<I", item, 0, ITEM_SIZE)
        item[4:516] = _wchar(ent["file_id"], 256)
        item[516:1028] = _wchar(ent["file_name"], 256)
        item[1028:1540] = _wchar(product_version, 256)
        struct.pack_into("<I", item, 1540, ent["file_size"])
        struct.pack_into("<I", item, 1544, ent["max_down_size"])
        struct.pack_into("<I", item, 1548, ent["download_pos"])
        data = Path(ent["path"]).read_bytes()
        if len(data) != ent["file_size"]:
            raise ValueError(
                f"{ent['file_name']} ka size badal gaya hai "
                f"({len(data)} != {ent['file_size']}) — readback "
                "dobara lo.")
        struct.pack_into("<H", item, ITEM_SIZE - 4, crc16(data))
        items_blob += item
        data_blobs.append(data)

    crc2 = crc16(bytes(items_blob))
    for blob in data_blobs:
        crc2 = crc16(blob, crc2)
    struct.pack_into("<H", header, HEADER_SIZE - 4,
                     crc16(bytes(header[:HEADER_SIZE - 4])))
    struct.pack_into("<H", header, HEADER_SIZE - 2, crc2)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(bytes(header))
        fh.write(bytes(items_blob))
        for blob in data_blobs:
            fh.write(blob)

    return {"path": out_path, "total_size": total_size,
            "file_count": len(entries), "entries": entries}


def _read_wchar(raw):
    return raw.decode("utf-16-le", errors="ignore").split("\x00")[0]


def parse_pac(path):
    """Standard-layout parser — header + item table parh kar
    summary do. Structure kharab ho to ValueError."""
    data = Path(path).read_bytes()
    if len(data) < HEADER_SIZE:
        raise ValueError("File PAC header (2120 bytes) se chhoti hai.")
    version = _read_wchar(data[0:48])
    if not version.startswith("BP_R"):
        raise ValueError(f"PAC version pehchan nahi mili: {version!r}")
    total_size = struct.unpack_from("<I", data, 48)[0]
    product = _read_wchar(data[52:564])
    prd_version = _read_wchar(data[564:1076])
    file_count = struct.unpack_from("<I", data, 1076)[0]
    file_offset = struct.unpack_from("<I", data, 1080)[0]
    crc1_stored = struct.unpack_from("<H", data, HEADER_SIZE - 4)[0]
    crc2_stored = struct.unpack_from("<H", data, HEADER_SIZE - 2)[0]
    if file_offset != HEADER_SIZE:
        raise ValueError(f"dwFileOffset ghair-mamooli hai: {file_offset}")
    if file_count > 512:
        raise ValueError(f"dwFileCount ghair-mamooli hai: {file_count}")
    entries = []
    for i in range(file_count):
        off = HEADER_SIZE + i * ITEM_SIZE
        item = data[off:off + ITEM_SIZE]
        if len(item) < ITEM_SIZE:
            raise ValueError(f"Item {i} na-mukammal hai.")
        item_size = struct.unpack_from("<I", item, 0)[0]
        if item_size != ITEM_SIZE:
            raise ValueError(f"Item {i} ka dwSize {item_size} hai "
                             f"(2580 hona chahiye).")
        file_size = struct.unpack_from("<I", item, 1540)[0]
        down_pos = struct.unpack_from("<I", item, 1548)[0]
        file_crc = struct.unpack_from("<H", item, ITEM_SIZE - 4)[0]
        blob = data[down_pos:down_pos + file_size]
        if len(blob) != file_size:
            raise ValueError(f"Item {i} ka data file se bahir hai.")
        entries.append({
            "file_id": _read_wchar(item[4:516]),
            "file_name": _read_wchar(item[516:1028]),
            "file_size": file_size,
            "download_pos": down_pos,
            "file_crc": file_crc,
            "crc_ok": crc16(blob) == file_crc,
        })
    crc1_ok = crc16(data[:HEADER_SIZE - 4]) == crc1_stored
    crc2_ok = crc16(data[HEADER_SIZE:]) == crc2_stored
    return {"version": version, "product": product,
            "product_version": prd_version, "total_size": total_size,
            "file_size_actual": len(data), "file_count": file_count,
            "entries": entries, "crc1_ok": crc1_ok, "crc2_ok": crc2_ok}
