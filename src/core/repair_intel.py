"""
repair_intel.py — Repair Intelligence: error-code / pattern
library + lookup + log-scan ki bunyad.

Data file: `tools/repair-intel.json` — har entry:
  {pattern, code, title, wajah, hal_steps[], source}
  pattern = log ke text par lagne wala regex (case-insensitive);
  kharab regex ho to seedha substring samajh kar lagta hai.

Seed entries ki GROUNDING pakki hai: har entry ka source wahi
hai jahan se pattern asal me liya gaya — vendored engines
(engines/mtkclient, engines/edl, engines/spd_dump) ke apne
error strings/codes, ya public documented SP Flash Tool
error list. Andaze wali entry is library me NAHI jati.

Do istemal:
  1. Lookup — GUI search + util_repair_intel op (title/code/
     pattern par talash).
  2. Log-scan hook — runner har FAIL hue op ke aakhir me us
     ke log ko in patterns se milata hai; match par
     "💡 Repair Intelligence: ..." hint jorta hai. Koi match
     na ho to khamosh rehta hai.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.runner import TOOLS_DIR

INTEL_NAME = "repair-intel.json"
MAX_HINTS = 2


def intel_path(tools_dir=None) -> Path:
    base = Path(tools_dir) if tools_dir is not None else TOOLS_DIR
    return base / INTEL_NAME


def load_entries(tools_dir=None):
    """Entries ki list; file na ho / kharab ho to []."""
    try:
        data = json.loads(intel_path(tools_dir).read_text(
            encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = data.get("entries", [])
    if not isinstance(data, list):
        return []
    out = []
    for e in data:
        if isinstance(e, dict) and e.get("pattern") \
                and e.get("title"):
            out.append({
                "pattern": str(e.get("pattern", "")),
                "code": str(e.get("code", "") or ""),
                "title": str(e.get("title", "")),
                "wajah": str(e.get("wajah", "") or ""),
                "hal_steps": [str(s) for s in
                              e.get("hal_steps", []) or []],
                "source": str(e.get("source", "") or ""),
            })
    return out


def _matches(entry, text) -> bool:
    pat = entry["pattern"]
    try:
        return re.search(pat, text, re.IGNORECASE) is not None
    except re.error:
        return pat.lower() in text.lower()


def match_text(text, tools_dir=None, limit=MAX_HINTS):
    """Log text par lagne wali entries (tartib wahi jo file
    me hai — pehle zyada khaas patterns rakhe gaye hain)."""
    if not text:
        return []
    out = []
    for e in load_entries(tools_dir):
        if _matches(e, text):
            out.append(e)
            if len(out) >= limit:
                break
    return out


def search(query, tools_dir=None):
    """Lookup: query code/title/wajah/pattern me dhoondo."""
    q = str(query or "").strip().lower()
    entries = load_entries(tools_dir)
    if not q:
        return entries
    out = []
    for e in entries:
        hay = " ".join([e["code"], e["title"], e["wajah"],
                        e["pattern"]]).lower()
        if q in hay:
            out.append(e)
    return out


def hint_line(entry) -> str:
    """Runner ke log ke liye aik-line hint."""
    parts = [f"💡 Repair Intelligence: {entry['title']}"]
    if entry["code"]:
        parts.append(f"[{entry['code']}]")
    line = " ".join(parts)
    if entry["wajah"]:
        line += f" — Wajah: {entry['wajah']}"
    if entry["hal_steps"]:
        line += " Hal: " + " → ".join(entry["hal_steps"][:3])
    return line
