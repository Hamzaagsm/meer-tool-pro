"""
meta_patch_capture.py — Anti-crack patch-data CAPTURE program
(core — MEER Tool Pro, Round 2 / Group 5).

MAQSAD (research SERVER-REQUIRED-ROUTES-RESEARCH-2.md §8 item 3,
§9 item 7): Transsion Anti-Crack Removal META mode me kaam karta
hai (AUT V200, MDMFixTool v1.0.0.5, BFT V1.7 — sab is ki gawahi
dete hain), lekin AUT ki apni changelog kehti hai us ki anti-crack
removal **server-based aur attempt-limited** hai — matlab META
*entry* local hai, anti-crack *patch data* server-side ho sakta
hai. MEER ke paas aaj **0 models** ka patch data hai
(tools/meta-patch-data.json — models: {}). Ye program us gap ko
bharne ka PEHLA qadam hai: Hamza ke bench par, asal phone se,
per-model META patch bytes CAPTURE karna.

YE PROGRAM SIRF CAPTURE KARTA HAI — READ-ONLY:
  - META session kholo (core.meta_session — maujooda engine).
  - GPT se dekho ke proinfo / prodnv partitions maujood hain ya nahi.
  - Un partitions ko FT_PART_READ se parho (chunked, verified).
  - Bytes + SHA-256 + sidecar record local files me save karo
    (tools/meta-patch-captures/ + tools/meta-patch-data.json
    ki "captures" section).
  - Device ne read refuse kiya to "refused" likho — kabhi fake
    bytes, kabhi guessed offset, kabhi andaze ka patch nahi.

IS ME NAHI HAI (jaan-boojh kar):
  - Koi WRITE nahi — is file me partition likhne wali koi call
    maujood hi nahi (na naam se, na id se); anti-crack removal /
    patch apply ALAG round ka kaam hai, jab patch bytes capture
    ho chuke hon.
  - Koi server upload nahi — data sirf local file me rehta hai.
  - Koi IMEI kaam nahi — proinfo/prodnv read sirf anti-crack
    region capture ke liye hai, IMEI se is ka koi talluq nahi.

IMAANDARI: kaun se bytes "anti-crack patch" hain, ye kisi public
source me documented NAHI hai — is liye capture poori partition
ka snapshot leta hai (hash ke saath), taake baad me bench par
compare karke asal patch region pehchana ja sake. Snapshot khud
koi removal nahi hai aur na hi ye daawa karta hai.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from core import meta_gpt, meta_patch, meta_session
from core.runner import TOOLS_DIR

# Anti-crack se mutalliq regions — SEPT-SEC-RESEARCH §4-B item 3:
# Security Plugin ki enrollment state META se pohanch wali
# proinfo/NVRAM-class storage me hoti hai. proinfo pehla
# candidate hai; prodnv doosra (NVRAM-class). Dono sirf READ.
CAPTURE_PARTITIONS = ("proinfo", "prodnv")

# Aik partition se zyada se zyada kitna parhna hai (proinfo/prodnv
# chhoti partitions hain; is se bari parhai yahan nahi hoti).
MAX_CAPTURE_BYTES = 8 * 1024 * 1024

CAPTURE_DIR = TOOLS_DIR / "meta-patch-captures"
PATCH_FILE = meta_patch.PATCH_FILE

CAPTURE_STATUSES = ("captured", "refused", "missing")


class CaptureError(Exception):
    """Capture flow / record ki har nakami — op ise saaf FAIL banata hai."""


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def sha256_hex(data) -> str:
    """Bytes ka SHA-256 hex digest (khali data par bhi defined)."""
    return hashlib.sha256(bytes(data or b"")).hexdigest()


def model_slug(text) -> str:
    """Model label -> file-safe slug (khali ho to 'unknown-model')."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-",
                  str(text or "").strip()).strip("-")
    return slug or "unknown-model"


def new_capture_record(model_code, chipset="", model_label="",
                       partitions=None, session_ref="", source=""):
    """Naya capture record (dict) — abhi save NAHI hota.

    partitions: {name: {status, size_bytes, sha256, file, reason}}
    — status "captured" wali entry me sha256 + size_bytes + file
    lazmi hain; "refused"/"missing" wali me reason lazmi hai.
    """
    code = str(model_code or "").strip()
    if not code:
        raise CaptureError("Capture record ke liye model_code chahiye "
                           "(khali nahi ho sakta).")
    parts = {}
    for name, entry in (partitions or {}).items():
        parts[str(name)] = dict(entry or {})
    return {
        "model_code": code,
        "chipset": str(chipset or ""),
        "model_label": str(model_label or ""),
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source or "bench capture (META FT_PART_READ)"),
        "session_log_ref": str(session_ref or ""),
        "kind": "anti_crack_capture",
        "partitions": parts,
    }


