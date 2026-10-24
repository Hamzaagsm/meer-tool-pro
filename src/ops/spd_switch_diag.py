"""
spd_switch_diag.py — "Switch to Diag": SPD section ka pehla qadam.

Hamza ki FINAL tartib (SPD-EXPANSION.md, 2026-10-24) ka step 1:
Diag mode me connect -> us ke baad Restore / FRP / IMEI ke
process easy ho jate hain. Ye op wahi connect asal me karke
dikhata hai. PEHLA RASTA BINA BUTTON: phone ON rakho — Diag
port (SPRD U2S Diag) khud nazar ayega; band phone + boot key
sirf fallback hai un phones ke liye jin ka Diag ON halat me
nahi khulta (Vol combo sirf isi fallback ke liye hai, Diag
ke liye lazmi nahi):

  1. SPRD Diag port (1782:4D00/4D01) ka intezaar aur pehchan
     (core/spd_diag + device_watch wali hi pehchan).
  2. Port khol kar AT+CGSN se IMEI 1 ki halat PARH kar log:
     durust IMEI, ya imaandari se "000000/null" — yehi wo field
     halat hai jo Hamza ne batayi thi (tool "written" kehta hai,
     phone me purana hi rehta hai). Halat sabit na ho to op
     SUCCESS nahi deta.
  3. Agar GUI params me IMEI diya gaya ho to aakhir me IMEI
     write wala hissa: IMEI GATE + Luhn ke baad imaandar
     guided-FAIL (core/spd_diag.write_imei_via_diag) — SPRD diag
     NV write public documented nahi, is liye asal write Cert
     Restore (prodnv, FDL) se hoti hai. Baghair params ke ye
     hissa chalta hi nahi.

Diag connect ho jane ke baad wale qadam (Restore/FRP) maujooda
ops hi hain: spd_cert_restore / spd_cert_backup / spd_frp.
"""

import time

from core import spd_diag

OP = {
    "id": "spd_switch_diag",
    "category": "SPD / Unisoc",
    "name": "Switch to Diag — Connect + IMEI State",
    "engine": "spd_diag",
    "modes": ("SPD",),
    "server_required": False,
}

WAIT_SECONDS = 90      # Diag port ke intezaar ka waqt (GUI params 'diag_wait' se override)


def _wait_seconds(ctx) -> int:
    try:
        return max(1, int(ctx.params.get("diag_wait", WAIT_SECONDS)))
    except Exception:  # noqa: BLE001
        return WAIT_SECONDS


def _boot_line(ctx):
    """Chip ke hisaab se boot-key rehnumai (mile to), warna aam line.

    Ye SIRF fallback hai — pehla rasta phone ON + Diag port hai.
    """
    try:
        from core import spd_chips
        line = spd_chips.boot_guidance(ctx.device)
        if line:
            return "Fallback (agar ON rasta na chale): " + line
    except Exception:  # noqa: BLE001 — rehnumai hi hai, rukawat nahi
        pass
    return ("Fallback (agar ON rasta na chale) — Boot key: Volume "
            "Down (kuch models par Up, naye Transsion par Up+Down "
            "dono) | Diag port: 1782:4D00")


def _find_port(ctx, wait_s):
    """(port_name, description) ya None — pehle device panel wala
    port, phir scan; waqt bhar polling, cancel par foran bahir."""
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
                    "aaye to band phone + boot key fallback hai.",
                    "INFO")
        time.sleep(0.5)


def run(ctx) -> bool:
    ctx.log("SPD tartib ka pehla qadam: Switch to Diag. Pehle "
            "BINA button: phone ON rakho — Diag port khud nazar "
            "ayega; na aaye to band phone + boot key sirf "
            "fallback hai. Diag connect ho jane ke baad "
            "Restore / FRP / IMEI ke process isi tartib se honge.",
            "INFO")
    ctx.log(_boot_line(ctx), "INFO")
    ctx.progress(10, "Diag port dhoondha ja raha hai...")

    try:
        found = _find_port(ctx, _wait_seconds(ctx))
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return False
    if ctx.is_cancelled():
        ctx.log("User ne rok diya — Diag connect nahi hua.", "WARN")
        return False
    if found is None:
        ctx.log("Diag port waqt ke andar nahi mila. Check karo: "
                "SPRD driver install hai, phone ON tha (ya "
                "fallback: band halat me boot key dabaye hue laga "
                "tha), cable durust hai. Port Device Manager me "
                "'SPRD U2S Diag' (1782:4D00) ke naam se ana "
                "chahiye.", "ERROR")
        return False
    port, desc = found
    ctx.log(f"Diag port mil gaya: {port} ({desc or 'SPRD Diag'})",
            "OK")
    ctx.progress(35, f"Diag port mila: {port} — session khul raha hai...")

    session = spd_diag.DiagSession(port)
    try:
        session.open()
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return False
    ctx.progress(45, f"Diag session khula: {port}")
    try:
        state, value = session.read_imei_state()
    except spd_diag.DiagError as e:
        session.close()
        ctx.log(str(e), "ERROR")
        ctx.log("Diag port khul gaya tha, lekin is channel par "
                "IMEI ki halat sabit nahi hui — SPRD diag ka NV "
                "protocol public documented nahi hai, is liye "
                "andaze se koi number nahi dikhaya jayega. IMEI "
                "ki asal halat FDL Cert Backup (prodnv read) se "
                "sabit hoti hai.", "WARN")
        return False
    try:
        if state == "ok":
            ctx.log(f"IMEI 1: {value} (Luhn pass — device par "
                    "asal IMEI maujood hai)", "DATA")
            ctx.log("Diag connect mukammal aur IMEI ki halat "
                    "sabit hai. Ab tartib ke agle qadam (Restore / "
                    "FRP / IMEI) isi session ke baad easy honge.",
                    "OK")
        else:
            # 'zero' ya 'null' — halat sabit hai, aur yehi Hamza
            # ki field report wali surat hai.
            ctx.log("IMEI 1 ki halat: NULL / 000000 — device par "
                    "koi durust IMEI maujood NAHI hai (modem khali "
                    "parh raha hai).", "WARN")
            ctx.log("Ye wohi halat hai jahan doosre tools 'write "
                    "done' keh dete hain lekin phone me number "
                    "lagta nahi. Is ka asal hal Cert Restore hai: "
                    "apna prodnv backup wapas likho (Cert Backup "
                    "pehle lazmi), ya gated 'Restore Original "
                    "IMEI' wala rasta.", "WARN")
            ctx.log("Diag connect ho gaya hai aur halat sabit "
                    "hai — op ka kaam mukammal.", "OK")
        ctx.progress(80, "Diag connect + IMEI halat sabit")

        # --- Aakhri hissa: IMEI write (sirf params mile hon to) --
        imei1 = (ctx.params.get("imei1") or "").strip()
        imei2 = (ctx.params.get("imei2") or "").strip()
        if imei1 or imei2:
            ctx.log("IMEI write ki darkhwast mili hai — tartib "
                    "ka aakhri qadam. Pehle gate, phir faisla:",
                    "INFO")
            return spd_diag.write_imei_via_diag(ctx, session,
                                                imei1, imei2)
        return True
    finally:
        session.close()
