"""
stubs.py — SERVER REQUIRED operations ke imaandar stubs.

Ye operations free engines se mumkin NAHI (paid server ka signed auth
chahiye — DESIGN.md section 3 dekho). UI me ye SERVER REQUIRED tag ke
saath nazar ayenge, aur chalane par log me saaf wajah milegi aur FAIL
return hoga. **Nakli success, nakli progress, nakli log — kabhi nahi.**

Jab Hamza ke paas kisi operation ka asal rasta (apna loader/server
access) ajaye ga, to us ka stub asal plugin se badal diya jayega.
"""


def _make(op_id, category, name, reason):
    def run(ctx, _reason=reason, _name=name):
        ctx.log(f"'{_name}' is build me available nahi hai.", "WARN")
        ctx.log(f"Wajah: {_reason}", "ERROR")
        ctx.log("Ye operation paid-server tools (Fenix/UnlockTool waghera) "
                "apne server se sign karwa kar karte hain. Free engine se "
                "ye mumkin nahi — is liye yahan fake button/success nahi "
                "rakha gaya.", "INFO")
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
          "file lazmi hai."),
    _make("qc_auth_flash", "Qualcomm",
          "Auth Flashing (Oppo/Vivo/Xiaomi EDL)",
          "Brand ke authorized server account ke baghair EDL auth "
          "nahi milta; firehose loader bhi authenticated chahiye."),
    _make("samsung_frp_new", "Samsung",
          "FRP Remove (Latest Security)",
          "Latest Samsung FRP server/Knox verification par mabni hai."),
    _make("carrier_unlock", "Samsung",
          "Carrier / Network Unlock",
          "Network unlock aksar models par server credits se hota hai."),
]

# Module-level pehla stub (taake file plugin contract par bhi poora utre)
_first = STUB_DEFS[0]
OP = _first["OP"]
run = _first["run"]
STUB_OPS = STUB_DEFS