def validate_capture_record(rec):
    """Capture record ki sakht jaanch → normalized dict.

    Kharabi par CaptureError (wajah ke saath) — kharab record
    library me kabhi nahi jayega, aur na hi us par bharosa hoga.
    """
    if not isinstance(rec, dict):
        raise CaptureError("Capture record dict nahi hai.")
    code = str(rec.get("model_code", "") or "").strip()
    if not code:
        raise CaptureError("Capture record me model_code khali hai.")
    if str(rec.get("kind", "")) != "anti_crack_capture":
        raise CaptureError(
            f"Capture record ka kind 'anti_crack_capture' hona "
            f"chahiye, mila: {rec.get('kind')!r}.")
    if not str(rec.get("captured_at", "") or "").strip():
        raise CaptureError("Capture record me captured_at khali hai.")
    parts = rec.get("partitions")
    if not isinstance(parts, dict) or not parts:
        raise CaptureError("Capture record me partitions khali hain.")
    out_parts = {}
    for name, entry in parts.items():
        if not isinstance(entry, dict):
            raise CaptureError(f"Partition '{name}': entry dict nahi hai.")
        status = str(entry.get("status", "") or "")
        if status not in CAPTURE_STATUSES:
            raise CaptureError(
                f"Partition '{name}': status '{status}' durust nahi "
                f"(captured / refused / missing me se hona chahiye).")
        norm = {"status": status,
                "reason": str(entry.get("reason", "") or "")}
        if status == "captured":
            digest = str(entry.get("sha256", "") or "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise CaptureError(
                    f"Partition '{name}': captured hai lekin sha256 "
                    f"durust 64-hex nahi hai.")
            size = entry.get("size_bytes")
            if not isinstance(size, int) or size <= 0:
                raise CaptureError(
                    f"Partition '{name}': captured hai lekin "
                    f"size_bytes durust positive int nahi hai.")
            fname = str(entry.get("file", "") or "")
            if not fname:
                raise CaptureError(
                    f"Partition '{name}': captured hai lekin file "
                    f"ka naam khali hai.")
            norm.update({"sha256": digest, "size_bytes": size,
                         "file": fname})
        else:
            if not norm["reason"]:
                raise CaptureError(
                    f"Partition '{name}': status '{status}' hai "
                    f"lekin reason khali hai — kyun nahi capture "
                    f"hua, ye likhna lazmi hai.")
        out_parts[str(name)] = norm
    return {"model_code": code,
            "chipset": str(rec.get("chipset", "") or ""),
            "model_label": str(rec.get("model_label", "") or ""),
            "captured_at": str(rec.get("captured_at", "")),
            "source": str(rec.get("source", "") or ""),
            "session_log_ref": str(rec.get("session_log_ref", "") or ""),
            "kind": "anti_crack_capture",
            "partitions": out_parts}


def verify_capture_bytes(entry, data) -> tuple:
    """Captured bytes ki tasdeeq — record ka sha256 dobara gino.

    Returns (True, "match") ya (False, wajah). Entry "captured"
    na ho to (False, wajah) — us par verify ka sawal hi nahi."""
    if not isinstance(entry, dict) or entry.get("status") != "captured":
        return False, "entry 'captured' nahi hai — verify nahi ho sakta"
    want = str(entry.get("sha256", "") or "").lower()
    got = sha256_hex(data)
    if got != want:
        return False, (f"sha256 mismatch — record me {want[:16]}…, "
                       f"dobara gina {got[:16]}…")
    size = entry.get("size_bytes")
    if isinstance(size, int) and len(bytes(data or b"")) != size:
        return False, (f"size mismatch — record me {size} bytes, "
                       f"mile {len(bytes(data or b''))}")
    return True, "match"


# --------------------------------------------------------------------------
# Library IO (tools/meta-patch-data.json ki "captures" section)
# --------------------------------------------------------------------------
def load_capture_library(patch_file=None):
    """Poori patch-data file parho (models + captures samet).

    Na mile/kharab ho to khali library — caller guided stop dega.
    Maujooda "models" section ko ye function kabhi nahi chheerta.
    """
    path = Path(patch_file) if patch_file else PATCH_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"version": 1, "models": {}, "captures": {}}


