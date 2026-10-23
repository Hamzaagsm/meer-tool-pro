"""
server.py — MEER Tool Pro ka server hissa (Suite Phase 3, Supabase).

Design (SERVER-EDITION-BRIEF.md + supabase-setup.sql ka contract):
  - Server sirf MANAGEMENT / SYNC hai: login (Supabase Auth),
    trial check (server ke time par — trial_status() RPC),
    dukaan backup (shop_backup), update khabar (app_releases).
  - SURVIVAL RULE: customer/repair records ki ASAL jagah LOCAL
    SQLite (tools/shop.db) hi hai. Server na mile to dukaan
    ka kaam nahi rukta — pehle se verify shuda session par
    OFFLINE mode me andar jane ki ijazat hai.
  - App me koi SECRET nahi: sirf project URL + PUBLISHABLE key
    (tools/server-config.json) — ye key design se hi public
    hai (har copy me jati hai; asal taale RLS policies +
    har user ka apna login hain). service_role key aur
    database password app me KABHI nahi ate.

Transport: sirf Python stdlib (urllib). Tests ke liye
transport inject ho sakta hai:
    transport(method, url, headers, json_body) -> (status, data)
    data = parsed JSON (dict/list) ya None.
    Network fail par transport ServerOffline raise karta hai.

Session: tools/session.json (runtime file — shop.db ki tarah
EXE ke saath; pehle run par khud banti hai, package me nahi
jati). Us me access/refresh token + aakhri verify shuda
trial status rehta hai (offline mode ki buniyad).
Test hook: MEER_SESSION_FILE / MEER_SERVER_CONFIG env overrides.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from core.runner import TOOLS_DIR

TIMEOUT = 10  # seconds — har server call ki had


# ------------------------------------------------------------- errors ----
class ServerOffline(Exception):
    """Server tak pahuncha hi nahi (internet/network/timeout)."""


class ServerError(Exception):
    """Server ne jawab diya lekin error wala (HTTP >= 400)."""

    def __init__(self, message, status=None, code=""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code or ""

    def __str__(self):
        return self.message


# ------------------------------------------------------------- config ----
# CONFIG PIN (anti-crack): trial ka asal taala server par hai,
# is liye is tool ko crack karne ka sab se asan rasta
# tools/server-config.json ki 'url' badal kar apna nakli local
# server khara karna hota — nakli server hamesha "trial ok"
# kahega. Asli project ka address is liye CODE me bhi pin hai:
# shipped config (default path) ka url is se na mile to server
# features band — ye copy asli nahi mani jayegi.
# MEER_SERVER_CONFIG env override (upar documented test/dev
# hook) par pin lagu NAHI hota; OFFLINE mode (tasdeeq shuda
# session + asli config) bilkul pehle ki tarah chalta hai.
EXPECTED_PROJECT_URL = "https://kcowjfrdeissgotsmljj.supabase.co"

CONFIG_PIN_MESSAGE = (
    "Server config badli hui hai — ye copy asli nahi hai. "
    "Tool ki asli copy download karo; is copy par server "
    "login/trial band hai.")


def config_pin_error(url, from_override=False):
    """Pin mismatch par CONFIG_PIN_MESSAGE, warna None (pure).

    Sirf HOST compare hota hai (scheme/path ki chhoti
    tabdeeli par nakli alarm nahi)."""
    if from_override:
        return None
    host = urllib.parse.urlparse(str(url or "")).netloc.lower()
    expected = urllib.parse.urlparse(
        EXPECTED_PROJECT_URL).netloc.lower()
    if host != expected:
        return CONFIG_PIN_MESSAGE
    return None


def config_path() -> Path:
    override = os.environ.get("MEER_SERVER_CONFIG", "").strip()
    if override:
        return Path(override)
    return TOOLS_DIR / "server-config.json"


def load_config() -> dict:
    """{url, publishable_key} — file na ho ya kharab ho to ServerError."""
    p = config_path()
    if not p.is_file():
        raise ServerError(
            "Server config nahi mili (tools/server-config.json) — "
            "tool ki mukammal copy download karo.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        url = str(data.get("url") or "").rstrip("/")
        key = str(data.get("publishable_key") or "")
        if not url or not key:
            raise ValueError("url/publishable_key khaali hai")
        pin_err = config_pin_error(
            url, from_override=bool(
                os.environ.get("MEER_SERVER_CONFIG", "").strip()))
        if pin_err:
            raise ServerError(pin_err, code="config_pin")
        return {"url": url, "publishable_key": key}
    except ServerError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ServerError(f"Server config kharab hai: {e}")


# ---------------------------------------------------------- transport ----
def _default_transport(method, url, headers, json_body):
    """Asal transport (urllib). (status, parsed_json|None) wapas.

    HTTP error par ServerError NAHI uthata — status wapas karta
    hai taake client jawab ke code/message ko saaf parh sake.
    Network fail par ServerOffline.
    """
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _parse_json(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, _parse_json(raw)
    except Exception as e:  # noqa: BLE001 — timeout/URLError waghera
        raise ServerOffline(f"Server se rabta nahi ho saka: {e}")


def _parse_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _error_from(status, data):
    """Supabase ke error jawab se saaf ServerError banao."""
    msg = ""
    code = ""
    if isinstance(data, dict):
        code = str(data.get("code") or data.get("error") or "")
        msg = str(data.get("message") or data.get("error_description")
                  or data.get("msg") or "")
    if not msg:
        msg = f"Server error (HTTP {status})"
    return ServerError(msg, status=status, code=code)


# ------------------------------------------------------------- client ----
class SupabaseClient:
    """Chhota sa Supabase client — Auth + PostgREST + RPC."""

    def __init__(self, url, publishable_key, transport=None):
        self.url = str(url).rstrip("/")
        self.key = publishable_key
        self.transport = transport or _default_transport

    @classmethod
    def from_config(cls, transport=None):
        cfg = load_config()
        return cls(cfg["url"], cfg["publishable_key"],
                   transport=transport)

    # -- low level --
    def _call(self, method, path, token=None, body=None,
              extra_headers=None):
        headers = {"apikey": self.key}
        headers["Authorization"] = f"Bearer {token or self.key}"
        if extra_headers:
            headers.update(extra_headers)
        status, data = self.transport(
            method, self.url + path, headers, body)
        if status >= 400:
            raise _error_from(status, data)
        return data

    # -- auth --
    def health(self):
        """Server zinda hai ya nahi (auth health — public)."""
        return self._call("GET", "/auth/v1/health")

    def signup(self, email, password):
        """POST /auth/v1/signup — jawab me session ho bhi sakta
        hai aur nahi bhi (email confirmation ON ho to sirf user
        ata hai, session nahi)."""
        return self._call("POST", "/auth/v1/signup",
                          body={"email": email, "password": password})

    def login(self, email, password):
        """POST /auth/v1/token?grant_type=password — session dict."""
        return self._call(
            "POST", "/auth/v1/token?grant_type=password",
            body={"email": email, "password": password})

    def refresh(self, refresh_token):
        """POST /auth/v1/token?grant_type=refresh_token."""
        return self._call(
            "POST", "/auth/v1/token?grant_type=refresh_token",
            body={"refresh_token": refresh_token})

    def logout(self, access_token):
        """POST /auth/v1/logout — best effort (fail khamosh)."""
        try:
            self._call("POST", "/auth/v1/logout", token=access_token)
        except Exception:  # noqa: BLE001
            pass

    def me(self, access_token):
        """GET /auth/v1/user — login user ki maloomat."""
        return self._call("GET", "/auth/v1/user", token=access_token)

    # -- data (PostgREST) --
    def trial_status(self, access_token):
        """POST /rest/v1/rpc/trial_status — SERVER time par trial
        ka faisla: {ok, role, days_left, reason...}."""
        return self._call("POST", "/rest/v1/rpc/trial_status",
                          token=access_token, body={})

    def get_settings(self, access_token):
        """app_settings -> {key: value} dict."""
        rows = self._call(
            "GET", "/rest/v1/app_settings?select=key,value",
            token=access_token) or []
        return {str(r.get("key")): str(r.get("value"))
                for r in rows if isinstance(r, dict)}

    def update_setting(self, access_token, key, value):
        """Admin: aik setting badlo (UPDATE policy ke tehet)."""
        q = urllib.parse.urlencode({"key": f"eq.{key}"})
        return self._call("PATCH", f"/rest/v1/app_settings?{q}",
                          token=access_token,
                          body={"value": str(value)})

    def list_profiles(self, access_token):
        """Admin: tamam profiles (RLS gair-admin ko sirf apni
        row deti hai)."""
        return self._call(
            "GET",
            "/rest/v1/profiles?select=id,email,role,blocked,"
            "trial_days_override,created_at&order=created_at.asc",
            token=access_token) or []

    def my_profile(self, access_token, user_id):
        rows = self._call(
            "GET",
            "/rest/v1/profiles?select=id,email,role,blocked,"
            "trial_days_override,created_at"
            f"&id=eq.{urllib.parse.quote(str(user_id))}",
            token=access_token) or []
        return rows[0] if rows else None

    def update_profile(self, access_token, user_id, patch):
        """Admin: profile ke fields badlo (blocked / override)."""
        q = urllib.parse.urlencode({"id": f"eq.{user_id}"})
        return self._call("PATCH", f"/rest/v1/profiles?{q}",
                          token=access_token, body=dict(patch))

    def upsert_backup(self, access_token, user_id, payload):
        """Dukaan ka poora JSON backup server par (aik row/user)."""
        body = {
            "user_id": user_id,
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._call(
            "POST", "/rest/v1/shop_backup", token=access_token,
            body=body,
            extra_headers={
                "Prefer": "resolution=merge-duplicates,"
                          "return=minimal"})

    def get_backup(self, access_token, user_id):
        """Apna server backup — {user_id, payload, updated_at}
        ya None (kabhi backup nahi liya)."""
        q = urllib.parse.urlencode({"user_id": f"eq.{user_id}"})
        rows = self._call(
            "GET",
            f"/rest/v1/shop_backup?select=user_id,payload,"
            f"updated_at&{q}",
            token=access_token) or []
        return rows[0] if rows else None

    def latest_release(self, access_token):
        """app_releases ki sab se nayi row ya None."""
        rows = self._call(
            "GET",
            "/rest/v1/app_releases?select=id,version,notes,url,"
            "sha256,created_at&order=created_at.desc&limit=1",
            token=access_token) or []
        return rows[0] if rows else None


# ------------------------------------------------------------ session ----
def session_path() -> Path:
    override = os.environ.get("MEER_SESSION_FILE", "").strip()
    if override:
        return Path(override)
    return TOOLS_DIR / "session.json"


def load_session():
    p = session_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("refresh_token"):
            return data
    except Exception:  # noqa: BLE001
        pass
    return None


def save_session(sess: dict) -> Path:
    p = session_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sess, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def clear_session():
    try:
        session_path().unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def session_from_auth(auth: dict, old: dict | None = None) -> dict:
    """Auth jawab (login/refresh) se session dict banao —
    purani last_status/last_state mehfooz rehti hai."""
    user = auth.get("user") or {}
    sess = dict(old or {})
    sess.update({
        "access_token": auth.get("access_token", ""),
        "refresh_token": auth.get("refresh_token", ""),
        "token_type": auth.get("token_type", "bearer"),
        "expires_at": time.time() + float(auth.get("expires_in")
                                          or 3600),
        "user_id": user.get("id") or sess.get("user_id", ""),
        "email": user.get("email") or sess.get("email", ""),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    })
    return sess


def _setup_pending(err: ServerError) -> bool:
    """Server jawab de raha hai lekin database setup (SQL)
    abhi nahi hua — tables/function maujood nahi."""
    if err.status in (404, 406):
        return True
    return (err.code or "").startswith("PGRST") or \
        "Could not find" in (err.message or "")


# -------------------------------------------------------- access gate ----
class AccessResult:
    """Startup gate ka natija.

    state: ok_user | ok_admin | offline_ok | login |
           locked_blocked | locked_expired | locked_setup
    """

    def __init__(self, state, message="", status=None, session=None,
                 offline=False):
        self.state = state
        self.message = message
        self.status = status or {}
        self.session = session
        self.offline = offline

    @property
    def allowed(self):
        return self.state in ("ok_user", "ok_admin", "offline_ok")

    @property
    def is_admin(self):
        if self.state == "ok_admin":
            return True
        if self.state == "offline_ok":
            return (self.status or {}).get("role") == "admin"
        return False

    def __repr__(self):
        return f"AccessResult({self.state!r})"


def evaluate_access(client: SupabaseClient) -> AccessResult:
    """App start par gate ka faisla. Network sirf yahin hota
    hai (GUI isay thread me chalati hai).

    Usool:
      - Session nahi -> LOGIN (pehli dafa offline ho tab bhi
        login lazmi hai — saaf message ke saath).
      - Session hai + server mila -> refresh + trial_status
        (SERVER time) hi asal faisla hai.
      - Session hai + server NAHI mila + pichli tasdeeq ok
        thi -> OFFLINE mode (survival rule: dukaan na ruke).
      - trial_status na chal sake (SQL setup baqi) ->
        locked_setup, nakli andar-jana nahi.
    """
    sess = load_session()
    if not sess:
        offline = False
        try:
            client.health()
        except ServerOffline:
            offline = True
        except Exception:  # noqa: BLE001
            pass
        msg = ("Internet nahi hai aur is PC par pehle koi login "
               "nahi hua — pehla login online lazmi hai."
               if offline else
               "Login ke liye apna email aur password likhen.")
        return AccessResult("login", msg, session=None,
                            offline=offline)

    # Session hai: token taza karo (server se rabta bhi sabit hoga)
    try:
        auth = client.refresh(sess["refresh_token"])
        if auth and auth.get("access_token"):
            sess = session_from_auth(auth, old=sess)
            save_session(sess)
    except ServerOffline:
        last = sess.get("last_status") or {}
        if last.get("ok"):
            return AccessResult(
                "offline_ok",
                "Internet nahi — OFFLINE mode. Aakhri server "
                "tasdeeq ke mutabiq andar jane ki ijazat hai; "
                "dukaan ka kaam local chalta rahega.",
                status=last, session=sess, offline=True)
        return AccessResult(
            "login",
            "Internet nahi hai aur is session ki server tasdeeq "
            "kabhi mukammal nahi hui — online login lazmi hai.",
            session=None, offline=True)
    except ServerError as e:
        # Refresh token hi mar gaya (logout/revoke/password change)
        if e.status in (400, 401, 403):
            clear_session()
            return AccessResult(
                "login",
                "Purani login khatam ho chuki hai — dobara "
                "login karo.", session=None)
        raise

    # Asal trial faisla — SERVER ke time par
    try:
        status = client.trial_status(sess["access_token"])
    except ServerOffline:
        last = sess.get("last_status") or {}
        if last.get("ok"):
            return AccessResult(
                "offline_ok",
                "Internet kat gaya — OFFLINE mode (aakhri "
                "tasdeeq par).", status=last, session=sess,
                offline=True)
        return AccessResult(
            "login",
            "Server se trial check nahi ho saka aur purani "
            "tasdeeq bhi nahi — online login lazmi hai.",
            session=None, offline=True)
    except ServerError as e:
        if _setup_pending(e):
            return AccessResult(
                "locked_setup",
                "Server tayyar hai lekin database setup (SQL) "
                "abhi baqi hai — admin ko batao ke setup mukammal "
                "kare. Tab tak servicing band hai; dukaan ke "
                "records neeche wale button se khul sakte hain.",
                session=sess)
        return AccessResult(
            "locked_setup",
            f"Server ne trial check par jawab diya: {e.message}",
            session=sess)

    if not isinstance(status, dict):
        return AccessResult(
            "locked_setup",
            "Server ka trial jawab samajh nahi aya.",
            session=sess)
    sess["last_status"] = status
    save_session(sess)
    if status.get("ok"):
        if status.get("role") == "admin":
            return AccessResult("ok_admin", "Admin account.",
                                status=status, session=sess)
        return AccessResult("ok_user", "Trial jaari hai.",
                            status=status, session=sess)
    reason = status.get("reason")
    if reason == "blocked":
        return AccessResult(
            "locked_blocked",
            "Aap ka account band hai — rabta karen.",
            status=status, session=sess)
    if reason == "trial_expired":
        return AccessResult(
            "locked_expired",
            "Trial khatam ho gaya hai — rabta karen.",
            status=status, session=sess)
    if reason == "no_profile":
        return AccessResult(
            "locked_setup",
            "Account ka profile server par nahi bana — "
            "database setup (SQL) baqi lagta hai. Admin ko batao.",
            status=status, session=sess)
    return AccessResult(
        "locked_setup",
        f"Server jawab: {status}", status=status, session=sess)


def friendly_auth_error(err: Exception) -> str:
    """Login/Signup ki aam ghaltiyon ke saaf jumle."""
    if isinstance(err, ServerOffline):
        return ("Internet nahi hai — pehla login online lazmi "
                "hai. Connection check karke dobara try karo.")
    if isinstance(err, ServerError) and err.code == "config_pin":
        return err.message
    if isinstance(err, ServerError):
        low = (err.message or "").lower()
        if "invalid login credentials" in low:
            return "Email ya password ghalat hai."
        if "already registered" in low or "already exists" in low:
            return ("Ye email pehle se registered hai — Login "
                    "karo.")
        if "email not confirmed" in low:
            return ("Email abhi confirm nahi hua — inbox me aya "
                    "Supabase ka link kholo, phir Login karo.")
        if "password" in low and ("weak" in low or "short" in low
                                   or "characters" in low):
            return ("Password kamzor/chhota hai — kam az kam 6 "
                    "characters ka rakho.")
        if "rate limit" in low or err.status == 429:
            return "Bohat zyada koshishen — kuch dair baad try karo."
        return f"Server: {err.message}"
    return str(err)


__all__ = [
    "ServerOffline", "ServerError", "SupabaseClient",
    "load_config", "config_path", "config_pin_error",
    "EXPECTED_PROJECT_URL", "CONFIG_PIN_MESSAGE",
    "session_path", "load_session", "save_session",
    "clear_session", "session_from_auth",
    "AccessResult", "evaluate_access", "friendly_auth_error",
    "TIMEOUT",
]
