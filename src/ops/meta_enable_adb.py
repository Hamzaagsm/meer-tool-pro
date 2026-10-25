"""
meta_enable_adb.py — META mode me FT protocol se ADB enable.

Pehle NEW-AUTH GUARD: naye-security Dimensity chips (MT6835 /
MT6878 / MT6983, Dimensity 6300/6400/7300/9000/9400) par META entry
hi 'new Auth' mang sakti hai jo server-assisted hai — wahan ye op
🔒 wajah ke saath ruk jata hai (core.meta_guard ki LADDER —
rukne ke saath doosra darwaza khud offer hota hai; Round 7 B7).

Baaki devices par META port se FT_SET_ADB request jati hai —
payload = FT set-value 1 byte 0x01 (ADB on). SUCCESS sirf verified
status==0x00 jawab par hai. ADB asal me tab milega jab phone normal
reboot ho jaye — us ke baad ADB tab ke ops chalte hain.
"""

from core import meta_guard, meta_session

OP = {
    "id": "meta_enable_adb",
    "category": "MDM / Transsion",
    "name": "Enable ADB (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}

# FT set-value: ADB enable ke liye aik byte — 0x01 = on
_ADB_ON_PAYLOAD = bytes([0x01])


def _new_auth_blocked(ctx) -> bool:
    """True = SERVER-REQUIRED wajah log ho chuki hai, aage mat barho.

    Round 7 (B7): rukna ab LADDER ke saath hai (core.meta_guard) —
    wajah ke saath doosra zinda darwaza (DA/Heapbait, test point,
    ADB) khud offer hota hai."""
    hit = meta_guard.hit_for(ctx)
    if not hit:
        return False
    meta_guard.ladder_stop(ctx, hit)
    return True


def run(ctx) -> bool:
    if _new_auth_blocked(ctx):
        return False
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    ctx.progress(30, "FT ADB-enable request bheji ja rahi hai...")
    try:
        with session:
            status, _payload = session.request(
                meta_session.FT_SET_ADB, payload=_ADB_ON_PAYLOAD,
                timeout=15)
    except meta_session.MetaError as e:
        ctx.log(str(e), "ERROR")
        return False
    if ctx.is_cancelled():
        return False
    if status != meta_session.FT_STATUS_OK:
        ctx.log(f"FT jawab aya lekin status token theek nahi "
                f"(status=0x{status & 0xFF:02X}) — ADB enable qabool "
                "nahi hua mana jayega. Kuch firmwares META se ADB "
                "set-value qabool hi nahi karte.", "ERROR")
        return False
    ctx.progress(85, "ADB enable ka verified jawab mil gaya")
    ctx.log("ADB enable ka verified jawab (status OK) mil gaya.", "OK")
    # Aakhri qadam (Smart 20 bench flaw fix, 2026-10-25): phone khud
    # normal boot par jaye — ADB asal me tab milega jab phone
    # normal reboot ho; pehle META mode me atka rehta tha.
    meta_session.reboot_to_normal(ctx)
    ctx.log("Agla qadam: phone normal boot hone par ADB ON milna "
            "chahiye; phir device panel me ADB mode ayega aur ADB "
            "tab ke ops (info, app profiles, Security Plugin "
            "waghera) chal sakenge. Agar reboot ke baad bhi ADB na "
            "mile to is firmware ne setting save nahi ki — wo surat "
            "log me nakli kamyabi se nahi chhupayi jayegi.",
            "INFO")
    ctx.progress(95, "Enable ADB mukammal")
    return True
