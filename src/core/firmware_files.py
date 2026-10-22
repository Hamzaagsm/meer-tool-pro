"""
firmware_files.py — Firmware front door ke pure helpers.

ZIP/TGZ scatter archives, OFP/OZIP aur payload.bin wale ops ke
liye mushtarka file pehchan + mehfooz extract logic. Koi GUI,
koi ctx, koi device nahi — sirf filesystem helpers, is liye
alag se test ho sakte hain.

Imaandari / hifazat:
  - detect_kind kabhi raise NAHI karta — kharab / adhoori
    archive par "unknown" wapas aata hai, exception andar hi
    daba di jati hai.
  - safe_extract_* zip-slip / tar-slip se bachate hain: jo
    entry dest ke bahir jaye (../, absolute path, link/device)
    wo SKIP hoti hai, extract kabhi dest se bahir nahi likhta.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def inbox_files(inbox):
    """inbox folder ki files ki sorted list (missing par [])."""
    try:
        folder = Path(inbox)
        if not folder.is_dir():
            return []
        return sorted((p for p in folder.iterdir() if p.is_file()),
                      key=lambda p: p.name.lower())
    except Exception:  # noqa: BLE001
        return []


def _is_scatter_name(name: str) -> bool:
    low = str(name).lower()
    return "scatter" in low and low.endswith(".txt")


def _is_payload_name(name: str) -> bool:
    low = str(name).replace("\\", "/").lower()
    return low == "payload.bin" or low.endswith("/payload.bin")


def detect_kind(path):
    """File ki qism pehchano: extension + andar ka content sniff.

    Return values: "ofp" | "ozip" | "payload-zip" | "zip-scatter"
    | "zip-other" | "tgz-scatter" | "tgz-other" | "payload"
    | "unknown". Kabhi raise nahi karta.
    """
    try:
        p = Path(path)
        name = p.name.lower()
        suffixes = [s.lower() for s in p.suffixes]

        if name.endswith(".ofp"):
            return "ofp"
        if name.endswith(".ozip"):
            return "ozip"

        if name.endswith(".zip"):
            try:
                with zipfile.ZipFile(p) as zf:
                    names = zf.namelist()
            except Exception:  # noqa: BLE001
                return "unknown"
            if any(_is_payload_name(n) for n in names):
                return "payload-zip"
            if any(_is_scatter_name(n) for n in names):
                return "zip-scatter"
            return "zip-other"

        if name.endswith(".tgz") or name.endswith(".tar.gz") or \
                suffixes[-2:] == [".tar", ".gz"]:
            try:
                with tarfile.open(p, "r:*") as tf:
                    names = tf.getnames()
            except Exception:  # noqa: BLE001
                return "unknown"
            if any(_is_scatter_name(n) for n in names):
                return "tgz-scatter"
            return "tgz-other"

        if name == "payload.bin":
            return "payload"

        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _safe_target(dest: Path, member_name: str):
    """dest ke andar ka resolved target ya None (escape par)."""
    dest_resolved = Path(dest).resolve()
    # Absolute / drive wale naam bhi dest ke andar hi ghumao
    clean = str(member_name).replace("\\", "/")
    target = (dest_resolved / clean).resolve()
    try:
        target.relative_to(dest_resolved)
    except ValueError:
        return None
    if target == dest_resolved:
        return None
    return target


def safe_extract_zip(zf, dest):
    """ZipFile ko dest me zip-slip protection ke saath extract karo.

    Jo entry dest se bahir jaye wo skip hoti hai. Return: extracted
    file paths ki list (Path objects).
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    extracted = []
    for info in zf.infolist():
        name = info.filename
        if not name or name.endswith("/") or name.endswith("\\"):
            continue
        target = _safe_target(dest, name)
        if target is None:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(info.filename)
            target.write_bytes(data)
            extracted.append(target)
        except Exception:  # noqa: BLE001
            continue
    return extracted


def safe_extract_tar(tf, dest):
    """TarFile ko dest me tar-slip protection ke saath extract karo.

    Links, devices, fifos waghera skip hote hain; sirf regular
    files (aur un ke parent folders) likhe jate hain. Return:
    extracted file paths ki list.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    extracted = []
    for member in tf.getmembers():
        # Sirf regular files — link/device/fifo kabhi nahi
        if not member.isfile():
            continue
        target = _safe_target(dest, member.name)
        if target is None:
            continue
        try:
            src = tf.extractfile(member)
            if src is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read())
            extracted.append(target)
        except Exception:  # noqa: BLE001
            continue
    return extracted


def find_scatter(folder):
    """folder me recursive scatter .txt dhoondo — Path ya None."""
    try:
        base = Path(folder)
        if not base.is_dir():
            return None
        candidates = sorted(
            (p for p in base.rglob("*")
             if p.is_file() and _is_scatter_name(p.name)),
            key=lambda p: str(p).lower(),
        )
        return candidates[0] if candidates else None
    except Exception:  # noqa: BLE001
        return None
