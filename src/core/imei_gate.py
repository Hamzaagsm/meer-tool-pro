"""
imei_gate.py — IMEI write gate (Hamza ki product shart, 2026-10-22).

Usool: jo bhi op/flow IMEI (ya IMEI wala NV/cert) LIKHNE ya RESTORE
karne jaye, us se PEHLE:
  1. Live log me ye warning wazeh tor par chhapegi — hamesha, har
     dafa, bina kisi shortcut ke.
  2. User ki explicit tasdeeq (confirmation) lazmi hogi — GUI me
     Network tab ka tasdeeq checkbox `ctx.imei_write_confirmed`
     ban kar ata hai. Tasdeeq na ho to op yahin RUK jata hai: ye
     guided STOP hai, error nahi, aur koi write koshish bhi nahi
     hoti (gate provider/Luhn/backup — har cheez se pehle hai).

Read/verify/backup side (Read IMEI, Backup Cert) par ye gate
NAHI lagta — gate sirf writes par hai.

Tasdeeq milne par aik audit line tools/imei-audit.log me bhi
likhi jati hai (research §3.5 point 5): tareekh/waqt, op id,
device model/serial — kal ko dukaan ke paas saboot ho ke har
IMEI write tasdeeq ke saath hua tha. Audit likhne ki nakami
gate ko NAHI rokti (try/except ke andar hai).
"""

# Hamza ke hukm ki exact warning — lafz-ba-lafz yahi chhapegi.
IMEI_WARNING = (
    "⚠️ KHABARDAR: Sirf phone ke DABBE / STICKER par likha hua ASAL "
    "IMEI hi likhen. Kisi doosre phone ka IMEI likhna JURM hai. "
    "Ghalat IMEI ki poori zimmedari aap ki apni hai."
)


def write_audit_line(ctx) -> bool:
    """tools/imei-audit.log me aik line — (True/False = likhi gayi ya nahi)."""
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
                f"op={op_id} | model={model or '-'} | "
                f"serial={serial or '-'} | IMEI write confirmed "
                "(original-restore)\n")
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOOLS_DIR / "imei-audit.log", "a",
                  encoding="utf-8") as fh:
            fh.write(line)
        return True
    except Exception:  # noqa: BLE001 — audit gate ko nahi rok sakta
        return False


def imei_write_gate(ctx) -> bool:
    """Warning chhapo + tasdeeq check karo.

    True = tasdeeq maujood hai, aage barho.
    False = tasdeeq nahi — op ko yahin ruk jana chahiye (guided stop).
    """
    ctx.log("=" * 72, "WARN")
    ctx.log(IMEI_WARNING, "WARN")
    ctx.log("=" * 72, "WARN")
    if getattr(ctx, "imei_write_confirmed", False):
        ctx.log("Tasdeeq mil gayi hai (user ne confirm kiya hai ke "
                "IMEI dabbe/sticker wala asal IMEI hai) — aage barh "
                "rahe hain.", "INFO")
        if write_audit_line(ctx):
            ctx.log("Audit: ye tasdeeq tools/imei-audit.log me "
                    "mehfooz kar di gayi hai.", "INFO")
        return True
    ctx.log("TASADEEQ NAHI MILI — IMEI write yahin ROK di gayi hai. "
            "Ye koi error nahi hai, ye gate hai: pehle Network tab "
            "me tasdeeq wala checkbox ON karen (ke ye IMEI is phone "
            "ke dabbe/sticker wala asal IMEI hai), phir dobara "
            "chalayen. Baghair tasdeeq koi write shuru nahi hogi.",
            "WARN")
    return False
