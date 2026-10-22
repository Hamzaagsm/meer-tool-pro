"""
adb_private_dns.py — Private DNS Toggle (Servicing Task).

Android ka Private DNS (DNS-over-TLS) `settings global` se
control hota hai:
  private_dns_mode     = off | hostname | opportunistic
  private_dns_specifier= provider ka hostname (hostname mode)

Ye op toggle hai: DNS band ho to dns.google ke saath ON,
chal raha ho (hostname/opportunistic) to OFF. Kai servicing
halaton me ye kaam ata hai (ads/DNS maslay, network test).

IMAANDARI:
  - Root: NAHI chahiye — global settings shell se likhi ja
    sakti hain.
  - SUCCESS sirf readback par: likhne ke baad dobara parh
    kar nayi value asal me wahi ho jo likhi thi. ROM ne
    ignore kiya to FAIL.
"""

from ops.adb_remove_ads import guard, sh

OP = {
    "id": "adb_private_dns",
    "category": "ADB / Fastboot",
    "name": "Private DNS Toggle (Servicing)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}

PROVIDER = "dns.google"


def dns_next_action(current):
    """Maujooda mode -> (nayi_mode, specifier|None) (pure).

    Band/unset ('off', 'null', khali) ho to hostname+dns.google
    ke saath ON; koi bhi chalti halat (hostname/opportunistic)
    ho to OFF.
    """
    cur = (current or "").strip().lower()
    if cur in ("off", "null", ""):
        return "hostname", PROVIDER
    return "off", None


def _get(adb, serial, key):
    out, _ = sh(adb, serial, ["settings", "get", "global", key])
    return (out or "").strip()


def _put(adb, serial, key, value):
    sh(adb, serial, ["settings", "put", "global", key, value])


def run(ctx) -> bool:
    adb, serial = guard(ctx)
    if adb is None:
        return False
    ctx.log("Root: NAHI chahiye — settings global shell se "
            "badli jati hai; saboot readback hoga.", "INFO")
    current = _get(adb, serial, "private_dns_mode")
    ctx.log(f"Maujooda Private DNS mode: {current or '(khali)'}",
            "DATA")
    mode, specifier = dns_next_action(current)
    ctx.progress(40, "Private DNS badla ja raha hai...")
    _put(adb, serial, "private_dns_mode", mode)
    if specifier:
        _put(adb, serial, "private_dns_specifier", specifier)
        ctx.log(f"Private DNS ON kiya ja raha hai — provider: "
                f"{specifier}", "INFO")
    else:
        ctx.log("Private DNS OFF kiya ja raha hai.", "INFO")
    back_mode = _get(adb, serial, "private_dns_mode")
    back_spec = _get(adb, serial, "private_dns_specifier")
    ctx.log(f"Readback: mode={back_mode or '(khali)'}"
            + (f", specifier={back_spec}" if specifier else ""),
            "DATA")
    ok = back_mode.lower() == mode
    if ok and specifier:
        ok = back_spec.lower() == specifier
    if not ok:
        ctx.log("Readback likhi hui value se match NAHI hua — "
                "is ROM ne setting ignore kar di. FAIL (nakli "
                "success nahi).", "ERROR")
        return False
    state = f"ON ({specifier})" if specifier else "OFF"
    ctx.log(f"Private DNS ab {state} hai — device readback se "
            "verify shuda.", "OK")
    ctx.progress(95, "Private DNS toggle mukammal")
    return True
