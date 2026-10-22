"""
scatter_build.py — Scatter Creator (COMPETITOR-RESEARCH-3 §4 P1).

MTK backup folder (MTKClient `rl` readback) ki GPT se SP Flash
Tool wala scatter .txt banta hai — backup ko flashable
dead-boot-repair asset banane ke liye. Khalis local transform
hai: koi device, koi engine nahi.

MTKClient ki `rl` readback folder me ye hota hai (vendored
MTKClient ke da_rl se tasdeeq shuda):
  - gpt.bin / gpt_backup.bin — flash ke pehle 32 sectors
    (protective MBR + GPT header + entries)
  - <partition>.bin — har partition ki image

GPT binary format public standard hai (UEFI spec): header
"EFI PART" LBA1 par; entries me type GUID, first/last LBA,
aur UTF-16LE naam. Scatter me start/size bytes me GPT se hi
ate hain — file ki maujoodgi sirf is_download tay karti hai.
"""

import struct
from pathlib import Path

_GPT_NAMES = ("gpt.bin", "gpt_backup.bin", "GPT.bin", "gpt_main.bin")
_ZERO_GUID = b"\x00" * 16


def find_gpt_file(folder):
    folder = Path(folder)
    for name in _GPT_NAMES:
        path = folder / name
        if path.is_file() and path.stat().st_size >= 1024:
            return path
    return None


def find_latest_mtk_backup(backups_dir):
    """Sab se naya backup folder jis me gpt.bin ho (mtk-* pehle)."""
    base = Path(backups_dir)
    if not base.is_dir():
        return None
    folders = [p for p in base.iterdir()
               if p.is_dir() and find_gpt_file(p) is not None]
    if not folders:
        return None
    folders.sort(key=lambda p: (0 if p.name.startswith("mtk-") else 1,
                                -p.stat().st_mtime))
    return folders[0]


def parse_gpt_binary(data, sector_size=512):
    """GPT bytes se partitions: [{name, first_lba, last_lba,
    start_bytes, size_bytes}]. Header LBA1 par (data LBA0 se
    shuru) ya LBA0 par (data seedha header se shuru) — dono
    surten handle hoti hain. Kharab data par ValueError."""
    data = bytes(data or b"")
    header_off = None
    if len(data) >= sector_size + 8 and \
            data[sector_size:sector_size + 8] == b"EFI PART":
        header_off = sector_size
        base = 0
    elif len(data) >= 8 and data[0:8] == b"EFI PART":
        header_off = 0
        base = -sector_size  # entries LBA disk-relative hai
    if header_off is None:
        raise ValueError("GPT header ('EFI PART') nahi mila — ye "
                         "gpt.bin nahi lagti ya kharab hai.")
    entries_lba = struct.unpack_from("<Q", data, header_off + 72)[0]
    num_entries = struct.unpack_from("<I", data, header_off + 80)[0]
    entry_size = struct.unpack_from("<I", data, header_off + 84)[0]
    if entry_size < 128 or num_entries == 0 or num_entries > 1024:
        raise ValueError(f"GPT entries ki maloomat ghair-mamooli "
                         f"hai (count={num_entries}, size={entry_size}).")
    entries_off = base + entries_lba * sector_size
    partitions = []
    for i in range(num_entries):
        off = entries_off + i * entry_size
        entry = data[off:off + entry_size]
        if len(entry) < 128:
            break
        if entry[0:16] == _ZERO_GUID:
            continue
        first_lba = struct.unpack_from("<Q", entry, 32)[0]
        last_lba = struct.unpack_from("<Q", entry, 40)[0]
        name = entry[56:128].decode("utf-16-le", errors="ignore")
        name = name.split("\x00")[0].strip()
        if not name or last_lba < first_lba:
            continue
        partitions.append({
            "name": name,
            "first_lba": first_lba,
            "last_lba": last_lba,
            "start_bytes": first_lba * sector_size,
            "size_bytes": (last_lba - first_lba + 1) * sector_size,
        })
    if not partitions:
        raise ValueError("GPT me koi partition entry nahi mili.")
    return partitions


def _is_preloader(name):
    return name.lower().startswith("preloader")


def build_scatter_text(partitions, file_names, platform="MTK"):
    """SP Flash Tool (V1.1.2 style) scatter text.
    file_names: {partition_name: file_name ya None} — file ho to
    is_download: true, warna file_name: NONE / is_download: false."""
    lines = [
        "###################################################################",
        "#  MEER Tool Pro — Scatter Creator",
        "#  MTK backup ki GPT se tayyar kiya gaya scatter.",
        "#  Start/size GPT ke asal values hain; jis partition ki",
        "#  image file folder me nahi, wo is_download: false hai.",
        "###################################################################",
        "- general: MTK_PLATFORM_CFG",
        "  info: ",
        "    - config_version: V1.1.2",
        f"      platform: {platform}",
        "      project: MEER-TOOL-PRO",
        "      storage: EMMC",
        "      boot_channel: MSDC_0",
        "      block_size: 0x20000",
        "",
    ]
    for idx, part in enumerate(partitions):
        name = part["name"]
        pre = _is_preloader(name)
        fname = file_names.get(name)
        lines += [
            f"- partition_index: SYS{idx}",
            f"  partition_name: {name}",
            f"  file_name: {fname if fname else 'NONE'}",
            f"  is_download: {'true' if fname else 'false'}",
            f"  type: {'SV5_BL_BIN' if pre else 'NORMAL_ROM'}",
            f"  linear_start_addr: {hex(part['start_bytes'])}",
            f"  physical_start_addr: {hex(part['start_bytes'])}",
            f"  partition_size: {hex(part['size_bytes'])}",
            f"  region: {'EMMC_BOOT_1' if pre else 'EMMC_USER'}",
            "  storage: HW_STORAGE_EMMC",
            "  boundary_check: true",
            "  is_reserved: false",
            f"  operation_type: {'BOOTLOADERS' if pre else 'UPDATE'}",
            "  is_upgradable: false",
            "  empty_boot_needed: false",
            "  reserve: 0x00",
            "",
        ]
    return "\n".join(lines)


def match_files(folder, partitions):
    """Har partition ke liye folder me <name>.bin dhoondo.
    Wapas: ({name: file_name|None}, warnings list) — file GPT
    size se bari ho to warning (scatter GPT size hi rakhta hai)."""
    folder = Path(folder)
    file_names, warnings = {}, []
    for part in partitions:
        candidate = folder / f"{part['name']}.bin"
        if candidate.is_file():
            file_names[part["name"]] = candidate.name
            actual = candidate.stat().st_size
            if actual > part["size_bytes"]:
                warnings.append(
                    f"{part['name']}.bin GPT size "
                    f"({part['size_bytes']} bytes) se bari hai "
                    f"({actual} bytes) — scatter me GPT wala size "
                    "rakha gaya hai; flash se pehle ye file check "
                    "kar lo.")
        else:
            file_names[part["name"]] = None
    return file_names, warnings
