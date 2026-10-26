"""
gpt_parse.py — GPT (GUID Partition Table) ka pure-Python parser +
Qualcomm FRP v2 ki erase-plan logic.

Koi engine, koi device nahi — sirf bytes in, partition naam out.
Isi liye ye module unit-test ke qabil hai (synthetic GPT se).

GPT layout (UEFI spec):
  LBA0  protective MBR
  LBA1  GPT header — signature "EFI PART", us me partition entries
        ka start LBA, count aur entry size
  phir  partition entries (har entry 128 bytes default):
        16B type GUID (sab zero = khali entry), 16B unique GUID,
        8B first LBA, 8B last LBA, 8B attrs, 72B naam (UTF-16LE)

QC FRP v2 ka usool (REPAIR-METHODS-RESEARCH §1.2/§4 P1#1):
  FRP jin partitions me reh sakta hai: `frp` (aam), `persistent`
  (Samsung QC), `config` (kuch Xiaomi/Oppo). GPT me jo mile wahi
  erase hoga. `persist` in me SHAAMIL NAHI hai aur kabhi nahi
  hoga — QC par persist calibration (sensors/fingerprint) hai;
  naam ki mushabihat (persistent vs persist) ki ghalti se bachne
  ke liye farq code me hard-coded hai.
"""

import struct

# FRP jin naamon se mil sakta hai (tartib = pehle ye try karo)
FRP_CANDIDATES = ("frp", "persistent", "config")

# Ye partition FRP NAHI hai — calibration hai. Kabhi erase nahi.
NEVER_ERASE = ("persist",)


def _find_header(data):
    """(header_offset, sector_size) ya None.

    Aam sector sizes (512 / 4096) par LBA1 wali jagah signature
    dhoondhta hai; dump agar seedha header se shuru ho to offset 0
    bhi qabool hai.
    """
    for sector in (512, 4096):
        off = sector
        if len(data) >= off + 8 and data[off:off + 8] == b"EFI PART":
            return off, sector
    if len(data) >= 8 and data[0:8] == b"EFI PART":
        return 0, 512
    return None


def parse_gpt(data: bytes, sector_size: int = 0) -> list:
    """GPT bytes -> partition naamon ki list (asal case ke saath).

    sector_size 0 = khud pehchano. Kharab/na-mukammal data par
    ValueError — caller ise guided FAIL me badlega (andaze se
    naam kabhi nahi bante).
    """
    if not data:
        raise ValueError("GPT data khali hai.")
    found = _find_header(data)
    if found is None:
        raise ValueError("GPT signature ('EFI PART') nahi mila — "
                         "ye GPT dump nahi lagta.")
    hdr_off, auto_sector = found
    sector = sector_size or auto_sector
    if len(data) < hdr_off + 92:
        raise ValueError("GPT header na-mukammal hai.")
    entries_lba = struct.unpack_from("<Q", data, hdr_off + 72)[0]
    num_entries = struct.unpack_from("<I", data, hdr_off + 80)[0]
    entry_size = struct.unpack_from("<I", data, hdr_off + 84)[0]
    if entry_size < 128 or entry_size > 4096:
        raise ValueError(f"GPT entry size ghair-mamooli hai: {entry_size}")
    if num_entries == 0 or num_entries > 1024:
        raise ValueError(f"GPT entries ki tadaad ghair-mamooli hai: "
                         f"{num_entries}")
    # Entries ka byte offset: mukammal dump (LBA0 se shuru) me
    # entries_lba * sector; agar dump seedha header (LBA1) se shuru
    # ho to header ke baad wale hisay se hisaab lagta hai.
    if hdr_off > 0:
        base = entries_lba * sector
    else:
        base = max(entries_lba - 1, 1) * sector
    names = []
    for i in range(num_entries):
        off = base + i * entry_size
        if off + entry_size > len(data):
            break
        entry = data[off:off + entry_size]
        if entry[0:16] == b"\x00" * 16:
            continue  # khali entry
        raw_name = entry[56:128]
        try:
            name = raw_name.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError:
            name = raw_name.decode("utf-16-le", errors="ignore")
        name = name.split("\x00")[0].strip()
        if name:
            names.append(name)
    if not names:
        raise ValueError("GPT parha gaya lekin koi partition naam "
                         "nahi mila — dump na-mukammal lagta hai.")
    return names


