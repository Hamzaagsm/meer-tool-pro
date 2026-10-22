"""
loader_library.py — Loaders Library: 465 verified loaders ka index,
matching aur import ki bunyad.

Do hisse hain:
  1. **Index** — `tools/loaders-index.json` (app ke saath ata hai):
     har verified loader ki entry {type, brand, key, path, size,
     sha256}. Is ke ilawa `tools/loaders-local-index.json` — user ke
     apne import kiye hue loaders (masalan Hovatek se laye hue DA)
     yahin darj hote hain; dono index aik saath parhe jate hain.
  2. **Files** — asal binaries `tools/loaders/` ke andar rehte hain:
     MTK DA → `tools/loaders/mtk/<Brand>/<file>`,
     firehose → `tools/loaders/qualcomm/<Brand>/<file>`.
     Binaries EXE me bundle NAHI hote — Loaders pack
     (MEERToolPro-Loaders.zip) alag release asset hai jo isi folder
     me extract hota hai.

Matching ka usool: exact chipset token pehle, phir brand ka
AllInOne/generic, phir brand ke baqi loaders, aur sab se aakhir me
doosre brand ka wahi chipset — wo bhi **saaf cross-brand flag** ke
saath (kisi aur brand ka signed loader chup chaap kabhi nahi chunta).

Index maujood ho lekin koi file install na ho to ye module
`not_installed_note()` se saaf wajah deta hai — ops wahi jumla log
karte hain, khaali "fail" kabhi nahi.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from core.runner import TOOLS_DIR

INDEX_NAME = "loaders-index.json"
LOCAL_INDEX_NAME = "loaders-local-index.json"
LIB_SUBDIR = "loaders"

MTK = "mtk-da"
FIREHOSE = "firehose"
# Phase 2 (firmware harvest) ke izafi khane — ye match() ke MTK /
# FIREHOSE raston se BAHIR hain: FDL sirf Unisoc FDL khane ke liye
# record hota hai, preloader/lk sirf harvest ke record ke tor par
# (auto-select inhe DA/firehose samajh kar KABHI nahi chunta —
# match() sirf MTK/FIREHOSE kinds par chalta hai).
FDL = "fdl"
PRELOADER = "preloader"
LK = "lk"

# ---------------------------------------------------------------------------
# Magic bytes (staging ke 465-file corpus se sabit):
#   firehose .elf/.mbn — ELF magic, ya purana MBN header (0x844BDCD1),
#     ya "data ddc" signed-container signature
#   MTK DA — header me "MTK_DOWNLOAD_AGENT", ya DA2 ke \xff\xff /
#     0x0700 headers
# ---------------------------------------------------------------------------
ELF_MAGIC = b"\x7fELF"
MBN_MAGIC = bytes([0xD1, 0xDC, 0x4B, 0x84])          # 0x844BDCD1 (LE)
DDC_MAGIC = b"data ddc"
MTK_DA_STRING = b"MTK_DOWNLOAD_AGENT"
_MAGIC_READ = 262144                                   # pehle 256 KB kafi hain


def _tools(tools_dir=None) -> Path:
    return Path(tools_dir) if tools_dir is not None else TOOLS_DIR


def library_root(tools_dir=None) -> Path:
    return _tools(tools_dir) / LIB_SUBDIR


def index_path(tools_dir=None) -> Path:
    return _tools(tools_dir) / INDEX_NAME


def local_index_path(tools_dir=None) -> Path:
    return _tools(tools_dir) / LOCAL_INDEX_NAME


# ---------------------------------------------------------------------------
# Index parhna
# ---------------------------------------------------------------------------
def _read_entries(path: Path):
    """Index file se entries list; format: {"entries":[...]} ya bare list."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = data.get("entries", [])
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("path")]


def load_index(tools_dir=None):
    """Main index + local (user-imported) index — merged list.

    Har entry me `local` flag: main index = False, local = True.
    Index file hi na ho to khaali list (guided halat).
    """
    tools = _tools(tools_dir)
    merged = []
    for entry in _read_entries(tools / INDEX_NAME):
        e = dict(entry)
        e.setdefault("local", False)
        merged.append(e)
    seen = {e["path"] for e in merged}
    for entry in _read_entries(tools / LOCAL_INDEX_NAME):
        if entry["path"] in seen:
            continue
        e = dict(entry)
        e["local"] = True
        merged.append(e)
    return merged


