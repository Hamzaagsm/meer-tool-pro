"""
util_transsion_rom_patcher.py — Transsion ROM Patcher (Super Debloat/MDM).

Oumse-class tools ka "Transsion Rom Maker" wala kaam, MEER ke
public tareeqe se: stock firmware ke super.img ko khol kar andar
se MDM / SecurityPlugin / finance / region-bloat ke CANDIDATE app
packages nikal kar super ko dobara band karna — taake har phone
par alag partition surgery ki bajaye aik patched super tayyar ho.

Pipeline (sab PC-side, offline):
  1. KHATRA gate sab se pehle (neeche dekho).
  2. Input: firmware-inbox me super.img / super wali ZIP, ya
     tools/firmware/<stem>/ ke extracted folder me super.img.
     Sparse super pehle hamari apni converter se raw banta hai.
  3. LP metadata vendored lpunpack.py (unix3dgforce, LGPL-3.0 —
     engines/lptools/) se parha jata hai: logical partitions ki
     fehrist log hoti hai.
  4. Chune hue SLOT (default B — reference tool ki tarah; params
     me slot mile ya fastboot mode me phone laga ho to asal
     current-slot) ke partitions scan hote hain: ext4 images ke
     andar standard app roots (app/, priv-app/, system/app/,
     system/priv-app/) me mile folder/APK naam
     tools/transsion-patch-list.json ke DOCUMENTED packages ke
     tokens se milaye jate hain.
  5. Mile hue candidates LOG me poori fehrist ke saath dikhaye
     jate hain — phir hi removal hota hai: partition image ki
     COPY par Cygwin e2fsprogs ke debugfs se (engines/lptools/
     debugfs/); har edit ke baad pehle e2fsck -y se bitmap ki
     durustagi, phir e2fsck -n verify — verify fail = edit shuda
     copy phenk di jati hai.
  6. Repack "metadata-preserving in-place" hai: asal super ki
     byte-copy par sirf edit hue partitions ke extents usi size
     me wapas. Output: tools/firmware-patched/<stem>-<slot>/
     super_patched_<slot>.img + summary file. ASAL firmware par
     kabhi kuch nahi likha jata.

IMAANDARI / HADEN:
  - ⚠️ BRICK: patched super SIRF unlocked bootloader ya
    vbmeta me verity band (disabled-verity) wale phone par boot
    hoga. Locked BL par flash = BRICK. Ye warning gate se pehle
    aur aakhir me dobara chhapti hai.
  - Candidate ≠ confirmed: token match sirf andesha hai — asal
    tasdeeq technician ki hai (fehrist is liye pehle dikhayi
    jati hai, aur removal danger-gate ki tasdeeq ke baghair
    hota hi nahi).
  - EROFS / F2FS partitions par removal NAHI hota (un ke liye
    rebuild tooling bundle me nahi hai) — op wahan saaf rukta
    hai. ext4 shared_blocks wali image par bhi rukta hai
    (vendored e2fsprogs 1.44.5 usay support nahi karta).
  - lpmake bundle me NAHI hai (trustworthy Windows build kisi
    official source par nahi mila — engines/lptools/SOURCE.md
    dekho). Is liye partition ka size badalna mumkin nahi;
    debugfs edit size nahi badalta, is liye in-place repack
    hamesha kaam karta hai. Size badal jaye to op FAIL deta hai.
  - Output super RAW hota hai (sparse nahi) — fastboot /
    SP Flash dono raw super le lete hain.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

from core.danger_gate import danger_gate
from core.runner import ENGINES_DIR, TOOLS_DIR

OP = {
    "id": "util_transsion_rom_patcher",
    "category": "Utility",
    "name": "Transsion ROM Patcher (Super Debloat/MDM)",
    "engine": "lptools",
    "modes": (),
    "server_required": False,
    "danger_write": True,
}

LPTOOLS_DIR = ENGINES_DIR / "lptools"
LPUNPACK_PY = LPTOOLS_DIR / "lpunpack.py"
DEBUGFS_DIR = LPTOOLS_DIR / "debugfs"
PATCH_LIST_FILE = TOOLS_DIR / "transsion-patch-list.json"
INBOX_DIR = TOOLS_DIR / "firmware-inbox"
FW_DIR = TOOLS_DIR / "firmware"
OUT_BASE = TOOLS_DIR / "firmware-patched"

SPARSE_MAGIC = 0xED26FF3A
EXT4_MAGIC = 0xEF53
EROFS_MAGIC = 0xE0F5E1E2
F2FS_MAGIC = 0xF2F52010
# ext4 superblock (file offset 1024) ke feature fields
_EXT4_INCOMPAT = 1024 + 0x60
_EXT4_RO_COMPAT = 1024 + 0x64
RO_COMPAT_SHARED_BLOCKS = 0x4000

# Jin logical partitions ke andar apps rehte hain (slot suffix
# hata kar compare hota hai)
APP_PARTITIONS = ("system", "system_ext", "product", "vendor", "odm")
# Partition image ke andar app roots (image-root se relative)
APP_ROOTS = ("app", "priv-app", "system/app", "system/priv-app")

BRICK_WARNING = (
    "⚠️⚠️ BRICK WARNING — patched super SIRF us phone par boot "
    "hoga jis ka bootloader UNLOCKED ho ya jis ki vbmeta me "
    "verity BAND (disabled-verity) ho. LOCKED bootloader wale "
    "phone par patched super flash karna = BRICK (phone dead / "
    "bootloop, aur recovery mushkil). Pehle phone ka bootloader "
    "unlock karo (is tool ke Bootloader Unlock ops) ya vbmeta "
    "verity band karo — warna ye patched super US phone ke "
    "liye mat banao."
)


# ---------------------------------------------------------------------------
# Chhote helpers
# ---------------------------------------------------------------------------

def _newest(candidates):
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return candidates[0]


def _run_capture(cmd, timeout=300):
    """Command chalao, (output, exit_code) wapas — kabhi raise nahi."""
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([str(c) for c in cmd], capture_output=True,
                             text=True, timeout=timeout, **kwargs)
        return (out.stdout or "") + (out.stderr or ""), out.returncode
    except Exception as e:  # noqa: BLE001
        return f"error: {e}", -1


def _win_path(p):
    """Cygwin tools ke liye path: backslash -> forward slash."""
    return str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# Sparse <-> raw
# ---------------------------------------------------------------------------

def is_sparse(path):
    """Android sparse format hai? (magic check, pure)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
        return len(head) == 4 and \
            struct.unpack("<I", head)[0] == SPARSE_MAGIC
    except Exception:  # noqa: BLE001
        return False