def save_capture_record(record, patch_file=None):
    """Validated capture record library ki "captures" section me
    save karo (per-model latest wins; .bin files + sidecar hi
    tareekh mehfooz rakhte hain). Returns Path.

    "models" section bilkul waisi hi rehti hai jaisi thi — ye
    function usay parhta bhi nahi, badalta bhi nahi (sirf
    dobara likhte waqt waisi hi wapas likhta hai).
    """
    rec = validate_capture_record(record)
    path = Path(patch_file) if patch_file else PATCH_FILE
    lib = load_capture_library(path)
    captures = lib.get("captures")
    if not isinstance(captures, dict):
        captures = {}
    captures[rec["model_code"]] = rec
    lib["captures"] = captures
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(lib, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        raise CaptureError(f"Capture record library me nahi likh "
                           f"saka ({path}): {e}")
    return path


def capture_for(model_code, patch_file=None):
    """(record|None, wajah|None) — model ka capture record ho to
    validated record, na ho to None + saaf wajah."""
    lib = load_capture_library(patch_file)
    captures = lib.get("captures", {})
    code = str(model_code or "").strip()
    entry = None
    if code:
        entry = captures.get(code) or captures.get(code.upper())
    if entry is None:
        return None, (f"Model '{code or '?'}' ka anti-crack capture "
                      "record library me NAHI hai — pehle capture "
                      "program chalao.")
    try:
        return validate_capture_record(entry), None
    except CaptureError as e:
        return None, str(e)


# --------------------------------------------------------------------------
# Session capture (READ-ONLY — yahan koi write call maujood nahi)
# --------------------------------------------------------------------------
def capture_partition(session, name, gpt_names=None,
                      max_bytes=MAX_CAPTURE_BYTES):
    """Aik partition ka snapshot → (entry_dict, data|None).

    - GPT me naam na ho → status "missing" (parhne ki koshish
      hi nahi — partition hai hi nahi).
    - FT read khali / status kharab / timeout → status "refused"
      (device ne mana kar diya — wajah ke saath, fake data nahi).
    - Verified read → status "captured" (sha256 + size).
    """
    if gpt_names is not None and name not in gpt_names:
        return {"status": "missing",
                "reason": f"GPT me partition '{name}' maujood nahi."}, None
    try:
        data = meta_patch.ft_part_read_to_end(session, name,
                                              max_bytes=max_bytes)
    except meta_session.MetaError as e:
        return {"status": "refused",
                "reason": f"FT part-read nakam: {e}"}, None
    except Exception as e:  # noqa: BLE001
        return {"status": "refused",
                "reason": f"FT part-read ghalti: {e}"}, None
    if not data:
        return {"status": "refused",
                "reason": f"FT part-read se 0 bytes mile — is "
                          f"firmware par '{name}' ka FT read "
                          f"supported nahi lagta (ya partition "
                          f"khali hai)."}, None
    return {"status": "captured",
            "sha256": sha256_hex(data),
            "size_bytes": len(data),
            "file": "",
            "reason": ""}, bytes(data)


def save_capture_files(model_code, captured, capture_dir=None):
    """Captured bytes ko .bin files + sidecar JSON me save karo.

    captured: {partition: bytes}. Returns {partition: filename}.
    Koi bhi file write fail ho to CaptureError — adhoora capture
    library me nahi jayega.
    """
    slug = model_slug(model_code)
    base = (Path(capture_dir) / slug) if capture_dir \
        else CAPTURE_DIR / slug
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        raise CaptureError(f"Capture folder nahi ban saka ({base}): {e}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = {}
    for name, data in captured.items():
        fname = f"{ts}-{name}.bin"
        try:
            (base / fname).write_bytes(bytes(data))
            sidecar = {
                "model_code": str(model_code),
                "partition": name,
                "when": datetime.now().isoformat(timespec="seconds"),
                "file": fname,
                "size_bytes": len(bytes(data)),
                "sha256": sha256_hex(data),
                "source": "bench capture (META FT_PART_READ, read-only)",
            }
            (base / f"{ts}-{name}.json").write_text(
                json.dumps(sidecar, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            raise CaptureError(f"Capture file '{fname}' nahi likh "
                               f"saka: {e}")
        saved[name] = fname
    return saved


def run_capture(session, model_code, chipset="", model_label="",
                ctx=None, gpt_names=None, patch_file=None,
                capture_dir=None):
    """Poora capture flow (session pehle se khula hua).

    1. GPT (best-effort — na parha ja sake to presence unknown
       rehti hai aur har partition par read try hoti hai).
    2. Har CAPTURE_PARTITIONS ka snapshot (read-only).
    3. Captured bytes .bin + sidecar me; record library me.
    Returns summary dict {model_code, record, captured_count,
    results}. Kam az kam aik partition captured na ho to
    CaptureError — "kuch nahi mila" ko success nahi kehte.
    """
    code = str(model_code or "").strip()
    if not code:
        raise CaptureError("Capture ke liye model_code chahiye.")
    names = gpt_names
    if names is None and ctx is not None:
        try:
            names, _why = meta_gpt.read_gpt(ctx, session)
        except Exception:  # noqa: BLE001
            names = None
    results = {}
    captured_bytes = {}
    for part in CAPTURE_PARTITIONS:
        entry, data = capture_partition(session, part,
                                        gpt_names=names)
        results[part] = entry
        if entry["status"] == "captured" and data is not None:
            captured_bytes[part] = data
    if not captured_bytes:
        detail = "; ".join(
            f"{p}: {e.get('reason', e.get('status', ''))}"
            for p, e in results.items())
        raise CaptureError(
            "Koi partition capture nahi ho saka — " + detail)
    saved = save_capture_files(code, captured_bytes,
                               capture_dir=capture_dir)
    for part, fname in saved.items():
        results[part]["file"] = fname
    record = new_capture_record(
        code, chipset=chipset, model_label=model_label,
        partitions=results,
        session_ref="META FT session (bench)",
        source="bench capture (META FT_PART_READ, read-only)")
    save_capture_record(record, patch_file=patch_file)
    return {"model_code": code, "record": record,
            "captured_count": len(captured_bytes),
            "results": results}