def entry_abspath(entry, tools_dir=None) -> Path:
    return _tools(tools_dir) / entry["path"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_installed(entry, tools_dir=None) -> bool:
    """File asal jagah par ho AUR size index se match kare."""
    p = entry_abspath(entry, tools_dir)
    try:
        return p.is_file() and p.stat().st_size == int(entry.get("size", -1))
    except Exception:  # noqa: BLE001
        return False


def installed_entries(tools_dir=None, entries=None, kind=None):
    """Sirf wo entries jo asal me disk par (size-verified) mojood hain."""
    if entries is None:
        entries = load_index(tools_dir)
    out = []
    for e in entries:
        if kind and e.get("type") != kind:
            continue
        if is_installed(e, tools_dir):
            out.append(e)
    return out


def library_state(tools_dir=None) -> dict:
    """{index_count, installed_count, mtk_installed, qc_installed, has_index}"""
    tools = _tools(tools_dir)
    entries = load_index(tools)
    inst = installed_entries(tools, entries)
    return {
        "has_index": (tools / INDEX_NAME).is_file(),
        "index_count": len(entries),
        "installed_count": len(inst),
        "mtk_installed": sum(1 for e in inst if e.get("type") == MTK),
        "qc_installed": sum(1 for e in inst if e.get("type") == FIREHOSE),
        "fdl_installed": sum(1 for e in inst if e.get("type") == FDL),
    }


def not_installed_note(tools_dir=None):
    """Library khali/install-na-shuda ho to plain-language wajah, warna None.

    Ops isay bilkul aise hi log karte hain taake user ko pata chale
    ke Loaders pack kahan lagana hai — khaali nakami kabhi nahi.
    """
    st = library_state(tools_dir)
    root = library_root(tools_dir)
    if st["installed_count"] > 0:
        return None
    if st["has_index"] and st["index_count"] > 0:
        return (f"Loaders Library ka index maujood hai ({st['index_count']} "
                f"loaders) lekin aik bhi loader file install NAHI hai — "
                f"Loaders pack (MEERToolPro-Loaders.zip) abhi nahi laga. "
                f"Us zip ko app ke is folder me extract karo: {root} "
                f"(andar mtk/ aur qualcomm/ folders ane chahiye). "
                f"Baghair loaders ke EDL/DA wale ops nahi chal sakte.")
    if not st["has_index"]:
        return (f"Loaders Library ka index hi nahi mila "
                f"({index_path(tools_dir)}) — app ke tools/ folder ki "
                f"copy naqis lagti hai. Aur loaders is folder me hone "
                f"chahiye thay: {root} (Loaders pack "
                f"MEERToolPro-Loaders.zip wahan extract hota hai).")
    return (f"Loader library khali hai — koi loader install nahi. "
            f"Loaders pack (MEERToolPro-Loaders.zip) is folder me "
            f"extract karo: {root}")


# ---------------------------------------------------------------------------
# Magic se side pehchanna (import ke liye)
# ---------------------------------------------------------------------------
def detect_side(path) -> str | None:
    """File ke magic bytes se: "mtk" | "qualcomm" | None (pehchan nahi).

    ELF/MBN wali har file Qualcomm hai; MTK DA apne header string ya
    DA2 headers se pehchana jata hai. Jo file dono me na aye use
    import NAHI karte — andaza laga kar galat khane me dalna is se
    bura hai.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(_MAGIC_READ)
    except Exception:  # noqa: BLE001
        return None
    if head[:4] == ELF_MAGIC or head[:4] == MBN_MAGIC or head[:8] == DDC_MAGIC:
        return "qualcomm"
    if MTK_DA_STRING in head:
        return "mtk"
    if head[:2] == b"\xff\xff":                       # DA2 header
        return "mtk"
    if head[:2] == b"\x07\x00" or head[2:4] == b"\x07\x00":   # 0x0700 header
        return "mtk"
    return None


# ---------------------------------------------------------------------------
# Brand / chipset tokens aur ranking
# ---------------------------------------------------------------------------
_CHIP_RES = [
    re.compile(r"MT\d{4}", re.I),
    re.compile(r"MSM\d{3,4}[A-Z]?", re.I),
    re.compile(r"SM\d{4}[A-Z]?", re.I),
    re.compile(r"SDM\d{3,4}", re.I),
    re.compile(r"8X\d{2}", re.I),                     # MSM8x26 jaisi surat
    re.compile(r"(?<![0-9])(?:89|86|82)\d{2}(?![0-9])"),  # 8909 / 8937 / 8610
]


def chip_tokens(text) -> set:
    """Text se chipset tokens (normalized bare-upper): MT6789, MSM8953..."""
    if not text:
        return set()
    out = set()
    for rx in _CHIP_RES:
        for m in rx.findall(str(text)):
            out.add(m.upper())
    return out


_GENERIC_BRANDS = {"genericchipset", "generic", "mixed", "other", "unknown"}


def _brand_token_set(brand) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(brand or "").lower()) if t}


# Jin brands ke loaders aapas me qareebi khandaan hain (folder naam se hi)
_BRAND_ALIASES = {
    "honor": {"huawei", "honor"},
    "huawei": {"huawei", "honor"},
    "redmi": {"xiaomi", "redmi"},
    "poco": {"xiaomi", "poco"},
    "iqoo": {"vivo", "iqoo"},
    "oneplus": {"oneplus", "oppo", "realme"},
}


def _brand_match(entry_brand, want_brand) -> bool:
    """Entry ka brand folder user ke brand se milta hai ya nahi."""
    want = str(want_brand or "").strip().lower()
    if not want:
        return False
    etoks = _brand_token_set(entry_brand)
    if want in etoks:
        return True
    for alias in _BRAND_ALIASES.get(want, set()):
        if alias in etoks:
            return True
    return False


def _is_generic_entry(entry) -> bool:
    brand_norm = re.sub(r"[^a-z0-9]", "", str(entry.get("brand", "")).lower())
    key = str(entry.get("key", "")).lower()
    name = Path(str(entry.get("path", ""))).name.lower()
    return (brand_norm in _GENERIC_BRANDS or "allinone" in key
            or "allinone" in name or "all_in_one" in name)


def _entry_tokens(entry) -> set:
    return chip_tokens(str(entry.get("key", "")) + " "
                       + Path(str(entry.get("path", ""))).name)


def _rank_key(item):
    """Tier ke andar tartib: verified index pehle, NEW_LOADER pehle,
    phir naam — taake auto-pick har dafa aik jaisa (deterministic) ho."""
    e = item["entry"]
    name = Path(str(e.get("path", ""))).name.lower()
    return (1 if e.get("local") else 0,
            0 if "new_loader" in name else 1,
            name)


def match(kind, brand, chip, tools_dir=None):
    """Ranked candidates — sirf installed entries.

    Har item: {entry, path (Path), tier, why, cross_brand}
      tier 1: brand + chipset exact
      tier 2: chipset + generic/AllInOne (brand-signed nahi), ya
              brand + AllInOne
      tier 3: sirf brand
      tier 4: sirf chipset — DOOSRA brand (cross_brand=True, saaf flag)
    """
    want_tokens = chip_tokens(chip)
    out = []
    for e in installed_entries(tools_dir, kind=kind):
        etoks = _entry_tokens(e)
        chip_hit = bool(want_tokens & etoks) if want_tokens else False
        brand_hit = _brand_match(e.get("brand"), brand)
        generic = _is_generic_entry(e)
        if brand_hit and chip_hit:
            tier, cross = 1, False
            why = (f"{e.get('brand')} + chipset "
                   f"{'/'.join(sorted(want_tokens & etoks))} exact match")
        elif chip_hit and generic:
            tier, cross = 2, False
            why = (f"chipset {'/'.join(sorted(want_tokens & etoks))} "
                   f"generic loader (brand-signed nahi)")
        elif brand_hit and generic:
            tier, cross = 2, False
            why = f"{e.get('brand')} AllInOne/generic (har chipset ke liye)"
        elif brand_hit:
            tier, cross = 3, False
            why = f"{e.get('brand')} brand match (chipset token nahi mila)"
        elif chip_hit:
            tier, cross = 4, True
            why = (f"⚠ CROSS-BRAND: {e.get('brand')} ka loader, chipset "
                   f"{'/'.join(sorted(want_tokens & etoks))} match — "
                   f"doosre brand ka signed loader hai, ehtiyat!")
        else:
            continue
        out.append({"entry": e, "path": entry_abspath(e, tools_dir),
                    "tier": tier, "why": why, "cross_brand": cross})
    out.sort(key=lambda it: (it["tier"], *_rank_key(it)))
    return out


def match_mtk(brand, chip, tools_dir=None):
    return match(MTK, brand, chip, tools_dir)


def match_qc(brand, chip, tools_dir=None):
    return match(FIREHOSE, brand, chip, tools_dir)


# ---------------------------------------------------------------------------
# Import helpers (ops/util_loader_import.py inhe istemal karta hai)
# ---------------------------------------------------------------------------
_KNOWN_BRAND_WORDS = [
    "infinix", "tecno", "itel", "samsung", "xiaomi", "redmi", "poco",
    "oppo", "realme", "oneplus", "vivo", "iqoo", "huawei", "honor",
    "motorola", "lenovo", "nokia", "lava", "doogee", "oukitel",
    "nothing", "zte", "asus", "acer", "blu", "coolpad", "casper",
    "lyf", "generic",
]


def parse_filename_tokens(filename):
    """Filename se (brand_guess, chip_guess) — local index ke liye.

    Brand: pehla known brand lafz (filename ya folder naam se).
    Chip: pehla chipset token. Kuch na mile to (None, None) —
    file phir bhi "Imported" khane me darj hoti hai.
    """
    text = str(filename or "")
    low = text.lower()
    brand = None
    for word in _KNOWN_BRAND_WORDS:
        if word in low:
            brand = "Generic-Chipset" if word == "generic" else word.capitalize()
            break
    toks = chip_tokens(text)
    chip = sorted(toks)[0] if toks else None
    return brand, chip


def find_by_hash(entries, sha256):
    for e in entries:
        if str(e.get("sha256", "")).lower() == str(sha256).lower():
            return e
    return None


def record_local_entry(entry, tools_dir=None) -> None:
    """Local index me entry joro (path par pehle ho to replace)."""
    tools = _tools(tools_dir)
    path = tools / LOCAL_INDEX_NAME
    existing = _read_entries(path)
    existing = [e for e in existing if e.get("path") != entry["path"]]
    clean = {k: entry[k] for k in
             ("type", "brand", "key", "path", "size", "sha256",
              "source")
             if k in entry}
    clean["local"] = True
    existing.append(clean)
    path.write_text(json.dumps({"entries": existing},
                               ensure_ascii=False, indent=1),
                    encoding="utf-8")