def parse_gpt_entries(data: bytes, sector_size: int = 0) -> list:
    """GPT bytes -> partition entries (naam + LBA range + size).

    Returns [{name, first_lba, last_lba, size_bytes, sector_size}]
    (asal case, GPT tartib me). Partition Manager ko naam ke
    saath SAHI SIZE chahiye hota hai — backup/read-back exact
    size se hota hai (adhoora backup = brick ka rasta), is liye
    sirf naam wali parse_gpt yahan kaafi nahi. Kharab data par
    ValueError (parse_gpt wala hi usool).
    """
    if not data:
        raise ValueError("GPT data khali hai.")
    found = _find_header(data)
    if found is None:
        raise ValueError("GPT signature ('EFI PART') nahi mila — "
                         "ye GPT dump nahi lagta.")
    hdr_off, auto_sector = found
    sector = sector_size or auto_sector
    if len(data) < hdr_off + 92:
        raise ValueError("GPT header na-mukammal hai.")
    entries_lba = struct.unpack_from("<Q", data, hdr_off + 72)[0]
    num_entries = struct.unpack_from("<I", data, hdr_off + 80)[0]
    entry_size = struct.unpack_from("<I", data, hdr_off + 84)[0]
    if entry_size < 128 or entry_size > 4096:
        raise ValueError(f"GPT entry size ghair-mamooli hai: {entry_size}")
    if num_entries == 0 or num_entries > 1024:
        raise ValueError(f"GPT entries ki tadaad ghair-mamooli hai: "
                         f"{num_entries}")
    if hdr_off > 0:
        base = entries_lba * sector
    else:
        base = max(entries_lba - 1, 1) * sector
    out = []
    for i in range(num_entries):
        off = base + i * entry_size
        if off + entry_size > len(data):
            break
        entry = data[off:off + entry_size]
        if entry[0:16] == b"\x00" * 16:
            continue  # khali entry
        raw_name = entry[56:128]
        try:
            name = raw_name.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError:
            name = raw_name.decode("utf-16-le", errors="ignore")
        name = name.split("\x00")[0].strip()
        if not name:
            continue
        first_lba = struct.unpack_from("<Q", entry, 32)[0]
        last_lba = struct.unpack_from("<Q", entry, 40)[0]
        if last_lba < first_lba:
            raise ValueError(f"Partition '{name}' ki LBA range "
                             "ulti hai — GPT dump kharab lagta hai.")
        out.append({"name": name, "first_lba": first_lba,
                    "last_lba": last_lba,
                    "size_bytes": (last_lba - first_lba + 1) * sector,
                    "sector_size": sector})
    if not out:
        raise ValueError("GPT parha gaya lekin koi partition naam "
                         "nahi mila — dump na-mukammal lagta hai.")
    return out


def _canon(names):
    """{lower-naam: asal-naam} mapping."""
    return {n.lower(): n for n in names}


def frp_erase_plan(names):
    """(erase_list, refusal) — dono me se aik hi bhara hoga.

    erase_list: GPT ke asal naamon se wahi partitions jo
    FRP_CANDIDATES me hain (candidate tartib se).
    refusal: (code, wajah) — code "only_persist" jab GPT me FRP
    ka koi naam nahi lekin `persist` maujood hai (ghalti se wahi
    mitane ki koshish rokna maqsad hai), warna "no_frp_partition".
    """
    lut = _canon(names)
    erase = [lut[c] for c in FRP_CANDIDATES if c in lut]
    # Hard guard: persist kisi surat erase list me nahi ja sakta —
    # candidate list me hai hi nahi, phir bhi dohari tasdeeq.
    erase = [n for n in erase if n.lower() not in NEVER_ERASE]
    if erase:
        return erase, None
    if "persist" in lut:
        return [], ("only_persist",
                    "GPT me sirf 'persist' mila — ye Qualcomm par "
                    "calibration partition hai (sensors/fingerprint), "
                    "FRP NAHI. Ise mitana phone ki calibration khatam "
                    "kar dega, is liye erase nahi kiya gaya.")
    return [], ("no_frp_partition",
                "GPT me FRP wali koi partition (frp / persistent / "
                "config) nahi mili — is model par FRP ka rasta EDL "
                "erase se nahi lagta.")
