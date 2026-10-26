"""
engine_refresh.py — Vendored engines ki freshness check + upstream
pull routine (core — MEER Tool Pro, Round 2 / Group 5).

MAQSAD (research SERVER-REQUIRED-ROUTES-RESEARCH-2.md §6.5, §9
item 8): MTKClient upstream par stalled lagta tha — lekin
2026-10-25 ko GitHub API se live check par latest release
**v2.1.4.1 (18 Mar 2026)** nikli, jab ke research me likha
V2.0.1 (Dec 2024) ab purana hai. Matlab: vendored copy
(2.1.4) latest release se aik patch peeche hai — routine isi
farq ko pakarti hai. Penumbra ke sirf Rust sources vendored
hain (engines/penumbra/), runnable binary nahi — routine isay
bhi flag karti hai.

ROUTINE KYA KARTI HAI:
  (a) MTKClient upstream version check — vendored (pyproject.toml)
      vs latest GitHub release tag; natija: up_to_date /
      update_available / ahead_of_release / upstream_unreachable.
  (b) DA update check — vendored DA .bin files ki inventory
      (naam + size + sha256) taake upstream se compare ho sake.
  (c) Penumbra build check — runnable binary maujood hai ya nahi;
      cargo maujood hai ya nahi; sources ka version kya hai.
  (d) Refresh action — sirf public upstream repos se; git checkout
      ho to git fetch/pull, warna "manual re-vendor" report.

DRY-RUN DEFAULT HAI: apply_refresh(dry_run=True) sirf report
banata hai, koi file change NAHI karta. Non-dry-run me bhi
routine engine code ko khud replace NAHI karti — sirf
tools/engine-versions.json snapshot likhti hai aur git-pull
(step d) chalati hai jahan checkout maujood ho. Engine code ki
replacement hamesha insan ki nazar se hoti hai (vendored engine
toot jaye to poora tool ruk jata hai).

KOI cracked/leaked source nahi — sirf public GitHub repos:
bkerler/mtkclient aur shomykohai/penumbra. Koi credential,
koi login, koi paid server nahi.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.runner import ENGINES_DIR, TOOLS_DIR

MTKCLIENT_REPO = "bkerler/mtkclient"
PENUMBRA_REPO = "shomykohai/penumbra"
GITHUB_API_LATEST = ("https://api.github.com/repos/{repo}"
                     "/releases/latest")

# Live-verify ki gayi maloomat (2026-10-25, GitHub API):
# MTKClient latest v2.1.4.1 (published 2026-03-18) — research §6.5
# ka "V2.0.1 Dec 2024 latest" is se pehle ka hai, ab purana hai.
# Penumbra latest v2.0.0 (published 2026-10-19).
# Ye values sirf FALLBACK hain (offline hone par) — routine pehle
# hamesha live API se poochti hai.
KNOWN_LATEST = {
    MTKCLIENT_REPO: ("v2.1.4.1", "2026-03-18T19:26:19Z"),
    PENUMBRA_REPO: ("v2.0.0", "2026-10-19T19:12:54Z"),
}

VERSION_FILE = TOOLS_DIR / "engine-versions.json"

# DA .bin files kahan hain (vendored MTKClient ke andar —
# engines/mtkclient/mtkclient/Loader/).
MTKCLIENT_DA_GLOB = "mtkclient/Loader/*.bin"
# User ki apni DA files (agar rakhi hon) — tools/loaders/mtk/.
USER_DA_DIR = TOOLS_DIR / "loaders" / "mtk"

PENUMBRA_BINARIES = (
    "target/release/penumbra",
    "target/release/penumbra.exe",
    "target/debug/penumbra",
    "target/debug/penumbra.exe",
)


class RefreshError(Exception):
    """Refresh routine ki nakami — op ise saaf FAIL banata hai."""


# --------------------------------------------------------------------------
# Version compare (pure)
# --------------------------------------------------------------------------
def parse_version(text):
    """"v2.1.4.1" / "2.1.4" -> (2, 1, 4, 1). Ghalat input par ().
    Sirf numeric components liye jate hain; suffix ("-rc1") nazar-
    andaaz hota hai — release tags ke liye kafi hai."""
    s = str(text or "").strip().lstrip("vV")
    if not s:
        return ()
    parts = []
    for piece in s.split("."):
        m = re.match(r"(\d+)", piece)
        if not m:
            break
        parts.append(int(m.group(1)))
    return tuple(parts)


def compare_versions(a, b) -> int:
    """-1 (a<b) / 0 (barabar) / 1 (a>b). Khaali version = unknown,
    compare nahi ho sakta — (0, wajah) ke liye version_status dekho."""
    pa, pb = parse_version(a), parse_version(b)
    if not pa or not pb:
        raise ValueError(f"Version compare nahi ho saka: {a!r} vs {b!r}")
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))
    pb = pb + (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def version_status(vendored, latest):
    """Vendored vs latest ka faisla (pure):
    up_to_date / update_available / ahead_of_release / unknown."""
    if not str(vendored or "").strip() or not str(latest or "").strip():
        return "unknown"
    try:
        cmp = compare_versions(vendored, latest)
    except ValueError:
        return "unknown"
    if cmp == 0:
        return "up_to_date"
    if cmp < 0:
        return "update_available"
    return "ahead_of_release"


# --------------------------------------------------------------------------
# Vendored state (local files se — koi network nahi)
# --------------------------------------------------------------------------
def _read_version_from_text(text, what):
    m = re.search(r"""^version\s*=\s*["']([^"']+)["']""",
                  text or "", re.MULTILINE)
    if not m:
        raise RefreshError(f"{what} me version nahi mila.")
    return m.group(1).strip()


def vendored_mtkclient_version(engines_dir=None):
    """Vendored MTKClient ka version (pyproject.toml se)."""
    base = Path(engines_dir) if engines_dir else ENGINES_DIR
    pyproject = base / "mtkclient" / "pyproject.toml"
    try:
        return _read_version_from_text(
            pyproject.read_text(encoding="utf-8"),
            "MTKClient pyproject.toml")
    except RefreshError:
        raise
    except Exception as e:  # noqa: BLE001
        raise RefreshError(f"MTKClient version nahi parha ja saka "
                           f"({pyproject}): {e}")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def vendored_da_inventory(engines_dir=None, tools_dir=None):
    """Vendored + user DA .bin files ki inventory.

    Returns [{name, location, size_bytes, sha256}]. Location
    "vendored" ya "user" hai. DA files ki build-date andar ke
    binary me hoti hai (file mtime nahi) — is liye inventory
    size+hash deti hai, taake upstream se compare ho sake.
    """
    base = Path(engines_dir) if engines_dir else ENGINES_DIR
    tools = Path(tools_dir) if tools_dir else TOOLS_DIR
    out = []
    for path in sorted(
            (base / "mtkclient" / "mtkclient").glob("Loader/*.bin")):
        try:
            out.append({"name": path.name, "location": "vendored",
                        "size_bytes": path.stat().st_size,
                        "sha256": _sha256_file(path)})
        except Exception as e:  # noqa: BLE001
            out.append({"name": path.name, "location": "vendored",
                        "size_bytes": -1, "sha256": "",
                        "error": str(e)})
    user_dir = tools / "loaders" / "mtk"
    if user_dir.is_dir():
        for path in sorted(user_dir.glob("*.bin")):
            try:
                out.append({"name": path.name, "location": "user",
                            "size_bytes": path.stat().st_size,
                            "sha256": _sha256_file(path)})
            except Exception as e:  # noqa: BLE001
                out.append({"name": path.name, "location": "user",
                            "size_bytes": -1, "sha256": "",
                            "error": str(e)})
    return out


def penumbra_status(engines_dir=None):
    """Penumbra build check (local):
    {sources_version, binary_present, binary_path, cargo_available,
    cargo_path, note}."""
    base = Path(engines_dir) if engines_dir else ENGINES_DIR
    root = base / "penumbra"
    sources_version = ""
    try:
        cargo_toml = (root / "Cargo.toml").read_text(encoding="utf-8")
        m = re.search(r"""^version\s*=\s*["']([^"']+)["']""",
                      cargo_toml, re.MULTILINE)
        if m:
            sources_version = m.group(1).strip()
    except Exception:  # noqa: BLE001
        pass
    binary_path = ""
    for rel in PENUMBRA_BINARIES:
        cand = root / rel
        if cand.is_file():
            binary_path = str(cand)
            break
    cargo = shutil.which("cargo")
    if binary_path:
        note = f"Runnable binary maujood hai: {binary_path}."
    elif cargo:
        note = ("Runnable binary NAHI hai — sources maujood hain, "
                "cargo maujood hai; 'cargo build --release' se "
                "banaya ja sakta hai (is routine me build NAHI "
                "chalaya jata — lamba kaam hai, alag se chalao).")
    else:
        note = ("Runnable binary NAHI hai aur is machine par cargo "
                "(Rust) bhi nahi mila — penumbra build yahan mumkin "
                "nahi; jis PC par cargo ho wahan 'cargo build "
                "--release' chalana hoga.")
    return {"sources_version": sources_version,
            "binary_present": bool(binary_path),
            "binary_path": binary_path,
            "cargo_available": bool(cargo),
            "cargo_path": cargo or "",
            "note": note}


# --------------------------------------------------------------------------
# Upstream check (public GitHub API — koi auth nahi)
# --------------------------------------------------------------------------
def fetch_latest_release(repo, opener=None):
    """GitHub releases/latest se {tag, published_at} ya
    {"status": "unreachable", "reason": ...}.

    opener: test ke liye injectable callable(url) -> dict
    ({"tag_name": ..., "published_at": ...} ya raise kare).
    Default opener urllib se live API poochta hai (timeout 10s).
    """
    url = GITHUB_API_LATEST.format(repo=repo)
    try:
        if opener is not None:
            data = opener(url)
        else:
            import urllib.request
            req = urllib.request.Request(
                url, headers={"User-Agent": "MEER-Tool-Pro/"
                                            "engine-refresh",
                              "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name", "") or "").strip()
        if not tag:
            raise ValueError("API jawab me tag_name khali hai.")
        return {"status": "ok", "tag": tag,
                "published_at": str(data.get("published_at", "") or ""),
                "url": url}
    except Exception as e:  # noqa: BLE001
        return {"status": "unreachable",
                "reason": f"{type(e).__name__}: {e}", "url": url}


def _upstream_or_known(repo, fetcher):
    """Live check pehle; na mile to KNOWN_LATEST fallback (offline
    note ke saath) — routine kabhi khali haath nahi laut-ti."""
    live = fetch_latest_release(repo, opener=fetcher)
    if live.get("status") == "ok":
        return {"tag": live["tag"],
                "published_at": live.get("published_at", ""),
                "source": "live (api.github.com)",
                "reachable": True}
    known_tag, known_date = KNOWN_LATEST.get(repo, ("", ""))
    return {"tag": known_tag, "published_at": known_date,
            "source": "fallback (last verified "
                      f"{known_date[:10] if known_date else 'unknown'})",
            "reachable": False,
            "unreachable_reason": live.get("reason", "")}


# --------------------------------------------------------------------------
# Report + refresh action
# --------------------------------------------------------------------------
def build_report(engines_dir=None, tools_dir=None, fetcher=None):
    """Poori freshness report (koi file change nahi — pure read)."""
    base = Path(engines_dir) if engines_dir else ENGINES_DIR
    tools = Path(tools_dir) if tools_dir else TOOLS_DIR
    report = {"checked_at": datetime.now().isoformat(timespec="seconds"),
              "mtkclient": {}, "da": {}, "penumbra": {}}

    # (a) MTKClient
    try:
        vendored = vendored_mtkclient_version(base)
        vendored_err = ""
    except RefreshError as e:
        vendored, vendored_err = "", str(e)
    up = _upstream_or_known(MTKCLIENT_REPO, fetcher)
    latest = up["tag"].lstrip("vV")
    status = version_status(vendored, latest) if vendored else "unknown"
    report["mtkclient"] = {
        "vendored_version": vendored,
        "vendored_error": vendored_err,
        "latest_tag": up["tag"],
        "latest_published_at": up["published_at"],
        "upstream_source": up["source"],
        "upstream_reachable": up["reachable"],
        "upstream_unreachable_reason": up.get("unreachable_reason", ""),
        "status": status,
    }

    # (b) DA inventory
    da_files = vendored_da_inventory(base, tools)
    report["da"] = {
        "files": da_files,
        "count": len(da_files),
        "vendored_count": sum(1 for f in da_files
                              if f["location"] == "vendored"),
        "user_count": sum(1 for f in da_files
                          if f["location"] == "user"),
        "total_bytes": sum(f["size_bytes"] for f in da_files
                           if f["size_bytes"] > 0),
        "note": ("DA files ki build-date binary ke andar hoti hai — "
                 "inventory size+sha256 deti hai taake upstream "
                 "MTKClient ke Loader/ se compare ho sake. Koi "
                 "nayee DA sirf upstream MTKClient release ke "
                 "saath ati hai (alag DA download ka koi public "
                 "channel nahi)."),
    }

    # (c) Penumbra
    pen = penumbra_status(base)
    pen_up = _upstream_or_known(PENUMBRA_REPO, fetcher)
    pen_latest = pen_up["tag"].lstrip("vV")
    pen_status = version_status(pen["sources_version"], pen_latest) \
        if pen["sources_version"] else "unknown"
    report["penumbra"] = {
        **pen,
        "latest_tag": pen_up["tag"],
        "latest_published_at": pen_up["published_at"],
        "upstream_source": pen_up["source"],
        "upstream_reachable": pen_up["reachable"],
        "upstream_unreachable_reason": pen_up.get(
            "unreachable_reason", ""),
        # sources_version workspace version hai (0.1.0), release tag
        # (v2.0.0) se compare karna ghalat hoga — is liye status
        # yahan binary par hai, version par nahi.
        "sources_vs_release_status": pen_status,
        "status": ("binary_present" if pen["binary_present"]
                   else "binary_missing"),
    }
    return report


def _git_checkout_present(path):
    return (Path(path) / ".git").is_dir()


def apply_refresh(engines_dir=None, tools_dir=None, fetcher=None,
                  dry_run=True):
    """Refresh routine.

    dry_run=True (DEFAULT): sirf report + planned actions — koi
    file change NAHI (na version file, na engine, na git).
    dry_run=False: tools/engine-versions.json snapshot likhta hai
    + jahan git checkout maujood ho wahan `git fetch` (pull nahi —
    pull merge conflict kar sakta hai; fetch ke baad insan faisla
    kare). Engine code kabhi khud replace nahi hota.
    Returns {dry_run, report, actions, changed_files}.
    """
    base = Path(engines_dir) if engines_dir else ENGINES_DIR
    tools = Path(tools_dir) if tools_dir else TOOLS_DIR
    report = build_report(base, tools, fetcher=fetcher)
    actions = []
    changed = []

    mc = report["mtkclient"]
    if mc["status"] == "update_available":
        actions.append(
            f"MTKClient update available: vendored {mc['vendored_version']} "
            f"< upstream {mc['latest_tag']} — naya MTKClient release "
            f"download karke engines/mtkclient/ dobara vendor karna "
            f"hoga (is routine me auto-replace NAHI hota).")
    elif mc["status"] == "up_to_date":
        actions.append("MTKClient up to date — koi action nahi.")
    elif mc["status"] == "ahead_of_release":
        actions.append(
            f"MTKClient vendored ({mc['vendored_version']}) latest "
            f"release ({mc['latest_tag']}) se AAGE hai — shayad "
            f"master snapshot hai; koi action nahi.")
    else:
        actions.append("MTKClient version compare nahi ho saka — "
                       "vendored ya upstream version maloom nahi.")

    pen = report["penumbra"]
    if pen["status"] == "binary_missing":
        if pen["cargo_available"]:
            actions.append("Penumbra binary missing — cargo maujood "
                           "hai; engines/penumbra/ me 'cargo build "
                           "--release' chalao.")
        else:
            actions.append("Penumbra binary missing aur cargo bhi "
                           "nahi — is PC par build mumkin nahi; jis "
                           "PC par Rust/cargo ho wahan build karo.")
    else:
        actions.append("Penumbra binary maujood hai — koi action nahi.")

    if not dry_run:
        # Sirf version snapshot likho — engine code ko haath nahi.
        version_path = tools / "engine-versions.json"
        try:
            tools.mkdir(parents=True, exist_ok=True)
            version_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8")
            changed.append(str(version_path))
        except Exception as e:  # noqa: BLE001
            raise RefreshError(f"Version snapshot nahi likh saka "
                               f"({version_path}): {e}")
        # Git pull sirf jahan checkout maujood ho (vendored copies
        # me .git NAHI hota — is liye aam tor par skip hoga).
        for name in ("mtkclient", "penumbra"):
            checkout = base / name
            if _git_checkout_present(checkout):
                try:
                    proc = subprocess.run(
                        ["git", "fetch", "--tags", "origin"],
                        cwd=str(checkout), capture_output=True,
                        text=True, timeout=120)
                    if proc.returncode == 0:
                        actions.append(
                            f"{name}: git fetch ho gaya (pull nahi "
                            f"chalaya — merge insan dekhega).")
                        changed.append(f"{name}: git fetch")
                    else:
                        actions.append(
                            f"{name}: git fetch fail "
                            f"({proc.stderr.strip()[:200]}) — manual "
                            f"check karo.")
                except Exception as e:  # noqa: BLE001
                    actions.append(f"{name}: git fetch nahi chal saka "
                                   f"({e}).")
            else:
                actions.append(
                    f"{name}: git checkout nahi hai (vendored copy) "
                    f"— auto-pull mumkin nahi, manual re-vendor hi "
                    f"rasta hai.")
    else:
        actions.append("DRY-RUN: koi file change nahi hui — version "
                       "snapshot bhi nahi likha gaya.")
    return {"dry_run": bool(dry_run), "report": report,
            "actions": actions, "changed_files": changed}
