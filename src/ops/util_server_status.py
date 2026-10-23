"""
util_server_status.py — Server / Account Status (Phase 3).

Supabase server tak rabta, maujooda login session, aur trial
ki halat LIVE LOG me dikhata hai. Sirf PARHTA hai — koi
tabdeeli nahi hoti.

Natija usool:
  - Server mila + login hai + trial jawab aya -> SUCCESS.
  - Server nahi mila / login nahi / trial check na ho saka
    -> FAIL saaf wajah ke saath (guided fail).
"""

OP = {
    "id": "util_server_status",
    "category": "Utility",
    "name": "Server / Account Status",
    "engine": "network",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    from core import server

    try:
        client = server.SupabaseClient.from_config()
    except server.ServerError as e:
        ctx.log(f"Server config ka masla: {e.message}", "ERROR")
        return False
    ctx.log(f"Server: {client.url}", "INFO")

    ctx.progress(20, "Server se rabta check ho raha hai...")
    try:
        client.health()
    except server.ServerOffline as e:
        ctx.log(f"Server se rabta nahi ho saka: {e}", "ERROR")
        ctx.log("Internet check karo — dukaan ke local records "
                "baghair server ke bhi chalte hain (CUSTOMERS / "
                "JOBS bilkul local hain).", "WARN")
        return False
    except server.ServerError as e:
        ctx.log(f"Server health jawab: {e.message}", "WARN")
    ctx.log("Server online hai.", "OK")

    sess = server.load_session()
    if not sess:
        ctx.log("Is PC par koi login session nahi hai — tool "
                "start karne par login screen ati hai, wahan "
                "apne account se login karo.", "WARN")
        return False
    ctx.log(f"Login: {sess.get('email') or sess.get('user_id')}",
            "INFO")

    ctx.progress(60, "Trial ki halat server se parhi ja rahi hai...")
    try:
        if sess.get("access_token"):
            try:
                status = client.trial_status(sess["access_token"])
            except server.ServerError as e:
                if e.status in (401, 403) and sess.get("refresh_token"):
                    auth = client.refresh(sess["refresh_token"])
                    sess = server.session_from_auth(auth, old=sess)
                    server.save_session(sess)
                    status = client.trial_status(sess["access_token"])
                else:
                    raise
        else:
            raise server.ServerError("Session me access token nahi")
    except server.ServerOffline as e:
        ctx.log(f"Trial check ke doran rabta kat gaya: {e}", "ERROR")
        last = sess.get("last_status") or {}
        if last:
            ctx.log(f"Aakhri maloom halat: {last}", "WARN")
        return False
    except server.ServerError as e:
        ctx.log(f"Trial check nahi ho saka: {e.message}", "ERROR")
        if e.status in (404,) or (e.code or "").startswith("PGRST"):
            ctx.log("Lagta hai server ka database setup (SQL) "
                    "abhi baqi hai — admin ko batao.", "WARN")
        return False

    if status.get("ok"):
        if status.get("role") == "admin":
            ctx.log("Account: ADMIN — trial ki koi had nahi.", "OK")
        else:
            ctx.log(f"Trial jaari hai — {status.get('days_left')} "
                    f"din baqi (khatam: {status.get('expires_at')}).",
                    "OK")
        sess["last_status"] = status
        server.save_session(sess)
        ctx.progress(95, "Server status mukammal")
        return True
    reason = status.get("reason")
    if reason == "blocked":
        ctx.log("Account BAND hai — admin se rabta karen.", "ERROR")
    elif reason == "trial_expired":
        ctx.log("Trial KHATAM ho gaya hai — admin se rabta "
                "karen.", "ERROR")
    else:
        ctx.log(f"Server jawab: {status}", "WARN")
    return False
