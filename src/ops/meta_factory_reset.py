"""
meta_factory_reset.py — META mode me FT protocol se factory reset.

Pehle NEW-AUTH GUARD: naye-security Dimensity chips (MT6835 /
MT6878 / MT6983, Dimensity 6300/6400/7300/9000/9400) par
new-algorithm META FRP/auth SERVER-REQUIRED hai — wahan ye op
chalne ka natak nahi karta, 🔒 wajah ke saath ruk jata hai
(core.mdm_list.NEW_AUTH_TOKENS; MDM List ke TMETA ops wala hi usool).

Baaki devices par META port se FT_FACTORY_RESET request jati hai.
IMAANDARI: ye reset META ka userdata-level reset hai — FRP tabhi
saaf hoga jab is model/security par META reset FRP bhi saaf kare
(old/mid security par aam tor par hota hai; naye par nahi). SUCCESS
sirf verified status==0x00 jawab par hai; us ke baad bhi asal
tasdeeq phone reboot karke setup me khud karni hai.
"""

from core import meta_session
from core.mdm_list import NEW_AUTH_TOKENS

OP = {
    "id": "meta_factory_reset",
    "category": "MDM / Transsion",
    "name": "Factory Reset (META Mode)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}


def _new_auth_blocked(ctx) -> bool:
    """True = SERVER-REQUIRED wajah log ho chuki hai, aage mat barho."""
    dev = ctx.device
    if dev is None:
        return False
    hay = " ".join([getattr(dev, "chip", "") or "",
                    getattr(dev, "model", "") or "",
                    getattr(dev, "detail", "") or ""])
    hit = next((t for t in NEW_AUTH_TOKENS if t.lower() in hay.lower()),
               None)
    if not hit:
        return False
    ctx.log(f"🔒 SERVER REQUIRED — chip/model pehchana gaya: {hit}. "
            "Is class par new-algorithm META FRP/auth server-side "
            "hota hai: Pandora jaisi tools bhi ye kaam apne auth/"
            "server se karti hain, public offline tareeqa maujood "
            "nahi.", "ERROR")
    ctx.log("Is liye ye op yahan ruk raha hai — jhooti koshish ya "
            "nakli success nahi di jayegi. Doosra darwaza: BROM/"
            "Download route ke ops (agar is model par chalte hon) "
            "ya authorized service.", "WARN")
    return True


def run(ctx) -> bool:
    if _new_auth_blocked(ctx):
        return False
    ctx.log("Ye META reset USERDATA-LEVEL hai — FRP tabhi jayega "
            "jab is model/security par META reset FRP bhi saaf kare "
            "(old/mid security par aam tor par hota hai; naye "
            "security par nahi — wahan wala guard upar lag chuka "
            "hai).", "WARN")
    ctx.log("Reset se pehle bata do: phone ka tamam data mit "
            "jayega — customer ki ijazat aur zaroori backup pehle "
            "lazmi hai.", "WARN")
    ctx.log("Changelog saboot: EFT Pro v5.6.6 ne Android 16 par "
            "META-mode FRP 20 taaza Transsion models par verify "
            "kiya hai (Infinix Note 50/40, HOT 60, GT 30 series; "
            "Tecno Camon 40, Pova 7 series) — MDM List me in "
            "models par '✓A16' nishan hai. Rasta public META "
            "protocol hi hai; new-Auth wale chips is se bahir "
            "hain (upar wala guard).", "INFO")
    session = meta_session.open_session(ctx)
    if session is None:
        return False
    ctx.progress(30, "FT factory reset request bheji ja rahi hai...")
    try:
        with session:
            status, _payload = session.request(
                meta_session.FT_FACTORY_RESET, timeout=20)
    except meta_session.MetaError as e:
        ctx.log(str(e), "ERROR")
        return False
    if ctx.is_cancelled():
        return False
    if status != meta_session.FT_STATUS_OK:
        ctx.log(f"FT jawab aya lekin status token theek nahi "
                f"(status=0x{status & 0xFF:02X}) — reset qabool "
                "nahi hua mana jayega.", "ERROR")
        return False
    ctx.progress(85, "Reset ka verified jawab mil gaya")
    ctx.log("META factory reset ka verified jawab (status OK) mil "
            "gaya — phone ko reboot hone do.", "OK")
    ctx.log("Tasdeeq tum khud karo: phone reboot karke setup check "
            "karo — data saaf hona chahiye; agar setup par purana "
            "Google account (FRP) mange to is model/security par "
            "META reset ne FRP saaf nahi kiya (upar wali imaandari "
            "wali line yaad karo) — phir BROM/Download wala FRP "
            "rasta istemal hoga.", "INFO")
    ctx.progress(95, "Factory Reset mukammal")
    return True
