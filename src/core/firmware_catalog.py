"""
firmware_catalog.py — Firmware Center ka catalogue (records only).

Usool (SERVER-EDITION-BRIEF, pakka):
  - Firmware files yahan HOST **NAHI** hotin — sirf official
    sources ke RECORDS hain: brand/model/code/version/Android/
    size/official link/SHA-256 checksum/note.
  - Data file `tools/firmware-catalog.json` hai — user-editable
    (GUI se bhi, haath se bhi). File na ho to khaali structure
    khud ban jati hai. **Nakli/misaali entries kabhi seed NAHI
    hotin** — data Hamza apne asal kaam se bharta hai.
  - Catalogue source ki rehnumai file ke `about` / `source_note`
    fields me darj hai (Hovatek Stock ROM Forum waghera).
  - Checksum verify: user jo firmware file download kare, us ka
    SHA-256 nikaal kar record wale checksum se milaya jata hai —
    match = file wahi hai jo record kehta hai; mismatch = file
    badli/kharab hai, flash se pehle rukna chahiye.

GUI (main.py ka Firmware Center) aur tests is module ko istemal
karte hain — koi device, koi ctx nahi, sirf filesystem + JSON.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.runner import TOOLS_DIR

CATALOG_NAME = "firmware-catalog.json"

FIELDS = ("brand", "model", "code", "version", "android", "size",
          "official_link", "checksum_sha256", "note")

ABOUT = (
    "Firmware Center ka catalogue — yahan firmware files HOST "
    "NAHI hotin, sirf official sources ke records hain (link + "
    "version + SHA-256 checksum). Asal file hamesha official "
    "source se download karo, phir is Center ke 'Checksum Verify' "
    "se us file ko record ke checksum se mila kar dekho — match "
    "ho tab hi flash ki taraf barho."
)

SOURCE_NOTE = (
    "Catalogue source (records jama karne ki jagah): Hovatek "
    "Stock ROM Forum — Infinix / Tecno / Itel ke model-wise "
    "stock firmware + PAC records: "
    "https://www.hovatek.com/forum/forum-105-page-30.html — "
    "baqi brands ke liye un ki apni official support sites. "
    "Sirf official link darj karo; anjaan download sites ke "
    "links is catalogue me mat dalo (badli hui firmware phone "
    "bhi kharab karti hai aur dukaan ka naam bhi)."
)


def catalog_path(tools_dir=None) -> Path:
    base = Path(tools_dir) if tools_dir is not None else TOOLS_DIR
    return base / CATALOG_NAME


def empty_catalog() -> dict:
    return {"about": ABOUT, "source_note": SOURCE_NOTE, "entries": []}


def load_catalog(tools_dir=None) -> dict:
    """Catalogue parho. File na ho / kharab ho to khaali structure
    (kabhi raise nahi — GUI hamesha khulni chahiye)."""
    path = catalog_path(tools_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return empty_catalog()
    if not isinstance(data, dict):
        return empty_catalog()
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    clean = []
    for e in entries:
        if isinstance(e, dict):
            clean.append({k: str(e.get(k, "") or "") for k in FIELDS})
    return {"about": str(data.get("about") or ABOUT),
            "source_note": str(data.get("source_note") or SOURCE_NOTE),
            "entries": clean}


def save_catalog(catalog, tools_dir=None) -> Path:
    path = catalog_path(tools_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {"about": catalog.get("about") or ABOUT,
           "source_note": catalog.get("source_note") or SOURCE_NOTE,
           "entries": [{k: str(e.get(k, "") or "") for k in FIELDS}
                       for e in catalog.get("entries", [])]}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def ensure_catalog(tools_dir=None) -> dict:
    """File na ho to khaali structure bana kar wapas karo."""
    path = catalog_path(tools_dir)
    if not path.is_file():
        cat = empty_catalog()
        save_catalog(cat, tools_dir)
        return cat
    return load_catalog(tools_dir)


def _clean_entry(entry) -> dict:
    return {k: str((entry or {}).get(k, "") or "").strip()
            for k in FIELDS}


def add_entry(catalog, entry) -> dict:
    """Nayi entry joro. Brand + Model lazmi — warna ValueError."""
    e = _clean_entry(entry)
    if not e["brand"] or not e["model"]:
        raise ValueError("Brand aur Model lazmi hain — pehle wo likho.")
    catalog.setdefault("entries", []).append(e)
    return e


def update_entry(catalog, index, entry) -> dict:
    """index wali entry badlo. Brand + Model lazmi."""
    e = _clean_entry(entry)
    if not e["brand"] or not e["model"]:
        raise ValueError("Brand aur Model lazmi hain — pehle wo likho.")
    catalog["entries"][index] = e
    return e


def search_entries(catalog, query):
    """(index, entry) joray — query brand/model/code/version me
    kahin bhi mile (case-insensitive). Khaali query = tamam."""
    q = str(query or "").strip().lower()
    out = []
    for i, e in enumerate(catalog.get("entries", [])):
        if not q:
            out.append((i, e))
            continue
        hay = " ".join(str(e.get(k, "")) for k in
                       ("brand", "model", "code", "version",
                        "android")).lower()
        if q in hay:
            out.append((i, e))
    return out


def sha256_of_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(entry, file_path):
    """Record ke checksum se asal file milao.

    Return: (status, actual_sha256|None)
      status: "match" | "mismatch" | "no-checksum" | "no-file"
    """
    expected = str((entry or {}).get("checksum_sha256", "") or "") \
        .strip().lower()
    if not expected:
        return "no-checksum", None
    p = Path(file_path)
    if not p.is_file():
        return "no-file", None
    actual = sha256_of_file(p)
    return ("match" if actual.lower() == expected else "mismatch"), actual
