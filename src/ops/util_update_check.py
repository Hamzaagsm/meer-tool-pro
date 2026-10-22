"""
util_update_check.py — Update Check (GitHub Releases).

GitHub API se MEER Tool Pro ki latest release parh kar maujooda
version se muqabla karta hai. Ye op sirf PARHTA hai (GET) —
koi download, upload ya tabdeeli nahi hoti.

Natija usool:
  - Check mukammal ho jaye (naya version ho ya na ho) -> SUCCESS.
  - Check khud na chal sake (internet/API/parse error) -> FAIL
    saaf wajah ke saath.
"""

import json
import urllib.error
import urllib.request

OP = {
    "id": "util_update_check",
    "category": "Utility",
    "name": "Update Check (GitHub Releases)",
    "engine": "network",
    "modes": (),
    "server_required": False,
}

CURRENT_VERSION = "1.0.1"

RELEASES_LATEST_URL = (
    "https://api.github.com/repos/Hamzaagsm/meer-tool-pro"
    "/releases/latest")


def parse_version(tag) -> tuple:
    """Version tag -> ints ka tuple (pure function).

    Leading "v" hat-ta hai, "." par split hota hai, jo hissa
    numeric na ho wo 0 banta hai.
    Masalan: "v1.0.1" -> (1, 0, 1); "1.0.1" -> (1, 0, 1);
    "v1.1" -> (1, 1).
    """
    text = str(tag or "").strip()
    if text[:1].lower() == "v":
        text = text[1:]
    parts = []
    for piece in text.split("."):
        piece = piece.strip()
        try:
            parts.append(int(piece))
        except (TypeError, ValueError):
            parts.append(0)
    return tuple(parts)


def run(ctx) -> bool:
    ctx.log(f"Maujooda version: v{CURRENT_VERSION}", "INFO")
    ctx.log("GitHub Releases se latest version check ho raha "
            "hai...", "INFO")
    ctx.progress(30, "Latest release check ho raha hai...")

    req = urllib.request.Request(
        RELEASES_LATEST_URL,
        headers={
            "User-Agent": f"MEERToolPro/{CURRENT_VERSION} "
                          "(update-check)",
            "Accept": "application/vnd.github+json",
        })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"Update check nahi ho saka: {exc}", "ERROR")
        ctx.log("Internet check karo — PC online ho aur GitHub "
                "khul raha ho, phir dobara try karo.", "ERROR")
        return False

    try:
        tag = str(data.get("tag_name") or "").strip()
        url = str(data.get("html_url") or "").strip()
        if not tag:
            raise ValueError("release me tag_name nahi mila")
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"GitHub ka jawab samajh nahi aya: {exc}", "ERROR")
        ctx.log("Internet check karo aur kuch dair baad dobara "
                "try karo.", "ERROR")
        return False

    ctx.progress(80, "Version ka muqabla ho raha hai...")
    latest = parse_version(tag)
    current = parse_version(CURRENT_VERSION)
    # Tuple muqabla lambai barabar karke (masalan (1,1) vs (1,0,1))
    width = max(len(latest), len(current))
    latest_p = latest + (0,) * (width - len(latest))
    current_p = current + (0,) * (width - len(current))

    if latest_p > current_p:
        ctx.log(f"Naya version maujood hai: {tag} "
                f"(maujooda: v{CURRENT_VERSION})", "OK")
        if url:
            ctx.log(f"Release page: {url}", "OK")
        ctx.log("Note: naya version download karke EXE replace "
                "karo; tools/ folder mehfooz rahega — wahan "
                "user ke loaders/backups hain, use mat cherna.",
                "INFO")
    else:
        ctx.log(f"Aap latest version par hain (v{CURRENT_VERSION}"
                + (f", GitHub par latest: {tag}" if tag else "")
                + ").", "OK")
    ctx.progress(95, "Update check mukammal")
    return True
