"""
util_update_check.py — Update Center (Phase 3 mukammal).

Pehle SERVER (Supabase app_releases) se sab se nayi release
parhta hai — version, notes, download URL aur SHA-256 ke
saath. Is ke liye login session chahiye (RLS: sirf logged-in
user parh sakta hai). Server/session na mile to purana
GitHub Releases check fallback ke tor par chalta hai.

SHA-256 verify: downloaded file ka hash server wale hash
se mila kar MATCH / MISMATCH batata hai (ctx.params me
"verify_file" + "verify_sha256" mile to run() ke andar hi;
GUI ka button isi module ke sha256_file() ko istemal karta
hai).

Natija usool:
  - Check mukammal ho jaye (naya version ho ya na ho,
    verify MATCH ho) -> SUCCESS.
  - Dono raste fail, ya verify MISMATCH -> FAIL saaf wajah
    ke saath.
"""

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

OP = {
    "id": "util_update_check",
    "category": "Utility",
    "name": "Update Check (Server + GitHub)",
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


def is_newer(latest_tag, current=CURRENT_VERSION) -> bool:
    """latest > current ho to True (lambai barabar karke)."""
    latest = parse_version(latest_tag)
    cur = parse_version(current)
    width = max(len(latest), len(cur))
    return (latest + (0,) * (width - len(latest))
            > cur + (0,) * (width - len(cur)))


def sha256_file(path) -> str:
    """File ki SHA-256 (bare files ke liye chunked read)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def _report_release(ctx, tag, notes, url, sha256, source) -> None:
    """Release ki maloomat + version muqabla log me."""
    if is_newer(tag):
        ctx.log(f"NAYA version maujood hai: {tag} "
                f"(maujooda: v{CURRENT_VERSION}) — zariya: "
                f"{source}", "OK")
    else:
        ctx.log(f"Aap latest version par hain (v{CURRENT_VERSION}"
                + (f", {source} par latest: {tag}" if tag else "")
                + ").", "OK")
    if notes:
        ctx.log(f"Release notes: {notes}", "INFO")
    if url:
        ctx.log(f"Download: {url}", "OK")
    if sha256:
        ctx.log(f"SHA-256 (server par darj): {sha256}", "INFO")
        ctx.log("Download ke baad file ki SHA-256 is se mila "
                "kar verify karo — UTILITY module ke 'UPDATE "
                "FILE VERIFY' button se.", "INFO")
    if is_newer(tag):
        ctx.log("Note: naya version download karke EXE replace "
                "karo; tools/ folder mehfooz rahega — wahan "
                "user ke loaders/backups hain, use mat cherna.",
                "INFO")


def _server_latest(ctx):
    """Server se latest release — (row|None, note).

    Session na ho to (None, 'no-session'); server fail ho to
    exception ServerError/ServerOffline (caller fallback
    karta hai).
    """
    from core import server

    sess = server.load_session()
    if not sess or not sess.get("access_token"):
        return None, "no-session"
    client = server.SupabaseClient.from_config()
    try:
        row = client.latest_release(sess["access_token"])
    except server.ServerError as e:
        if e.status in (401, 403) and sess.get("refresh_token"):
            auth = client.refresh(sess["refresh_token"])
            sess = server.session_from_auth(auth, old=sess)
            server.save_session(sess)
            row = client.latest_release(sess["access_token"])
        else:
            raise
    return row, "ok"


def _github_check(ctx) -> bool:
    """Purana GitHub Releases check (fallback)."""
    ctx.log("GitHub Releases se latest version check ho raha "
            "hai...", "INFO")
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

    _report_release(ctx, tag, str(data.get("body") or "")[:400],
                    url, "", "GitHub")
    return True


def _verify(ctx, path, expected) -> bool:
    """Downloaded file ki SHA-256 mila kar natija."""
    p = Path(path)
    if not p.is_file():
        ctx.log(f"Verify file nahi mili: {path}", "ERROR")
        return False
    ctx.log(f"SHA-256 gin raha hai: {p.name}...", "INFO")
    digest = sha256_file(p)
    ctx.log(f"File ki SHA-256: {digest}", "INFO")
    if expected:
        if digest.lower() == str(expected).strip().lower():
            ctx.log("✅ SHA-256 MATCH — file bilkul sahi hai "
                    "(server wale hash se mil gayi).", "OK")
            return True
        ctx.log("❌ SHA-256 MISMATCH — file server wale hash "
                "se NAHI milti. Download kharab/badli hui ho "
                "sakti hai — dobara download karo, is file ko "
                "istemaal mat karo.", "ERROR")
        return False
    ctx.log("Muqable ke liye server par is release ka SHA-256 "
            "darj nahi hai — sirf file ka hash dikhaya gaya "
            "hai.", "WARN")
    return True


def run(ctx) -> bool:
    ctx.log(f"Maujooda version: v{CURRENT_VERSION}", "INFO")
    ctx.progress(20, "Server se latest release parhi ja rahi hai...")

    row = None
    server_sha = ""
    try:
        row, _note = _server_latest(ctx)
    except Exception as exc:  # noqa: BLE001 — fallback pakka
        ctx.log(f"Server se release nahi mili ({exc}) — "
                "GitHub fallback...", "WARN")
        row = None

    ok = True
    if row:
        server_sha = str(row.get("sha256") or "")
        _report_release(ctx, str(row.get("version") or ""),
                        str(row.get("notes") or ""),
                        str(row.get("url") or ""), server_sha,
                        "Server")
    else:
        ctx.progress(50, "GitHub se check ho raha hai...")
        ok = _github_check(ctx)

    # SHA-256 verify (agar params me file di gayi ho)
    params = getattr(ctx, "params", {}) or {}
    verify_file = params.get("verify_file")
    if verify_file:
        ctx.progress(80, "Downloaded file verify ho rahi hai...")
        expected = params.get("verify_sha256") or server_sha
        ok = _verify(ctx, verify_file, expected) and ok

    if ok:
        ctx.progress(95, "Update check mukammal")
    return ok