def sparse_to_raw(src, dst, chunk_bytes=4 * 1024 * 1024):
    """Sparse image -> raw image. Kul raw size (bytes) wapas.

    Format: header 28 bytes (magic, major, minor, file_hdr_sz,
    chunk_hdr_sz, blk_sz, total_blks, total_chunks, checksum),
    phir chunks: RAW 0xCAC1 / FILL 0xCAC2 / DONT_CARE 0xCAC3 /
    CRC32 0xCAC4. Ghalat format par ValueError.
    """
    with open(src, "rb") as fh:
        header = fh.read(28)
        if len(header) < 28:
            raise ValueError("sparse header adhoora hai")
        (magic, _major, _minor, file_hdr_sz, chunk_hdr_sz, blk_sz,
         total_blks, total_chunks, _crc) = struct.unpack("<IHHHHIIII",
                                                         header)
        if magic != SPARSE_MAGIC:
            raise ValueError("sparse magic match nahi hua")
        if file_hdr_sz > 28:
            fh.seek(file_hdr_sz - 28, 1)
        written = 0
        with open(dst, "wb") as out:
            for _ in range(total_chunks):
                chead = fh.read(12)
                if len(chead) < 12:
                    raise ValueError("sparse chunk header adhoora hai")
                ctype, _res, chunk_sz, total_sz = struct.unpack(
                    "<HHII", chead)
                if chunk_hdr_sz > 12:
                    fh.seek(chunk_hdr_sz - 12, 1)
                data_len = total_sz - chunk_hdr_sz
                out_len = chunk_sz * blk_sz
                if ctype == 0xCAC1:  # RAW
                    remaining = data_len
                    while remaining > 0:
                        block = fh.read(min(chunk_bytes, remaining))
                        if not block:
                            raise ValueError("sparse data adhoora hai")
                        out.write(block)
                        remaining -= len(block)
                elif ctype == 0xCAC2:  # FILL
                    fill = fh.read(4)
                    if len(fill) < 4:
                        raise ValueError("sparse fill adhoora hai")
                    piece = fill * (chunk_bytes // 4)
                    remaining = out_len
                    while remaining > 0:
                        n = min(len(piece), remaining)
                        out.write(piece[:n])
                        remaining -= n
                    if data_len > 4:
                        fh.seek(data_len - 4, 1)
                elif ctype == 0xCAC3:  # DONT_CARE -> zeros
                    out.seek(out_len, 1)
                    out.truncate(out.tell())
                elif ctype == 0xCAC4:  # CRC32 chunk — data skip
                    if data_len > 0:
                        fh.seek(data_len, 1)
                else:
                    raise ValueError(
                        f"na-maloom sparse chunk type: 0x{ctype:04x}")
                written += out_len
        expected = total_blks * blk_sz
        if written != expected:
            raise ValueError(
                f"sparse size mismatch: chunks se {written} bytes "
                f"bane, header {expected} kehta hai")
        return written


# ---------------------------------------------------------------------------
# LP metadata (vendored lpunpack.py)
# ---------------------------------------------------------------------------

def load_lpunpack(path=LPUNPACK_PY):
    """lpunpack.py ko module ki tarah load karo (pinned vendored copy)."""
    spec = importlib.util.spec_from_file_location("meer_lpunpack",
                                                  str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"lpunpack.py load nahi ho saka: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_super_metadata(lp, raw_super):
    """LpUnpack parser se (metadata, partitions_info) — partitions_info:
    [{name, group, size, extents: [(offset, size)]}]."""
    unpacker = lp.LpUnpack(SUPER_IMAGE=str(raw_super))
    try:
        md = unpacker._read_metadata()
    finally:
        try:
            unpacker._fd.close()
        except Exception:  # noqa: BLE001
            pass
    groups = list(md.groups)
    parts = []
    for part in md.partitions:
        extents = []
        size = 0
        for i in range(part.num_extents):
            ext = md.extents[part.first_extent_index + i]
            if ext.target_type != lp.LP_TARGET_TYPE_LINEAR:
                raise ValueError(
                    f"partition {part.name}: ZERO-type extent hai — "
                    "ye super in-place repack ke qabil nahi")
            extents.append((ext.target_data * lp.LP_SECTOR_SIZE,
                            ext.num_sectors * lp.LP_SECTOR_SIZE))
            size += ext.num_sectors * lp.LP_SECTOR_SIZE
        gname = ""
        if 0 <= part.group_index < len(groups):
            gname = groups[part.group_index].name
        parts.append({"name": part.name, "group": gname,
                      "size": size, "extents": extents})
    return md, parts


def extract_partition(raw_super, extents, out_path, chunk=1024 * 1024):
    """Extents ko jor kar partition image banao. Kul bytes wapas."""
    total = 0
    with open(raw_super, "rb") as src, open(out_path, "wb") as out:
        for offset, size in extents:
            src.seek(offset)
            remaining = size
            while remaining > 0:
                block = src.read(min(chunk, remaining))
                if not block:
                    raise ValueError("super file adhoori hai (extent "
                                     "file se bahir hai)")
                out.write(block)
                remaining -= len(block)
                total += len(block)
    return total


def write_partition_back(super_path, extents, img_path, chunk=1024 * 1024):
    """Edit hui partition image ko super ki copy me usi jaga/us size
    me wapas likho. Size mismatch par ValueError."""
    img_size = Path(img_path).stat().st_size
    total_extent = sum(size for _off, size in extents)
    if img_size != total_extent:
        raise ValueError(
            f"partition image ka size badal gaya ({img_size} != "
            f"{total_extent}) — size badalne wali repack ke liye "
            "lpmake chahiye jo bundle me nahi hai (SOURCE.md dekho)")
    with open(img_path, "rb") as src, open(super_path, "r+b") as dst:
        for offset, size in extents:
            dst.seek(offset)
            remaining = size
            while remaining > 0:
                block = src.read(min(chunk, remaining))
                if not block:
                    raise ValueError("partition image adhoori hai")
                dst.write(block)
                remaining -= len(block)


# ---------------------------------------------------------------------------
# Filesystem pehchan (ext4 / erofs / f2fs)
# ---------------------------------------------------------------------------

def detect_fs(img_path):
    """Partition image ka filesystem: 'ext4' | 'erofs' | 'f2fs' |
    'unknown' (pure — magic bytes par)."""
    try:
        with open(img_path, "rb") as fh:
            fh.seek(1024)
            buf = fh.read(64)
        if len(buf) < 60:
            return "unknown"
        erofs = struct.unpack_from("<I", buf, 0)[0]
        if erofs == EROFS_MAGIC:
            return "erofs"
        f2fs = struct.unpack_from("<I", buf, 0)[0]
        if f2fs == F2FS_MAGIC:
            return "f2fs"
        ext = struct.unpack_from("<H", buf, 56)[0]
        if ext == EXT4_MAGIC:
            return "ext4"
        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def ext4_shared_blocks(img_path):
    """ext4 image me shared_blocks (RO compat 0x4000) hai? (pure)"""
    try:
        with open(img_path, "rb") as fh:
            fh.seek(_EXT4_RO_COMPAT)
            raw = fh.read(4)
        if len(raw) < 4:
            return False
        return bool(struct.unpack("<I", raw)[0] & RO_COMPAT_SHARED_BLOCKS)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Patch list + candidate matching
# ---------------------------------------------------------------------------

def load_patch_list(path=PATCH_LIST_FILE):
    """tools/transsion-patch-list.json parho — kharab/na-mile par
    khali structure (kabhi raise nahi)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("groups"),
                                                  list):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"groups": []}


def match_candidates(names, patch_list):
    """names: image ke andar mile folder/APK naam (str list).
    Return: [{name, package, label, group}] — har naam zyada se
    zyada aik entry se match hota hai. (pure)"""
    found = []
    lowered = [(n, n.lower()) for n in names]
    for group in patch_list.get("groups", []):
        gname = group.get("name") or group.get("id") or ""
        for entry in group.get("entries", []):
            tokens = [str(t).lower() for t in entry.get("tokens", [])
                      if str(t).strip()]
            if not tokens:
                continue
            for name, low in lowered:
                if any(tok in low for tok in tokens):
                    if not any(f["name"] == name for f in found):
                        found.append({
                            "name": name,
                            "package": entry.get("package", ""),
                            "label": entry.get("label", ""),
                            "group": gname,
                            "caution": entry.get("caution", ""),
                        })
    return found


def slot_of_name(name):
    """Partition naam se slot: 'a' | 'b' | None (pure)."""
    low = (name or "").lower()
    if low.endswith("_a"):
        return "a"
    if low.endswith("_b"):
        return "b"
    return None


def base_name(name):
    """Slot suffix hata kar asal naam (pure)."""
    low = (name or "")
    if low.lower().endswith(("_a", "_b")):
        return low[:-2]
    return low


# ---------------------------------------------------------------------------
# debugfs driving (Cygwin e2fsprogs)
# ---------------------------------------------------------------------------

def find_debugfs(tool_dir=DEBUGFS_DIR):
    """(debugfs, e2fsck) paths ya (None, None)."""
    dbg = Path(tool_dir) / "debugfs.exe"
    fsck = Path(tool_dir) / "e2fsck.exe"
    if dbg.is_file():
        return dbg, (fsck if fsck.is_file() else None)
    # Linux smoke tests ke liye system tools fallback
    sys_dbg = shutil.which("debugfs")
    if sys_dbg:
        return Path(sys_dbg), (shutil.which("e2fsck") or None)
    return None, None


def dbg_ls(debugfs, img, dirpath, timeout=60):
    """debugfs ls -p -> [{name, is_dir}] ya None (jawab na aya /
    folder nahi hai). `ls -p` format: /inode/mode/uid/gid/name//"""
    out, _code = _run_capture(
        [debugfs, "-R", f"ls -p {dirpath}", _win_path(img)],
        timeout=timeout)
    entries = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("/"):
            continue
        fields = line.split("/")
        # ['', inode, mode, uid, gid, naam, '', '']
        if len(fields) < 6:
            continue
        name = fields[5]
        mode = fields[2]
        if name in (".", "..", ""):
            continue
        entries.append({"name": name,
                        "is_dir": mode.startswith("04")})
    if not entries and ("no such" in out.lower()
                         or "not a directory" in out.lower()):
        return None
    return entries


def collect_tree(debugfs, img, dirpath, max_depth=4, max_items=400):
    """Recursive listing: (files, dirs) — dono image-absolute paths.
    dirs me dirpath khud shamil NAHI. (debugfs read-only)"""
    files, dirs = [], []
    stack = [(dirpath, 0)]
    seen = 0
    while stack:
        current, depth = stack.pop()
        entries = dbg_ls(debugfs, img, current)
        if entries is None:
            continue
        for ent in entries:
            seen += 1
            if seen > max_items:
                return files, dirs
            child = current.rstrip("/") + "/" + ent["name"]
            if ent["is_dir"]:
                dirs.append(child)
                if depth + 1 < max_depth:
                    stack.append((child, depth + 1))
            else:
                files.append(child)
    return files, dirs


def scan_partition_apps(debugfs, img):
    """Standard app roots scan: [{root, name, is_dir}] — har woh
    entry jo kisi app root ke seedha andar hai."""
    found = []
    for root in APP_ROOTS:
        entries = dbg_ls(debugfs, img, "/" + root)
        if not entries:
            continue
        for ent in entries:
            found.append({"root": root, "name": ent["name"],
                          "is_dir": ent["is_dir"],
                          "path": "/" + root + "/" + ent["name"]})
    return found


def remove_path_tree(debugfs, img, target, timeout=300):
    """target (folder ya file) ko debugfs -w se recursive hatao.
    Return: (removed_count, errors list).
    Pehle read-only enumeration, phir aik -f script: files pehle,
    folders gehrai ke ultay tartib me (pehle andar wale)."""
    files, dirs = [], []
    entries = dbg_ls(debugfs, img, target)
    if entries is None:
        # Folder nahi — seedhi file ho sakti hai
        files = [target]
    else:
        dirs.append(target)
        sub_files, sub_dirs = collect_tree(debugfs, img, target)
        files = sub_files
        dirs.extend(sub_dirs)
    cmds = []
    for f in sorted(files):
        cmds.append(f"rm {f}")
    for d in sorted(dirs, key=lambda p: -p.count("/")):
        cmds.append(f"rmdir {d}")
    if not cmds:
        return 0, ["koi file/folder nahi mila"]
    script = Path(img).with_suffix(".dbgcmds.txt")
    try:
        script.write_text("\n".join(cmds) + "\n", encoding="utf-8")
        out, _code = _run_capture(
            [debugfs, "-w", "-f", _win_path(script), _win_path(img)],
            timeout=timeout)
    finally:
        try:
            script.unlink()
        except Exception:  # noqa: BLE001
            pass
    errors = []
    for line in (out or "").splitlines():
        low = line.lower()
        if "error" in low or "not empty" in low or "no such" in low:
            errors.append(line.strip())
    return len(cmds), errors


def verify_removed(debugfs, img, target):
    """Removal ke baad target asal me gaya? stat se check (pure-ish)."""
    out, _ = _run_capture([debugfs, "-R", f"stat {target}",
                           _win_path(img)], timeout=60)
    low = (out or "").lower()
    return "file not found" in low or "no such file" in low or \
        "does not exist" in low or not out.strip()


def fsck_repair(e2fsck, img, timeout=600):
    """e2fsck -y -f: debugfs rm ke baad block bitmap ki chhoti
    na-ahamkhwani (hataye hue file ka block bitmap me reh jana)
    durust karo. (True/False, aakhri lines). Exit 0/1/2 qabool
    (0 = saaf tha, 1/2 = ghaltiyan durust huin)."""
    if e2fsck is None:
        return False, "e2fsck nahi mila"
    out, code = _run_capture(
        [e2fsck, "-y", "-f", _win_path(img)], timeout=timeout)
    tail = "\n".join((out or "").splitlines()[-6:])
    return code in (0, 1, 2), tail


def fsck_clean(e2fsck, img, timeout=600):
    """e2fsck -n: (True/False, aakhri output lines)."""
    if e2fsck is None:
        return False, "e2fsck nahi mila"
    out, code = _run_capture(
        [e2fsck, "-n", "-f", _win_path(img)], timeout=timeout)
    tail = "\n".join((out or "").splitlines()[-6:])
    return code == 0, tail


# ---------------------------------------------------------------------------
# Input (firmware) talaash — inbox / extracted folders
# ---------------------------------------------------------------------------

def _find_super_in_zip(ctx, zip_path, work_dir):
    """ZIP ke andar super.img member -> sirf wahi extract karo.
    (super_path, member_name) ya (None, None)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            member = None
            for name in zf.namelist():
                low = name.replace("\\", "/").lower()
                if low == "super.img" or low.endswith("/super.img"):
                    member = name
                    break
            if member is None:
                return None, None
            target = Path(work_dir) / "super-from-zip.img"
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
            ctx.log(f"super.img ZIP se nikali gayi ({member}): "
                    f"{target.stat().st_size:,} bytes", "INFO")
            return target, member
    except Exception as e:  # noqa: BLE001
        ctx.log(f"ZIP se super.img nahi nikal saki: {e}", "ERROR")
        return None, None


def find_input_super(ctx, work_dir):
    """(super_path, stem, note) ya (None, None, None).

    Tartib: 1) firmware-inbox ki seedhi super*.img,
    2) inbox ki ZIP ke andar super.img,
    3) tools/firmware/<stem>/ extracted folders me super.img."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = [p for p in INBOX_DIR.iterdir() if p.is_file()] \
        if INBOX_DIR.is_dir() else []
    direct = [p for p in files if p.name.lower().startswith("super")
              and p.suffix.lower() == ".img"]
    if direct:
        src = _newest(direct)
        ctx.log(f"super image mili (inbox): {src}", "INFO")
        return src, src.stem, "inbox-file"
    zips = [p for p in files if p.suffix.lower() == ".zip"]
    if zips:
        src_zip = _newest(zips)
        ctx.log(f"Inbox me ZIP mili: {src_zip.name} — andar super.img "
                "dhoondhi ja rahi hai...", "INFO")
        sp, _member = _find_super_in_zip(ctx, src_zip, work_dir)
        if sp is not None:
            return sp, src_zip.stem, "inbox-zip"
    if FW_DIR.is_dir():
        supers = sorted(FW_DIR.rglob("super.img"),
                        key=lambda p: str(p).lower())
        if supers:
            src = _newest(supers)
            ctx.log(f"super image extracted firmware folder me mili: "
                    f"{src}", "INFO")
            return src, src.parent.name, "firmware-folder"
    return None, None, None


