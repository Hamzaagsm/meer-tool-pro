"""
carrier_unlock_guide.py — Carrier / Network Unlock Guide (Pakistan).

SERVER-REQUIRED research §4.4: network unlock code koi free tool
generate NAHI kar sakta — code carrier ke database/algorithm se
ata hai (server-side secret). Free-qanooni rasta carrier ki apni
request hai — ye op wahi rasta dikhata hai (helplines + procedure),
dead-end FAIL ki jagah.

Helplines (research ~/workspace/research/gsm-pakistan-carrier-
unlock.md, verify 2026-10-12):
  Jazz    — 111
  Zong    — 310 (Zong number se) / (051) 111-222-111
  Ufone   — 333 (Ufone number se) / 033-11-333-100
  Telenor — 345 (Telenor number se) / 042-111-345-100

Phone ADB me ho to operator naam se carrier pehchan kar sirf us
ki guide dikhti hai; warna chaaron carriers ki guide ati hai.
Ye op koi unlock code nahi banata, koi call nahi karta, koi
server nahi chhoota — sirf rehnumai hai.

Device ki zaroorat nahi (modes ()).
"""

from core import device_watch, engines

OP = {
    "id": "carrier_unlock_guide",
    "category": "Utility",
    "name": "Carrier Unlock Guide (Pakistan — Free Legal Route)",
    "engine": "local",
    "modes": (),
    "server_required": False,
}

CARRIERS = (
    {
        "name": "Jazz",
        "aliases": ("jazz", "mobilink", "warid"),
        "helpline": "111",
        "alt": "",
        "steps": [
            "Jazz helpline 111 par call karo.",
            "'Network unlock code' mango.",
            "IMEI (*#06# se) aur CNIC tayyar rakho.",
            "Qist/contract poora ho to carrier muft unlock karta hai.",
        ],
    },
    {
        "name": "Zong",
        "aliases": ("zong",),
        "helpline": "310",
        "alt": "(051) 111-222-111",
        "steps": [
            "Zong number se 310 par call karo (kisi bhi phone se "
            "(051) 111-222-111).",
            "'Network unlock code' mango.",
            "IMEI (*#06# se) aur CNIC tayyar rakho.",
            "Qist/contract poora ho to carrier muft unlock karta hai.",
        ],
    },
    {
        "name": "Ufone",
        "aliases": ("ufone",),
        "helpline": "333",
        "alt": "033-11-333-100",
        "steps": [
            "Ufone number se 333 par call karo (ya 033-11-333-100).",
            "'Network unlock code' mango.",
            "IMEI (*#06# se) aur CNIC tayyar rakho.",
            "Qist/contract poora ho to carrier muft unlock karta hai.",
        ],
    },
    {
        "name": "Telenor",
        "aliases": ("telenor",),
        "helpline": "345",
        "alt": "042-111-345-100",
        "steps": [
            "Telenor number se 345 par call karo (kisi bhi network / "
            "PTCL se 042-111-345-100).",
            "'Network unlock code' mango.",
            "IMEI (*#06# se) aur CNIC tayyar rakho.",
            "Qist/contract poora ho to carrier muft unlock karta hai.",
        ],
    },
)


def carrier_from_text(text):
    """Operator naam se carrier — dict ya None (pure).

    "Jazz" / "Mobilink" / "ZONG" / "Telenor PK" jaisi suraten
    chalti hain; na mile to None (andaza nahi)."""
    low = str(text or "").lower()
    if not low.strip():
        return None
    for carrier in CARRIERS:
        if any(alias in low for alias in carrier["aliases"]):
            return carrier
    return None


def guide_lines(carrier):
    """Aik carrier ki rehnumai lines (pure)."""
    lines = [f"{carrier['name']} — Helpline: {carrier['helpline']}"]
    if carrier.get("alt"):
        lines.append(f"  Doosra number: {carrier['alt']}")
    for i, step in enumerate(carrier["steps"], 1):
        lines.append(f"  {i}. {step}")
    return lines


def _detect_carrier(ctx):
    """ADB device ho to operator props se carrier — dict ya None."""
    dev = getattr(ctx, "device", None)
    if dev is None or getattr(dev, "mode", None) != "ADB":
        return None
    try:
        adb = engines.find_platform_tool("adb")
        props = device_watch.adb_getprops(adb, dev.serial)
    except Exception:  # noqa: BLE001 — props na milen to sab guides
        return None
    for key in ("gsm.sim.operator.alpha", "gsm.operator.alpha",
                "ro.carrier", "gsm.sim.operator.numeric"):
        hit = carrier_from_text((props or {}).get(key, ""))
        if hit is not None:
            return hit
    return None


def run(ctx) -> bool:
    ctx.log("Network unlock code koi free tool generate nahi kar "
            "sakta — code carrier ke paas hai. Asal duniya ka "
            "rasta ye hai:", "INFO")
    carrier = _detect_carrier(ctx)
    if carrier is not None:
        ctx.log("Phone ka carrier pehchana gaya:", "OK")
        for line in guide_lines(carrier):
            ctx.log(line, "INFO")
    else:
        ctx.log("Carrier pehchana nahi gaya (ya phone ADB me nahi) "
                "— chaaron carriers ki guide:", "INFO")
        for carrier in CARRIERS:
            for line in guide_lines(carrier):
                ctx.log(line, "INFO")
    ctx.log("Note: IMEI-based online unlock services maujood hain "
            "lekin paid hain — MEER unhen 'free' keh kar nahi "
            "dikhaye ga.", "INFO")
    return True
