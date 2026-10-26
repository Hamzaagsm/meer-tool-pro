"""
stubs.py — SERVER REQUIRED operations ke imaandar stubs.

Ye operations free engines se mumkin NAHI (paid server ka signed auth
chahiye — DESIGN.md section 3 dekho). UI me ye SERVER REQUIRED tag ke
saath nazar ayenge, aur chalane par log me saaf wajah milegi aur FAIL
return hoga. **Nakli success, nakli progress, nakli log — kabhi nahi.**

2026-10-25 (Fenix usool): khaali label par rukna band — har stub
ke saath us ka FREE / asal-duniya ka rasta bhi log hota hai
(`alt`): pehle MEER ka free darwaza azmao, phir jo baqi bache
wo saaf rehnumai ke saath. Server copy nahi ho sakta (MEER
free hai), lekin user kabhi dead-end par khara nahi rehta.

Jab Hamza ke paas kisi operation ka asal rasta (apna loader/server
access) ajaye ga, to us ka stub asal plugin se badal diya jayega.
"""


def _make(op_id, category, name, reason, alt=None):
    def run(ctx, _reason=reason, _name=name, _alt=alt):
        ctx.log(f"'{_name}' is build me available nahi hai.", "WARN")
        ctx.log(f"Wajah: {_reason}", "ERROR")
        ctx.log("Ye operation paid-server tools (Fenix/UnlockTool waghera) "
                "apne server se sign karwa kar karte hain. Free engine se "
                "ye mumkin nahi — is liye yahan fake button/success nahi "
                "rakha gaya.", "INFO")
        if _alt:
            ctx.log(f"Doosra darwaza: {_alt}", "INFO")
        return False

    return {
        "OP": {
            "id": op_id,
            "category": category,
            "name": name,
            "engine": "server",
            "modes": (),
            "server_required": True,
        },
        "run": run,
    }


# Registry (ops/__init__) sirf module-level OP/run uthata hai — is file ke
# stubs ko registry me shamil karne ke liye har stub ko neeche alag module
# namespace ki tarah expose kiya gaya hai: load_operations inhen
# STUB_OPS list se bhi parhta hai.
STUB_DEFS = [
    _make("mtk_sla_auth", "MTK",
          "SLA/DAA Auth Bypass (New Chipsets)",
          "Naye MTK chipsets ka BROM locked hai; server-signed DA/auth "
          "file lazmi hai.",
          "Pehle MTK ops tree ka 'Latest Bypass (Auto)' chalao — "
          "payload → carbonara → heapbait chain GPT se verify hota "
          "hai aur aksar SLA/DAA ko free me paar kar leta hai. "
          "Transsion phone ho to MDM List ka TMETA route bhi "
          "documented free rasta hai. Chain bhi nakam ho to ye "
          "waqai server case hai."),
    _make("qc_auth_flash", "Qualcomm",
          "Auth Flashing (Oppo/Vivo/Xiaomi EDL)",
          "Brand ke authorized server account ke baghair EDL auth "
          "nahi milta; firehose loader bhi authenticated chahiye.",
          "Free raste: (1) 'No-Auth Loader Slot' se apna patched "
          "loader darj karo, phir 'Xiaomi No-Auth EDL' chalao "
          "(purane chips); (2) 'Firmware → Loader Harvest' se "
          "stock firmware se loader nikalo; (3) Loaders Library "
          "me match check karo. Naya locked model + auth "
          "handshake ho to ye server wala kaam hai — authorized "
          "account/service center. Koi crack/shared login "
          "istemal nahi kiya jayega."),
    _make("samsung_frp_new", "Samsung",
          "FRP Remove (Latest Security)",
          "Latest Samsung FRP server/Knox verification par mabni hai.",
          "Pehle Samsung section ka 'FRP Remove — Test Mode *#0*# "
          "(Free)' chalao — Dec 2022 tak ki firmware par wo FRP "
          "khud hatata hai (MEER ka apna engine). Sirf latest "
          "security par ruke to ye server case hai; 'FRP Method "
          "Router' patch tareekh se faisla batata hai."),
    _make("carrier_unlock", "Samsung",
          "Carrier / Network Unlock",
          "Network unlock aksar models par server credits se hota hai.",
          "Code carrier ke paas hai — UTILITY ka 'Carrier Unlock "
          "Guide' op chalao: Jazz 111 / Zong 310 / Ufone 333 / "
          "Telenor 345 par call karne ke steps milenge (CNIC + "
          "IMEI tayyar rakho)."),
]

# Module-level pehla stub (taake file plugin contract par bhi poora utre)
_first = STUB_DEFS[0]
OP = _first["OP"]
run = _first["run"]
STUB_OPS = STUB_DEFS
