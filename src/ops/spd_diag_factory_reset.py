"""
spd_diag_factory_reset.py — Diag Factory Reset (bina FDL/PAC).

TSM PRO 2026.08.15 ka precedent: "Factory Reset Unisoc Devices
via Diag Mode" (+ UMT Unisoc v1.7 "Safe Format"). RESEARCH-2
§8.5 / §9.2. Is op ka rasta:

  1. Pehle backup warning + tasdeeq — data wipe hoga:
     pre_reset_honesty (finance/MDM label + live check jahan
     mumkin) AUR danger_gate (KHATARNAAK-write tasdeeq, audit
     log). Dono ke baghair port ki taraf AIK qadam bhi nahi.
  2. Shared Diag-session helper FRP-erase op se (ops module ka
     _find_port + _identify — project me cross-op import ka
     wahi pattern jo qc_qcn_restore / mtk_nv_restore istemal
     karte hain): Diag port autodetect → identify (AT, public).
  3. Reset ki koshish core/spd_diag.py ke verified-command table
     se — table aaj KHALI hai (TSM ke Diag command bytes closed
     hain; koi public byte-level spec nahi mili). Is liye op aaj
     imaandar FAIL deta hai (bench-capture rehnumai + working
     FDL alternative ke saath). Data wipe ke naam par koi byte
     port par nahi jata.
  4. Jab bench-capture se table me entry aye gi, wahi op asal
     koshish karega aur jawab verify karega — phir result_label
     (USERDATA-LEVEL RESET) lagega.

Working alternative (aaj, asal): 'Unisoc Factory Reset (FDL)'
(spd_reset) — userdata (+ metadata) erase, FDL session se.
NV/prodnv ko reset NAHI chhuta — IMEI/cert mehfooz rehta hai.
"""

from core import spd_diag
from core.danger_gate import danger_gate
from core.reset_honesty import pre_reset_honesty, result_label
from ops.spd_diag_frp_erase import _find_port, _identify, _wait_seconds

OP = {
    "id": "spd_diag_factory_reset",
    "category": "SPD / Unisoc",
    "name": "Diag Factory Reset — Bina FDL/PAC",
    "engine": "spd_diag",
    "modes": ("SPD",),
    "server_required": False,
}


def run(ctx) -> bool:
    ctx.log("Diag Factory Reset — bina FDL/PAC (TSM PRO 2026.08.15 "
            "wali Diag-mode tartib). Pehle warning + tasdeeq, "
            "phir Diag session, phir reset ki koshish.", "INFO")
    # -- 1. Backup warning + tasdeeq (port chhune se PEHLE) ------
    _hon = pre_reset_honesty(ctx)
    ctx.log("⚠️ BACKUP WARNING: factory reset se phone ka SARA "
            "user data jayega — photos, apps, accounts, messages. "
            "Aage barhne se pehle backup le lo (agar phone khulta "
            "ho). NV/prodnv ko reset nahi chhuta — IMEI/cert "
            "mehfooz rahega.", "WARN")
    if not danger_gate(ctx, "DIAG FACTORY RESET (userdata wipe)"):
        return False
    if ctx.is_cancelled():
        ctx.log("User ne rok diya — factory reset nahi hua.", "WARN")
        return False

    # -- 2. Shared Diag helper: port + identify -------------------
    ctx.progress(10, "Diag port dhoondha ja raha hai...")
    try:
        found = _find_port(ctx, _wait_seconds(ctx))
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return False
    if ctx.is_cancelled():
        ctx.log("User ne rok diya — factory reset nahi hua.", "WARN")
        return False
    if found is None:
        ctx.log("Diag port waqt ke andar nahi mila. Check karo: "
                "SPRD driver install hai, phone ON tha (ya band "
                "halat me boot key dabaye hue laga tha), cable "
                "durust hai.", "ERROR")
        return False
    port, desc = found
    ctx.log(f"Diag port mil gaya: {port} ({desc or 'SPRD Diag'})", "OK")

    session = spd_diag.DiagSession(port)
    try:
        session.open()
    except spd_diag.DiagError as e:
        ctx.log(str(e), "ERROR")
        return False
    try:
        ident = _identify(ctx, session)
        if ident is None:
            return False
        # -- 3. Reset ki koshish (verified table se) --------------
        ctx.progress(60, "Diag factory reset ki koshish ho rahi hai...")
        ok, evidence = spd_diag.attempt_diag_factory_reset(session, ident)
        if not ok:
            ctx.log("Diag factory reset NAHI ho saka — imaandar "
                    "FAIL (jhooti SUCCESS nahi; data wipe ke naam "
                    "par koi byte port par nahi gaya).", "ERROR")
            ctx.log(evidence, "WARN")
            ctx.log("Aaj ka working rasta: 'Unisoc Factory Reset "
                    "(FDL)' op (spd_reset) — FDL session se "
                    "userdata (+ metadata) erase, usi phone par. "
                    "Wo op chalao.", "INFO")
            return False
        ctx.progress(95, "Diag factory reset mukammal")
        ctx.log(evidence, "OK")
        ctx.log("Factory reset ka jawab verify hua — phone restart "
                "ho kar setup wizard par ayega.", "OK")
        result_label(ctx, _hon)
        return True
    finally:
        session.close()