def _detect_slot_from_params(ctx):
    """ctx.params se slot ('a'/'b') ya None (pure-ish)."""
    try:
        raw = str((ctx.params or {}).get("slot") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return None
    return raw if raw in ("a", "b") else None


def _detect_slot_from_device(ctx):
    """Phone FASTBOOT mode me laga ho to asal current-slot parho —
    warna None. (resolve_fastboot ke ERROR logs se bachne ke liye
    seedha engines + getvar helpers.)"""
    dev = getattr(ctx, "device", None)
    if not dev or getattr(dev, "mode", "") != "FASTBOOT":
        return None
    try:
        from core import engines
        from ops.fastboot_frp import getvar_all, parse_getvar
        fb = engines.find_platform_tool("fastboot")
        if not fb:
            return None
        data = parse_getvar(getvar_all(fb, dev.serial))
        slot = (data.get("current-slot") or "").strip().lower()
        return slot if slot in ("a", "b") else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(ctx) -> bool:
    # --- 0) BRICK warning + danger gate — SAB SE PEHLE --------------
    ctx.log("=" * 72, "WARN")
    ctx.log(BRICK_WARNING, "WARN")
    ctx.log("=" * 72, "WARN")
    if not danger_gate(ctx, "TRANSSION SUPER PATCH (ROM-level debloat/"
                            "MDM — patched super banana)"):
        return False

    work_root = OUT_BASE / "_work"
    try:
        work_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Work folder nahi ban saka: {e}", "ERROR")
        return False

    # --- 1) Tooling check -------------------------------------------
    if not LPUNPACK_PY.is_file():
        ctx.log("lpunpack.py nahi mila — engines/lptools/ folder "
                "maujood nahi ya adhoora hai.", "ERROR")
        ctx.log("Guide: ENGINES package dobara download karke app ke "
                "saath extract karo taake engines/lptools/ aa jaye "
                "(provenance: engines/lptools/SOURCE.md).", "WARN")
        return False
    try:
        lp = load_lpunpack()
    except Exception as e:  # noqa: BLE001
        ctx.log(f"lpunpack.py load nahi ho saka: {e}", "ERROR")
        return False
    debugfs, e2fsck = find_debugfs()
    if debugfs is None:
        ctx.log("debugfs nahi mila — engines/lptools/debugfs/ setup "
                "nahi hai. Baghair debugfs ke ext4 partitions ke "
                "andar se packages NAHI nikale ja sakte.", "ERROR")
        ctx.log("Guide: ENGINES package dobara extract karo; "
                "provenance engines/lptools/SOURCE.md me hai.",
                "WARN")
        return False
    ctx.log(f"lpunpack.py tayyar hai; debugfs: {debugfs}", "INFO")

    # --- 2) Input super ---------------------------------------------
    ctx.progress(10, "Firmware ki super.img dhoondhi ja rahi hai...")
    super_src, stem, _note = find_input_super(ctx, work_root)
    if super_src is None:
        ctx.log("Kahin super.img nahi mili (firmware-inbox me file/"
                "ZIP, na extracted firmware folder me).", "ERROR")
        ctx.log(f"Guide: stock firmware ki super.img (ya super wali "
                f"ZIP) is folder me rakho: {INBOX_DIR} — ya 'Firmware "
                f"Archive Kholo' op se firmware pehle extract karo. "
                f"Phir ye op dobara chalao.", "WARN")
        return False
    stem = stem or "firmware"

    # --- 3) Sparse -> raw (working copy; asal ko haath nahi) --------
    raw_super = work_root / f"{stem}-super-raw.img"
    if is_sparse(super_src):
        ctx.log("Super SPARSE hai — raw me badla ja raha hai "
                "(working copy par)...", "INFO")
        ctx.progress(16, "Sparse super raw ho raha hai...")
        try:
            size = sparse_to_raw(super_src, raw_super)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Sparse -> raw nakam: {e}", "ERROR")
            return False
        ctx.log(f"Raw super tayyar: {size:,} bytes", "INFO")
    else:
        ctx.log("Super raw hai — working copy ban rahi hai...", "INFO")
        ctx.progress(16, "Super ki working copy ban rahi hai...")
        shutil.copyfile(super_src, raw_super)

    # --- 4) Metadata + partitions ki fehrist -------------------------
    ctx.progress(22, "Super ki metadata parhi ja rahi hai...")
    try:
        md, parts = read_super_metadata(lp, raw_super)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Super ki LP metadata parhi nahi ja saki: {e}",
                "ERROR")
        ctx.log("File shayad super.img nahi hai ya kharab/adhoori "
                "hai — asal stock firmware ki super.img istemal "
                "karo.", "WARN")
        return False
    if not parts:
        ctx.log("Metadata me koi logical partition nahi mila.",
                "ERROR")
        return False
    geo = md.geometry
    ctx.log(f"LP metadata: version "
            f"{md.header.major_version}.{md.header.minor_version}, "
            f"metadata slots {geo.metadata_slot_count}, logical "
            f"block {geo.logical_block_size} bytes", "INFO")
    ctx.log(f"{len(parts)} logical partitions mileen:", "OK")
    for p in parts:
        ctx.log(f"  {p['name']}  ({p['size']:,} bytes, group: "
                f"{p['group'] or '-'})", "DATA")

    # --- 5) Slot chuno -----------------------------------------------
    slot = _detect_slot_from_params(ctx)
    slot_note = "params se"
    if slot is None:
        slot = _detect_slot_from_device(ctx)
        slot_note = "phone ke fastboot current-slot se"
    if slot is None:
        slot = "b"
        slot_note = ("asal slot maloom nahi ho saka — reference "
                     "tool ki tarah default Slot B")
    ctx.log(f"Chuna hua slot: {slot.upper()} ({slot_note}). Super "
            f"isi slot ke partitions ke liye patch hoga.", "INFO")

    in_slot = [p for p in parts
               if slot_of_name(p["name"]) in (slot, None)]
    other_slot = [p for p in parts
                  if slot_of_name(p["name"]) not in (slot, None)]
    if other_slot:
        ctx.log(f"Note: {len(other_slot)} partitions doosre slot ki "
                f"hain — wo bilkul nahi chhoo'i jayengi: "
                + ", ".join(p["name"] for p in other_slot), "INFO")

    # --- 6) Patch list + scan ----------------------------------------
    patch_list = load_patch_list()
    if not patch_list.get("groups"):
        ctx.log(f"Patch list nahi mili ya khali hai: "
                f"{PATCH_LIST_FILE} — candidates ke baghair aage "
                "barhna bekaar hai.", "ERROR")
        return False
    total_entries = sum(len(g.get("entries", []))
                        for g in patch_list["groups"])
    ctx.log(f"Patch list: {total_entries} documented packages "
            f"({len(patch_list['groups'])} groups) — "
            f"{PATCH_LIST_FILE.name}", "INFO")

    extract_dir = work_root / "parts"
    extract_dir.mkdir(parents=True, exist_ok=True)

    all_candidates = []   # {part_name, path, name, package,...}
    fs_notes = []
    scan_targets = [p for p in in_slot
                    if base_name(p["name"]).lower() in APP_PARTITIONS]
    if not scan_targets:
        ctx.log("Is slot me koi app-wali partition (system/product/"
                "vendor waghera) nahi mili — patch ka koi maqsad "
                "nahi.", "ERROR")
        return False

    ctx.progress(35, "Partitions scan ho rahe hain (candidates)...")
    for part in scan_targets:
        if ctx.is_cancelled():
            return False
        img = extract_dir / (part["name"] + ".img")
        try:
            extract_partition(raw_super, part["extents"], img)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"{part['name']}: extract nakam: {e}", "WARN")
            continue
        fs = detect_fs(img)
        if fs != "ext4":
            fs_notes.append((part["name"], fs))
            ctx.log(f"{part['name']}: filesystem '{fs}' hai — is par "
                    f"package removal NAHI hoga (sirf ext4 par "
                    f"debugfs kaam karta hai; erofs/f2fs ke liye "
                    f"rebuild tooling bundle me nahi hai).", "WARN")
            continue
        if ext4_shared_blocks(img):
            fs_notes.append((part["name"], "ext4+shared_blocks"))
            ctx.log(f"{part['name']}: ext4 shared_blocks wali image "
                    f"hai — vendored e2fsprogs 1.44.5 isay edit "
                    f"nahi kar sakta, ye partition chhod di gayi.",
                    "WARN")
            continue
        apps = scan_partition_apps(debugfs, img)
        names = [a["name"] for a in apps]
        matches = match_candidates(names, patch_list)
        by_name = {a["name"]: a for a in apps}
        for m in matches:
            app = by_name.get(m["name"])
            if app is None:
                continue
            all_candidates.append({
                "part": part, "img": img, "path": app["path"],
                "is_dir": app["is_dir"], "name": m["name"],
                "package": m["package"], "label": m["label"],
                "group": m["group"], "caution": m["caution"],
            })
        ctx.log(f"{part['name']}: {len(apps)} app entries scan "
                f"huin, {len(matches)} candidates mile.", "INFO")

    if not all_candidates:
        ctx.log("Kisi partition me patch-list ka koi candidate nahi "
                "mila — patched super banane ka koi faida nahi, "
                "is liye yahin ruk rahe hain (ye nakami nahi, is "
                "firmware me wo packages hi nahi hain).", "WARN")
        ctx.log("Note: candidate pehchan sirf DOCUMENTED packages "
                "ke tokens se hoti hai. Koi naya package maloom ho "
                "to tools/transsion-patch-list.json me entry jor "
                "do.", "INFO")
        return False

    # --- 7) Candidates ki fehrist — TASDEEQ se pehle poori ----------
    ctx.log("=" * 72, "WARN")
    ctx.log(f"YE {len(all_candidates)} CANDIDATES NIKALE JAYENGE "
            f"(slot {slot.upper()}):", "WARN")
    for i, c in enumerate(all_candidates, 1):
        ctx.log(f"  {i}. [{c['group']}] {c['path']}  "
                f"(partition: {c['part']['name']}) — package: "
                f"{c['package'] or '?'} ({c['label']})", "DATA")
        if c["caution"]:
            ctx.log(f"     ⚠️ {c['caution']}", "WARN")
    ctx.log("Candidate = token match par andesha — confirmed "
            "plugin hona lazmi nahi. Fehrist gaur se parho: koi "
            "cheez galat lagti ho to STOP kar do aur patch-list "
            "theek karke dobara chalao. Aage barhna = in sab ki "
            "removal ki tasdeeq.", "WARN")
    ctx.log("=" * 72, "WARN")

    # --- 8) Removal (har partition: copy -> debugfs -> e2fsck) -------
    ctx.progress(55, "Candidates nikale ja rahe hain...")
    removed, failed = [], []
    edited_parts = {}   # part name -> (part, edited_img)
    by_part = {}
    for c in all_candidates:
        by_part.setdefault(c["part"]["name"], []).append(c)

    for part_name, clist in by_part.items():
        if ctx.is_cancelled():
            return False
        part = clist[0]["part"]
        orig_img = clist[0]["img"]
        work_img = extract_dir / (part_name + "-edited.img")
        shutil.copyfile(orig_img, work_img)
        part_failed = False
        for c in clist:
            count, errors = remove_path_tree(debugfs, work_img,
                                             c["path"])
            if errors:
                ctx.log(f"{c['path']}: removal me errors: "
                        + "; ".join(errors[:3]), "WARN")
            if verify_removed(debugfs, work_img, c["path"]):
                removed.append(c)
                ctx.log(f"✓ {c['path']} hata diya gaya "
                        f"({count} entries).", "OK")
            else:
                part_failed = True
                failed.append(c)
                ctx.log(f"✗ {c['path']} removal confirm NAHI hua — "
                        f"ye partition ki edit RADD kar di jayegi.",
                        "ERROR")
        if part_failed:
            try:
                work_img.unlink()
            except Exception:  # noqa: BLE001
                pass
            continue
        rep_ok, rep_tail = fsck_repair(e2fsck, work_img)
        if not rep_ok:
            ctx.log(f"{part_name}: e2fsck repair step nakam — edit "
                    f"shuda copy RADD. e2fsck aakhar:\n{rep_tail}",
                    "ERROR")
            try:
                work_img.unlink()
            except Exception:  # noqa: BLE001
                pass
            for c in clist:
                if c in removed:
                    removed.remove(c)
                    failed.append(c)
            continue
        ok, tail = fsck_clean(e2fsck, work_img)
        if not ok:
            ctx.log(f"{part_name}: e2fsck -n verify FAIL — edit "
                    f"shuda copy RADD. e2fsck aakhar:\n{tail}",
                    "ERROR")
            try:
                work_img.unlink()
            except Exception:  # noqa: BLE001
                pass
            for c in clist:
                if c in removed:
                    removed.remove(c)
                    failed.append(c)
            continue
        ctx.log(f"{part_name}: e2fsck verify saaf — edit qabool.",
                "OK")
        edited_parts[part_name] = (part, work_img)

    if not removed or not edited_parts:
        ctx.log("Aik bhi candidate mehfooz tareeqe se nahi nikal "
                "saka — patched super NAHI banaya gaya.", "ERROR")
        return False

    # --- 9) In-place repack ------------------------------------------
    ctx.progress(80, "Patched super band ho raha hai...")
    out_dir = OUT_BASE / f"{stem}-slot{slot}"
    out_dir.mkdir(parents=True, exist_ok=True)
    patched_super = out_dir / f"super_patched_{slot}.img"
    shutil.copyfile(raw_super, patched_super)
    size_before = patched_super.stat().st_size
    for part_name, (part, work_img) in edited_parts.items():
        try:
            write_partition_back(patched_super, part["extents"],
                                 work_img)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"{part_name}: repack nakam: {e}", "ERROR")
            return False
        ctx.log(f"{part_name}: extents me wapas likh diya gaya.",
                "INFO")

    # --- 10) Output verify: patched super dobara parho ---------------
    ctx.progress(90, "Patched super verify ho raha hai...")
    try:
        _md2, parts2 = read_super_metadata(lp, patched_super)
        names2 = {p["name"] for p in parts2}
        if names2 != {p["name"] for p in parts}:
            ctx.log("Verify: patched super ki partition fehrist asal "
                    "se mukhtalif hai — output RADD.", "ERROR")
            return False
        # Edit hui partitions nikaal kar candidates dobara dhoondho
        verify_dir = work_root / "verify"
        verify_dir.mkdir(parents=True, exist_ok=True)
        still_there = []
        for part_name, (part, _w) in edited_parts.items():
            vimg = verify_dir / (part_name + ".img")
            extract_partition(patched_super, part["extents"], vimg)
            apps = scan_partition_apps(debugfs, vimg)
            names = [a["name"] for a in apps]
            for m in match_candidates(names, patch_list):
                if any(c["part"]["name"] == part_name
                       and c["name"] == m["name"]
                       for c in removed):
                    still_there.append(f"{part_name}:{m['name']}")
        if still_there:
            ctx.log("Verify: ye candidates patched super me AB BHI "
                    "hain: " + ", ".join(still_there), "ERROR")
            return False
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Patched super verify nahi ho saka: {e}", "ERROR")
        return False
    ctx.log("Verify mukammal: metadata saaf, removed candidates "
            "patched super me nahi hain.", "OK")

    # --- 11) Summary --------------------------------------------------
    size_after = patched_super.stat().st_size
    removed_bytes_note = ("size waisa hi hai (in-place repack me "
                          "super ka size nahi badalta; andar ki "
                          "khali jagah device par rehti hai)")
    summary_lines = [
        "MEER Tool Pro — Transsion ROM Patcher summary",
        f"Firmware: {stem}   Slot: {slot.upper()} ({slot_note})",
        f"Input super: {super_src}",
        f"Output: {patched_super}",
        f"Super size: {size_before:,} bytes ({removed_bytes_note})",
        "",
        f"Removed candidates ({len(removed)}):",
        *[f"  - [{c['group']}] {c['path']} (package: "
          f"{c['package'] or '?'})" for c in removed],
    ]
    if failed:
        summary_lines += ["",
                          f"Removal nakam / radd ({len(failed)}):",
                          *[f"  - {c['path']}" for c in failed]]
    if fs_notes:
        summary_lines += ["",
                          "Chhod di gayi partitions (filesystem):",
                          *[f"  - {n}: {f}" for n, f in fs_notes]]
    summary_path = out_dir / "patch-summary.txt"
    try:
        summary_path.write_text("\n".join(summary_lines) + "\n",
                                encoding="utf-8")
    except Exception:  # noqa: BLE001
        summary_path = None

    ctx.log(f"PATCHED SUPER TAYYAR: {patched_super} "
            f"({size_after:,} bytes)", "OK")
    if summary_path:
        ctx.log(f"Summary file: {summary_path}", "INFO")
    ctx.log("Flash rehnumai: ye super is tool ke maujooda flash "
            "raston se lagega — MTK: BROM/SP Flash wale flash op me "
            "super partition ki jagah ye file do; Fastboot: "
            f"'fastboot flash super super_patched_{slot}.img'. "
            "Flash se pehle asal firmware ka backup mehfooz rakho.",
            "INFO")
    ctx.log(BRICK_WARNING, "WARN")
    if failed:
        ctx.log(f"Note: {len(failed)} candidates nakam/radd hue — "
                f"natija juzvi (partial) hai; fehrist summary me "
                f"hai.", "WARN")
        return False
    ctx.progress(95, "Patched super tayyar + verify shuda")
    return True
