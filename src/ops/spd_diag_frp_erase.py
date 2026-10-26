"""
spd_diag_frp_erase.py — Universal Diag FRP Erase (Transsion Unisoc).

NCK Online Tool Unisoc Module v1.9 (20 Oct 2026) + UMT Unisoc
v2.3 (Oct 2026) ka "universal Diag FRP erase" — "will autodetect
phone and erase FRP if supported. No model selection needed."
(RESEARCH-2 §1.9, §8.4, §9.2.) MEER me wahi usool:

  1. NO MODEL SELECTION — Diag port khud dhoondha jata hai
     (1782:4D00/4D01), phone identify hota hai (AT+CGMI/CGMM/
     CGMR/CGSN — 3GPP TS 27.007, public).
  2. Naye Unisoc models pehle: Smart 10 (X6725), Pop 10 (KM4s),
     Spark Go 1/3, Itel P65 class, T7250/T760/T820/T7300.
  3. FRP erase ki koshish core/spd_diag.py ke verified-command
     table se hoti hai — table aaj KHALI hai (NCK/UMT ke Diag
     command bytes closed hain; koi public byte-level spec nahi
     mili — dobara dhoonda gaya). Is liye op aaj: identify +
     darja-bandi + session-verify karta hai, phir IMAANDAR FAIL
     deta hai (bench-capture rehnumai + working FDL alternative
     ke saath). Port par erase ke naam par AIK byte bhi nahi
     jata. **Agar device expected jawab na de to FAIL — "ho
     gaya" kabhi nahi likha jata.**
  4. Jab bench-capture se table me entry aye gi, wahi op baghair
     tabdeeli ke asal koshish karega aur jawab verify karega.

Working alternative (aaj, asal): 'Unisoc FRP Erase (FDL)'
(spd_frp) — persist erase, FDL session se.
"""

import time

from core import spd_diag

OP = {
    "id": "spd_diag_frp_erase",
    "category": "SPD / Unisoc",
    "name": "Diag FRP Erase — Universal (No Model Select)",
    "engine": "spd_diag",
    "modes": ("SPD",),
    "server_required": False,
}

WAIT_SECONDS = 90


def _wait_seconds(ctx) -> int:
    try:
        return max(1, int(ctx.params.get("diag_wait", WAIT_SECONDS)))
    except Exception:  # noqa: BLE001
        return WAIT_SECONDS


def _find_port(ctx, wait_s):
    """(port, description) ya None — pehle device panel, phir scan."""
    dev = ctx.device
    if dev is not None and getattr(dev, "mode", "") == "SPD" \
            and getattr(dev, "port", ""):
        return dev.port, getattr(dev, "detail", "") or "Device panel"
    deadline = time.time() + wait_s
    last_log = 0.0
    while True:
        ports = spd_diag.find_diag_ports()
        if ports:
            return ports[0][0], ports[0][1]
        if ctx.is_cancelled() or time.time() >= deadline:
            return None
        now = time.time()
        if now - last_log >= 10:
            last_log = now
            left = int(deadline - now)
            ctx.progress(15, f"Diag port ka intezaar... ({left}s)")
            ctx.log(f"Diag port ka intezaar hai... ({left}s baqi) "
                    "— phone ON rakho (Diag port khud ayega); na "
                    "aaye to band phone + boot key (Vol Down, kuch "
                    "par Up, naye Transsion par Up+Down).", "INFO")
        time.sleep(0.5)


def _identify(ctx, session):
    """Diag session se pehchan — log + dict, ya None (FAIL ki taraf)."""
    try:
        ident = spd_diag.identify_diag_device(session)
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return None
    ctx.log(f"Pehchan: {ident.get('manufacturer') or '?'} "
            f"{ident.get('model') or '?'}"
            f" (firmware: {ident.get('firmware') or 'na-maloom'})",
            "DATA")
    state, value = ident.get("imei_state"), ident.get("imei")
    if state == "ok":
        ctx.log(f"IMEI 1: {value} (Luhn pass)", "DATA")
    else:
        ctx.log(f"IMEI ki halat: {state or 'na-maloom'} — FRP erase "
                "se IMEI nahi badalta (ye sirf FRP state ka kaam "
                "hai).", "WARN")
    tier, reason = spd_diag.classify_diag_target(ident)
    ctx.log(f"Target darja: {tier.upper()} — {reason}",
            "INFO" if tier != "unknown" else "WARN")
    return ident


def run(ctx) -> bool:
    ctx.log("Universal Diag FRP Erase — koi model select nahi: "
            "Diag port khud milega, phone khud pehchana jayega, "
            "FRP erase ki koshish hogi (NCK Unisoc v1.9 / UMT "
            "Unisoc v2.3 wali universal tartib). Naye Unisoc "
            "pehle: Smart 10, Pop 10, Spark Go 1/3, Itel P65, "
            "T7250/T760/T820/T7300 class.", "INFO")
    ctx.progress(10, "Diag port dhoondha ja raha hai...")
    try:
        found = _find_port(ctx, _wait_seconds(ctx))
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return False
    if ctx.is_cancelled():
        ctx.log("User ne rok diya — Diag FRP erase nahi hua.", "WARN")
        return False
    if found is None:
        ctx.log("Diag port waqt ke andar nahi mila. Check karo: "
                "SPRD driver install hai, phone ON tha (ya band "
                "halat me boot key dabaye hue laga tha), cable "
                "durust hai. Port Device Manager me 'SPRD U2S "
                "Diag' (1782:4D00) ke naam se ana chahiye.", "ERROR")
        return False
    port, desc = found
    ctx.log(f"Diag port mil gaya: {port} ({desc or 'SPRD Diag'})", "OK")
    ctx.progress(35, f"Diag session khul raha hai: {port}...")

    session = spd_diag.DiagSession(port)
    try:
        session.open()
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return False
    try:
        ident = _identify(ctx, session)
        if ident is None:
            return False
        ctx.progress(60, "FRP erase ki koshish ho rahi hai...")
        ok, evidence = spd_diag.attempt_diag_frp_erase(session, ident)
        if not ok:
            ctx.log("Diag FRP erase NAHI ho saka — imaandar FAIL "
                    "(jhooti SUCCESS nahi).", "ERROR")
            ctx.log(evidence, "WARN")
            ctx.log("Aaj ka working rasta: 'Unisoc FRP Erase "
                    "(FDL)' op (spd_frp) — FDL session se persist "
                    "erase, usi phone par. Wo op chalao.", "INFO")
            return False
        ctx.progress(95, "Diag FRP erase mukammal")
        ctx.log(evidence, "OK")
        ctx.log("FRP erase ka jawab verify hua. Phone on karke "
                "check karo — setup wizard me purana Google "
                "account NAHI mangna chahiye.", "OK")
        return True
    finally:
        session.close()
