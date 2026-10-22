"""
meta_read_info.py — META mode me FT protocol se asal device info.

META port (core.meta_session) khol kar FT_VERSION_INFO request bheji
jati hai. SUCCESS sirf tab hai jab jawab verified frame me aye,
status token 0x00 ho, aur payload khali na ho — jawab ka text DATA
lines me log hota hai. Timeout / ghalat status / khali payload =
saaf FAIL, wajah ke saath. Command "bhej di" kabhi success nahi.
"""

from core import meta_session

OP = {
    "id": "meta_read_info",
    "category": "MDM / Transsion",
    "name": "Read Info (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    ctx.log("META mode se device info parhi ja rahi hai — pehle META "
            "port ka session khulega.", "INFO")
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    ctx.progress(30, "FT version/info request bheji ja rahi hai...")
    try:
        with session:
            status, payload = session.request(
                meta_session.FT_VERSION_INFO, timeout=15)
    except meta_session.MetaError as e:
        ctx.log(str(e), "ERROR")
        ctx.log("Guide: phone META mode me hi rakho, cable na hilao; "
                "kuch firmwares par FT info request ka jawab nahi "
                "ata — aisi surat me ye op imaandari se FAIL hi "
                "rahega, nakli info nahi banegi.", "WARN")
        return False
    if ctx.is_cancelled():
        return False
    if status != meta_session.FT_STATUS_OK:
        ctx.log(f"FT jawab aya lekin status token theek nahi "
                f"(status=0x{status & 0xFF:02X}) — info qabool nahi "
                "ki gayi.", "ERROR")
        return False
    if not payload:
        ctx.log("FT jawab ka status theek hai lekin info payload "
                "khali hai — is device/firmware se info nahi parhi "
                "ja saki.", "ERROR")
        return False
    ctx.progress(80, "Info mil gayi — log me likhi ja rahi hai")
    text = payload.decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        # Text na bane to raw bytes hex me dikha do — jo aya wahi sach hai
        ctx.log(f"Info payload (raw hex): {payload.hex(' ')}", "DATA")
    for ln in lines:
        printable = "".join(ch if ch.isprintable() else "·" for ch in ln)
        ctx.log(printable, "DATA")
    ctx.log("META Read Info mukammal — upar wali maloomat phone ke "
            "asal FT jawab se ayi hai.", "OK")
    ctx.progress(95, "Read Info mukammal")
    return True
