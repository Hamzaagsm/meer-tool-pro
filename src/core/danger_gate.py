"""
danger_gate.py — Khatarnaak (destructive) write ops ka tasdeeq gate.

IMEI gate (core/imei_gate.py) ki hi discipline family, lekin un
asal operations ke liye jo device par seedha DESTRUCTIVE write
karte hain: RPMB Write / RPMB Erase, raw sector write waghera.
In me ghalti ki qeemat aam write se kahin zyada hai — RPMB to
authenticated / anti-rollback area hai, wahan likha hua data
aam flash se bhi wapas nahi ata.

Usool:
  1. Live log me bhaari warning hamesha, har dafa chhapegi.
  2. User ki explicit tasdeeq lazmi — GUI ke neeche wale bar ki
     "⚠ Tasdeeq (KHATARNAAK write)" checkbox `ctx.danger_confirmed`
     ban kar ati hai. Tasdeeq na ho to op yahin RUK jata hai:
     ye guided STOP hai, error nahi, aur device par AIK bhi
     write koshish nahi hoti (gate sab guards se pehle hai).
  3. Tasdeeq milne par audit line tools/danger-audit.log me
     likhi jati hai (waqt, op id, amal, model/serial) — dukaan
     ke paas saboot rehta hai ke har khatarnaak write tasdeeq
     ke saath hua.
  4. Tasdeeq aik dafa tick karne se har amal par lagoo NAHI
     samjhi jati — har run ka matlab hai user usi waqt zimmedari
     le raha hai; op apni warning phir bhi hamesha chhapta hai.

Read-side ops (RPMB Read, Sector Read) par ye gate NAHI lagta —
gate sirf destructive writes par hai.
"""

# Bhaari warning — lafz yahi chhapenge, har gated op me.
DANGER_WARNING = (
    "⚠️⚠️ KHATARDAR — YE DESTRUCTIVE (KHATARNAAK) WRITE HAI. "
    "Galat data, galat jagah ya galat device par ye amal phone ko "
    "mustaqil tor par kharab (BRICK / secure-boot kharab) kar "
    "sakta hai. Is ki poori zimmedari aap ki apni hai. Aage barhne "
    "se pehle tasdeeq karen ke file/range BILKUL isi device ke "
    "liye hai aur aap ke paas backup maujood hai."
)


def write_audit_line(ctx, action: str) -> bool:
    """tools/danger-audit.log me aik line — (True/False)."""
    try:
        from datetime import datetime

        from core.runner import TOOLS_DIR
        dev = getattr(ctx, "device", None)
        model = ""
        serial = ""
        if dev is not None:
            model = (getattr(dev, "model", "") or
                     getattr(dev, "brand", "") or "")
            serial = getattr(dev, "serial", "") or ""
        op_id = getattr(ctx, "op_id", "") or "unknown"
        line = (f"{datetime.now().isoformat(timespec='seconds')} | "
                f"op={op_id} | action={action} | "
                f"model={model or '-'} | serial={serial or '-'} | "
                "destructive write confirmed by user\n")
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOOLS_DIR / "danger-audit.log", "a",
                  encoding="utf-8") as fh:
            fh.write(line)
        return True
    except Exception:  # noqa: BLE001 — audit gate ko nahi rok sakta
        return False


def danger_gate(ctx, action: str) -> bool:
    """Warning chhapo + tasdeeq check karo.

    action: amal ka naam jo warning/audit me ayega
    (masalan "RPMB WRITE", "RAW SECTOR WRITE").

    True = tasdeeq maujood hai, aage barho.
    False = tasdeeq nahi — op ko yahin ruk jana chahiye
    (guided stop; device par koi koshish nahi hui).
    """
    ctx.log("=" * 72, "WARN")
    ctx.log(DANGER_WARNING, "WARN")
    ctx.log(f"Amal: {action}", "WARN")
    ctx.log("=" * 72, "WARN")
    if getattr(ctx, "danger_confirmed", False):
        ctx.log("Tasdeeq mil gayi hai (user ne neeche wale bar ki "
                "khatarnaak-write tasdeeq ON ki hai) — aage barh "
                "rahe hain.", "INFO")
        if write_audit_line(ctx, action):
            ctx.log("Audit: ye tasdeeq tools/danger-audit.log me "
                    "mehfooz kar di gayi hai.", "INFO")
        return True
    ctx.log("TASADEEQ NAHI MILI — destructive write yahin ROK di "
            "gayi hai. Ye koi error nahi hai, ye gate hai: pehle "
            "window ke neeche wale bar me '⚠ Tasdeeq (KHATARNAAK "
            "write)' wali checkbox ON karen, phir dobara chalayen. "
            "Baghair tasdeeq device par AIK bhi write koshish "
            "nahi hogi.", "WARN")
    return False
