"""
meta_patch.py — META FT partition read/write + per-model
patch-data framework (Round 7, B3 ki bunyad; B2 bhi yahi
istemal karta hai).

SEPT-SEC-RESEARCH §4-B item 3: Security Plugin ki enrollment
state META se pohanch wali NVRAM/proinfo-class storage me hai —
protocol (FT) hamara hai, asal kaam **per-model patch-data
library** hai (offsets/patterns). Ye module wahi library chalata
hai, sakht usoolon ke saath:

  1. Patch-data sirf tools/meta-patch-data.json se ata hai.
     Model library me NA HO to guided STOP — wajah ke saath.
     **Guessed offset par likhne ka koi rasta code me hai hi
     nahi.**
  2. Har patch se pehle GPT compatibility check (core.meta_gpt)
     — partition maujood hi na ho to rukna.
  3. BACKUP-FIRST: jo bytes badle jayenge, un ki ASAL halat
     pehle parh kar backups/meta-patch/ me record (JSON, hex)
     mehfooz hoti hai — record na bane to write NAHI hota.
  4. FIND-PATTERN VERIFY: device par maujood bytes library ke
     'find' pattern se match na hon to STOP (firmware mukhtalif
     hai — is data ka is phone par istemal khatarnak hota).
  5. WRITE ke baad READ-BACK byte-match — tabhi SUCCESS.
  6. RESTORE: aakhri backup record ke original bytes wapas
     likh kar read-back verify — plugin/MDM ki asal halat
     bilkul waisi hi ho jati hai jaisi patch se pehle thi.

FT partition IO yahin hai (FT_PART_READ / FT_PART_WRITE,
core.meta_session ke round-7 constants): chunked (4 KB), har
jawab status 0x00 verified — warna MetaError / saaf FAIL.

IMAANDARI: FT part read/write ids public FT table ki agli class
se hain; codec software-tested hai lekin in ids ki asal phone
par bench-verification baqi hai (meta_session docstring wala
usool). Aur library is build me jaan-boojh kar kisi model ka
byte-pattern NAHI rakhti — koi public source verified per-model
pattern nahi deta; data Hamza ke apne bench kaam se bharega.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from core import meta_session
from core.runner import BACKUPS_DIR, TOOLS_DIR

PATCH_FILE = TOOLS_DIR / "meta-patch-data.json"
PATCH_BACKUP_DIR = BACKUPS_DIR / "meta-patch"

CHUNK = 4096          # FT frame payload uint16 hai — 4 KB mehfooz chunk
MAX_PART_BYTES = 32 * 1024 * 1024   # is se bari partition yahan nahi parhte


class PatchError(Exception):
    """Patch framework ki har nakami — ops ise saaf FAIL banate hain."""


# --------------------------------------------------------------------------
# FT partition IO (chunked, verified)
# --------------------------------------------------------------------------
def _name_payload(name):
    return str(name).encode("ascii", errors="strict") + b"\x00"


def ft_part_read(session, name, offset, length, timeout=20):
    """Partition ka [offset, offset+length) hissa parho.

    Har chunk ka jawab status 0x00 ke saath verified hota hai;
    kam data / ghalat status / timeout par MetaError — adhoora
    data kabhi wapas nahi jata."""
    if length < 0:
        raise meta_session.MetaError("read length manfi hai.")
    out = bytearray()
    pos = int(offset)
    remaining = int(length)
    while remaining > 0:
        n = min(CHUNK, remaining)
        payload = (_name_payload(name) + pos.to_bytes(4, "little")
                   + n.to_bytes(4, "little"))
        status, data = session.request(meta_session.FT_PART_READ,
                                       payload=payload, timeout=timeout)
        if status != meta_session.FT_STATUS_OK:
            raise meta_session.MetaError(
                f"Partition '{name}' read @{pos}: FT status theek "
                f"nahi (0x{status & 0xFF:02X}) — is firmware par FT "
                "partition read shayad supported nahi.")
        if len(data) < n:
            raise meta_session.MetaError(
                f"Partition '{name}' read @{pos}: {n} bytes mange, "
                f"miley {len(data)} — adhoora data qabool nahi.")
        out += data[:n]
        pos += n
        remaining -= n
    return bytes(out)


def ft_part_read_to_end(session, name, max_bytes=MAX_PART_BYTES,
                        unit=CHUNK):
    """Partition ko aakhir tak parho — jitna verified parha
    gaya wahi wapas (0 bytes bhi mumkin hai: partition na mile
    ya pehli hi request fail ho).

    Usool: ft_part_read adhoora data kabhi nahi deta, is liye
    nakami = us unit se aage partition ka aakhir mana jata hai;
    aakhir ke qareeb 512-byte ki salvage units bhi try hoti
    hain taake ghair-aligned hadd par bhi nuqsan kam ho. GPT
    read (core.meta_gpt) aur full-LK backup (B2) dono yahi
    istemal karte hain — GPT partition aksar 64 KB se chhoti
    hoti hai, exact-length wali parhai wahan nakam hoti."""
    data = bytearray()
    offset = 0
    u = int(unit)
    while len(data) < max_bytes:
        want = min(u, max_bytes - len(data))
        try:
            chunk = ft_part_read(session, name, offset, want)
        except meta_session.MetaError:
            if u > 512:
                u = 512
                continue
            break
        if not chunk:
            break
        data += chunk
        offset += len(chunk)
    return bytes(data)


def ft_part_write(session, name, offset, data, timeout=20):
    """Partition par [offset, ...) data likho — chunked, har
    chunk status 0x00 verified. Nakami par MetaError (jo chunk
    likha gaya wo likha gaya — caller restore ki hidayat dega)."""
    data = bytes(data or b"")
    pos = int(offset)
    idx = 0
    while idx < len(data):
        chunk = data[idx:idx + CHUNK]
        payload = (_name_payload(name) + pos.to_bytes(4, "little")
                   + chunk)
        status, _ = session.request(meta_session.FT_PART_WRITE,
                                    payload=payload, timeout=timeout)
        if status != meta_session.FT_STATUS_OK:
            raise meta_session.MetaError(
                f"Partition '{name}' write @{pos}: FT status "
                f"theek nahi (0x{status & 0xFF:02X}) — write "
                "qabool nahi hua mana jayega.")
        pos += len(chunk)
        idx += len(chunk)
    return True


# --------------------------------------------------------------------------
# Patch-data library
# --------------------------------------------------------------------------
def load_patch_library():
    """tools/meta-patch-data.json parho → dict (na mile/kharab
    ho to khali library — caller guided stop dega)."""
    try:
        data = json.loads(PATCH_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"version": 1, "models": {}}


def _hex_bytes(text, what):
    try:
        return bytes.fromhex(str(text or "").strip())
    except Exception:  # noqa: BLE001
        raise PatchError(f"Patch-data me {what} ki hex durust nahi: "
                         f"{text!r}")


def _validate_patch_entry(model_code, kind, entry):
    """Library entry ki sakht jaanch → normalized dict.
    Kharabi par PatchError (wajah ke saath) — kharab data par
    device ko haath hi nahi lagta."""
    if not isinstance(entry, dict):
        raise PatchError(f"{model_code}/{kind}: entry dict nahi hai.")
    part = str(entry.get("partition", "")).strip()
    if not part or not re.fullmatch(r"[A-Za-z0-9_]+", part):
        raise PatchError(f"{model_code}/{kind}: partition naam "
                         "durust nahi.")
    raw_patches = entry.get("patches")
    if not isinstance(raw_patches, list) or not raw_patches:
        raise PatchError(f"{model_code}/{kind}: patches ki list "
                         "khali hai.")
    patches = []
    for i, p in enumerate(raw_patches):
        if not isinstance(p, dict):
            raise PatchError(f"{model_code}/{kind} patch #{i + 1}: "
                             "dict nahi.")
        offset = p.get("offset")
        if not isinstance(offset, int) or offset < 0:
            raise PatchError(f"{model_code}/{kind} patch #{i + 1}: "
                             "offset durust int nahi.")
        find = _hex_bytes(p.get("find_hex"), f"patch #{i + 1} find")
        repl = _hex_bytes(p.get("replace_hex"),
                          f"patch #{i + 1} replace")
        if not find or len(find) != len(repl):
            raise PatchError(
                f"{model_code}/{kind} patch #{i + 1}: find/replace "
                "hex khali hai ya un ki lambai barabar nahi "
                f"({len(find)} vs {len(repl)}) — barabar lambai "
                "lazmi hai (jagah wohi rehti hai).")
        patches.append({"offset": offset, "find": find,
                        "replace": repl,
                        "note": str(p.get("note", ""))})
    return {"partition": part, "patches": patches,
            "source": str(entry.get("source", ""))}


def patch_entry_for(model_code, kind):
    """(entry|None, wajah|None) — model/kind library me ho aur
    valid ho to normalized entry; na ho to None + saaf wajah."""
    lib = load_patch_library()
    models = lib.get("models", {})
    code = str(model_code or "").strip()
    entry = None
    if code:
        entry = models.get(code) or models.get(code.upper())
    if entry is None:
        return None, (f"Model '{code or '?'}' ka '{kind}' patch-data "
                      "library (tools/meta-patch-data.json) me NAHI "
                      "hai.")
    if not isinstance(entry, dict) or kind not in entry:
        return None, (f"Model '{code}' library me hai lekin us me "
                      f"'{kind}' wala patch-data NAHI hai.")
    try:
        return _validate_patch_entry(code, kind, entry[kind]), None
    except PatchError as e:
        return None, str(e)


def model_code_for(ctx, model=None):
    """Patch-data lookup ki chabi: MDM model ka code, warna
    device ki maloomat (model/detail) me se koi library code
    dhoondh kar. Na mile to '' (caller guided stop dega)."""
    if model and model.get("code"):
        return str(model["code"]).strip()
    dev = getattr(ctx, "device", None)
    if dev is not None:
        hay = " ".join([getattr(dev, "model", "") or "",
                        getattr(dev, "detail", "") or "",
                        getattr(dev, "brand", "") or ""]).upper()
        for code in load_patch_library().get("models", {}):
            if str(code).upper() in hay:
                return str(code)
    return ""


# --------------------------------------------------------------------------
# Backup records (patch se pehle ki asal halat)
# --------------------------------------------------------------------------
def save_backup_record(ctx, model_code, kind, partition, originals,
                       source=""):
    """originals = [(offset, bytes), ...] → JSON record file.
    Returns Path. Nakami par PatchError (backup ke baghair
    write nahi hoga — caller ruk jayega)."""
    try:
        PATCH_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        rec = {
            "model_code": model_code, "kind": kind,
            "partition": partition,
            "when": datetime.now().isoformat(timespec="seconds"),
            "device_serial": getattr(getattr(ctx, "device", None),
                                     "serial", "") or "",
            "source": source,
            "entries": [{"offset": off, "original_hex": data.hex()}
                        for off, data in originals],
        }
        safe = re.sub(r"[^A-Za-z0-9]+", "-", model_code).strip("-")
        path = PATCH_BACKUP_DIR / f"{safe or 'model'}-{kind}-{ts}.json"
        path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        return path
    except PatchError:
        raise
    except Exception as e:  # noqa: BLE001
        raise PatchError(f"Backup record nahi ban saka: {e}")


def latest_backup_record(model_code, kind=None):
    """Model ka sab se taza backup record (dict, path) ya
    (None, None). kind diya ho to sirf usi qisam ka record."""
    if not PATCH_BACKUP_DIR.is_dir():
        return None, None
    safe = re.sub(r"[^A-Za-z0-9]+", "-",
                  str(model_code or "")).strip("-")
    files = sorted(PATCH_BACKUP_DIR.glob("*.json"),
                   key=lambda p: p.stat().st_mtime)
    for path in reversed(files):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if str(rec.get("model_code", "")).upper() != \
                str(model_code or "").upper():
            if safe and not path.name.startswith(safe + "-"):
                continue
            if not safe:
                continue
        if kind and rec.get("kind") != kind:
            continue
        return rec, path
    return None, None
