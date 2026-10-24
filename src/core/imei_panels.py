"""imei_panels.py — UNLOCK page ke naye panels (2026-10-24, Hamza ke hukm).

Teen panels, sab main.py se aik hook se jurte hain (koi maujooda
layout nahi toota):

1. Phone Information panel — Read Info / connect ke baad khud bhar
   jata hai (App.set_device se refresh hota hai). Log neeche hi
   rehta hai, tafseel ke liye.

2. Dedicated IMEI section — MODEL LIST SE AZAD. IMEI A / IMEI B
   + tasdeeq checkbox + "Restore Original IMEI" (chip ke hisab se
   khud route) + META IMEI Write + DIAG subsection (SPD).
   MDM list me model ho ya na ho — phone connect ho to kaam hoga;
   chip live detection (device panel) se pehchana jata hai, kisi
   list selection se nahi.

3. Brand-wise pages — har company ka apna page. Har page par SIRF
   wohi functions jo MEER ke engine se waqai chalte hain; jis brand
   ka alag engine nahi, us par saaf label + aam (ADB/Fastboot) ops.
   Server-required stubs button nahi, label hain (🔒 SERVER REQUIRED).

Non-negotiables (yahan bhi laagu):
  - NO-LAUNCHER: ye panels sirf maujooda ops chalate hain
    (app._run_action) — koi bahari tool kabhi nahi khulta.
  - IMEI = sirf dabbe/sticker wala ASAL IMEI; warning gate +
    tasdeeq checkbox + backup-first + read-back verify ops ke
    andar hai; mismatch / 000000 / null = FAIL, kabhi nakli SUCCESS
    nahi.
  - SPD Diag write imaandari: SPRD diag-channel NV write public
    nahi (WRITE_VIA_DIAG_AVAILABLE = False) — DIAG subsection
    connect + IMEI state check karta hai, asal SPD write Cert
    (prodnv) Restore se hoti hai; ye baat panel par likhi hai.
"""

import re
import tkinter as tk

# Rang main.py ke barabar (main se import nahi — circular import se
# bachne ke liye yahan dohrane hain; tabdeel hon to dono jagah).
BG = "#14181f"
PANEL = "#1b212b"
PANEL2 = "#202834"
FG = "#e6e9ee"
MUTED = "#8b95a5"
ACCENT = "#ffa028"
GREEN = "#3fb950"
WARN_FG = "#fbbf24"

IMEI_WARNING = (
    "⚠ Sirf phone ke DABBE / STICKER wala ASAL IMEI likho. "
    "Doosra IMEI likhna JURM hai."
)

# ---------------------------------------------------------------------------
# Chip family detection (live device se — kisi list selection se nahi)
# ---------------------------------------------------------------------------

_SPD_CHIP_RES = re.compile(r"UNISOC|SPRD|UMS\d+|TIGER", re.I)


def detect_family(device):
    """'mtk' | 'spd' | None — mode + chip string se (live detection)."""
    if device is None:
        return None
    mode = (getattr(device, "mode", "") or "").upper()
    chip = (getattr(device, "chip", "") or "").upper()
    if mode == "SPD" or _SPD_CHIP_RES.search(chip) \
            or chip.startswith("SC"):
        return "spd"
    if mode in ("BROM", "PRELOADER", "META") \
            or "MT" in chip or "HELIO" in chip \
            or "DIMENSITY" in chip or "MEDIATEK" in chip:
        return "mtk"
    return None


# ---------------------------------------------------------------------------
# 1. Phone Information panel
# ---------------------------------------------------------------------------

_INFO_FIELDS = (("Brand", "brand"), ("Model", "model"),
                ("Chip", "chip"), ("Mode", "mode"),
                ("Port", "port"), ("Android", "android"),
                ("Serial", "serial"), ("Detail", "detail"))


def build_phone_info_panel(parent, app):
    """LabelFrame + refresh(dev) — App.set_device se call hota hai."""
    frame = tk.LabelFrame(parent, text=" PHONE INFORMATION ",
                          bg=PANEL, fg=MUTED, bd=1,
                          font=("Segoe UI", 9, "bold"))
    labels = {}
    for i, (title, key) in enumerate(_INFO_FIELDS):
        col = (i % 4) * 2
        row = i // 4
        tk.Label(frame, text=f"{title}:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=row, column=col,
                                            sticky="e",
                                            padx=(10, 2), pady=2)
        val = tk.Label(frame, text="—", bg=PANEL, fg=FG,
                       font=("Segoe UI", 9, "bold"))
        val.grid(row=row, column=col + 1, sticky="w", pady=2)
        labels[key] = val

    def refresh(dev):
        vals = {}
        if dev is not None:
            vals = {"brand": getattr(dev, "brand", ""),
                    "model": getattr(dev, "model", ""),
                    "chip": getattr(dev, "chip", ""),
                    "mode": getattr(dev, "mode", ""),
                    "port": getattr(dev, "port", ""),
                    "android": getattr(dev, "android", ""),
                    "serial": getattr(dev, "serial", ""),
                    "detail": getattr(dev, "detail", "")}
        for key, lbl in labels.items():
            try:
                lbl.configure(text=vals.get(key) or "—")
            except tk.TclError:
                pass

    frame.refresh = refresh
    return frame, refresh


# ---------------------------------------------------------------------------
# 2. Dedicated IMEI section (model-list se azad)
# ---------------------------------------------------------------------------

def _run_op(app, op_id):
    """Op module dhoondh kar chalao; na mile to log me saaf wajah."""
    module = None
    try:
        module = app._module_by_id(op_id)
    except Exception:  # noqa: BLE001 — module lookup kabhi crash nahi
        module = None
    if module is None:
        app.log_line(f"Operation '{op_id}' is build me nahi mila — "
                     "pehle poora pack (EXE + tools) update karo.",
                     "ERROR")
        return
    app._run_action(module)


def build_imei_section(parent, app):
    """IMEI A/B + tasdeeq + Restore + META Write + DIAG subsection."""
    frame = tk.LabelFrame(
        parent,
        text=" IMEI — Sirf Original (Dabbe / Sticker wala) — "
             "Model list ki zaroorat NAHI ",
        bg=PANEL, fg=MUTED, bd=1, font=("Segoe UI", 9, "bold"))

    tk.Label(frame, text=IMEI_WARNING, bg=PANEL, fg=WARN_FG,
             wraplength=700, justify="left",
             font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8,
                                                pady=(4, 2))
    # IMEI fields — app par vars (taake _collect_op_args inhe parh sake)
    app.imei_sec_var1 = tk.StringVar()
    app.imei_sec_var2 = tk.StringVar()
    row = tk.Frame(frame, bg=PANEL)
    row.pack(fill="x", padx=8, pady=2)
    for title, var in (("IMEI A:", app.imei_sec_var1),
                       ("IMEI B:", app.imei_sec_var2)):
        tk.Label(row, text=title, bg=PANEL, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(side="left",
                                                    padx=(0, 2))
        tk.Entry(row, textvariable=var, bg=PANEL2, fg=FG,
                 insertbackground=FG, relief="flat",
                 font=("Consolas", 10), width=18).pack(
                     side="left", padx=(0, 14))

    app.imei_sec_confirm_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame,
        text="Tasdeeq: ye IMEI is phone ke DABBE / STICKER wala "
             "ASAL IMEI hai — doosra IMEI likhna JURM hai",
        variable=app.imei_sec_confirm_var, bg=PANEL, fg=FG,
        selectcolor=PANEL2, activebackground=PANEL,
        activeforeground=FG, font=("Segoe UI", 8),
        anchor="w").pack(anchor="w", padx=8, pady=(2, 4))

    def _auto_restore():
        """Chip ke hisab se khud route: MTK -> native META op;
        SPD -> Switch to Diag (pehla qadam; write Cert Restore se);
        namaloom -> guide (pehle Read Info / connect)."""
        fam = detect_family(getattr(app, "device", None))
        if fam == "mtk":
            _run_op(app, "mtk_meta_imei_restore")
        elif fam == "spd":
            app.log_line(
                "SPD phone hai — typed IMEI seedha Diag se nahi "
                "likha jata (protocol public nahi). Pehla qadam "
                "Switch to Diag chal raha hai (IMEI state check); "
                "asal write neeche DIAG subsection se Cert "
                "Restore ke zariye hogi.", "WARN")
            _run_op(app, "spd_switch_diag")
        else:
            app.log_line(
                "Chip pehchana nahi gaya — pehle phone connect "
                "karo aur Read Info chalao (chip + mode panel me "
                "aane ke baad ye button khud sahi rasta chunega). "
                "Ya seedha META IMEI Write / DIAG subsection ka "
                "button dabao.", "WARN")

    btnrow = tk.Frame(frame, bg=PANEL)
    btnrow.pack(fill="x", padx=8, pady=(0, 2))
    tk.Button(btnrow, text="Restore Original IMEI",
               bg=ACCENT, fg="#111", relief="flat",
               font=("Segoe UI", 9, "bold"), padx=10, pady=4,
               command=_auto_restore).pack(side="left", padx=(0, 6))
    tk.Button(btnrow, text="META IMEI Write",
               bg=PANEL2, fg=FG, relief="flat",
               font=("Segoe UI", 9, "bold"), padx=10, pady=4,
               command=lambda: _run_op(
                   app, "mtk_meta_imei_restore")).pack(
                       side="left", padx=(0, 6))
    tk.Label(btnrow, text="MTK: META session se nvdata me write + "
                          "read-back verify. Backup pehle khud banta hai.",
             bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(
                 side="left")

    # --- DIAG subsection (SPD / Unisoc) ---
    diag = tk.LabelFrame(frame, text=" DIAG IMEI (SPD / Unisoc) ",
                         bg=PANEL, fg=MUTED, bd=1,
                         font=("Segoe UI", 9, "bold"))
    diag.pack(fill="x", padx=8, pady=(6, 6))
    tk.Label(diag,
             text="Tartib: Switch Diag -> IMEI state check -> Cert "
                  "Backup -> Cert Restore (write). SPD me Diag se "
                  "seedha IMEI write public nahi hai — is liye asal "
                  "write Cert (prodnv) Restore se hoti hai; ye koi "
                  "nakli write nahi, wahi rasta hai jo field me "
                  "kaam karta hai.",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=2)
    drow = tk.Frame(diag, bg=PANEL)
    drow.pack(fill="x", padx=8, pady=(0, 2))
    tk.Button(drow, text="Switch to Diag (Connect + IMEI State)",
               bg=PANEL2, fg=FG, relief="flat",
               font=("Segoe UI", 8, "bold"), padx=8, pady=4,
               command=lambda: _run_op(app, "spd_switch_diag")).pack(
                   side="left", padx=(0, 6))
    tk.Button(drow, text="Backup Cert (prodnv)",
               bg=PANEL2, fg=FG, relief="flat",
               font=("Segoe UI", 8, "bold"), padx=8, pady=4,
               command=lambda: _run_op(app, "spd_cert_backup")).pack(
                   side="left", padx=(0, 6))
    tk.Button(drow, text="DIAG IMEI Write — Cert Restore se",
               bg=PANEL2, fg=FG, relief="flat",
               font=("Segoe UI", 8, "bold"), padx=8, pady=4,
               command=lambda: _run_op(app, "spd_cert_restore")).pack(
                   side="left", padx=(0, 6))
    tk.Label(diag,
             text="Note: Cert Restore KHATARNAAK write hai — "
                  "neeche PARAMS bar ki ⚠ tasdeeq bhi ON karni "
                  "hogi, warna gate rok dega. Restore ke baad "
                  "*#06# se dabbe wale number se milao.",
             bg=PANEL, fg=WARN_FG, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 4))
    return frame


# ---------------------------------------------------------------------------
# 3. Brand-wise pages
# ---------------------------------------------------------------------------

# Aam ops (har brand page par jo engine nahi rakhta, wahan bhi sachay
# tareeqe se dikhaye jate hain — ye ADB/Fastboot par chalte hain).
_GENERIC_OPS = ("adb_info", "adb_reboot", "fastboot_info",
                "fastboot_frp", "fastboot_reset")

_TRANSSION_OPS = (
    "mdm_adb_check", "mdm_app_profiles", "mdm_finance_check",
    "mdm_library", "mdm_meta_guide", "mdm_payjoy",
    "mdm_proinfo_backup", "mdm_proinfo_write",
    "mdm_security_plugin", "meta_disable_adb", "meta_enable_adb",
    "meta_enter", "meta_frp_erase", "meta_factory_reset",
    "meta_gpt_read", "meta_poweroff", "meta_read_info",
    "meta_reboot_fastboot", "meta_reboot_normal",
    "meta_restore_patch", "meta_plugin_patch",
    "meta_ubl_unlock", "meta_ubl_restore",
)

_MTK_OPS = (
    "mtk_info", "mtk_backup", "mtk_identify_backup",
    "mtk_bypass_chain", "mtk_nv_backup", "mtk_nv_restore",
    "mtk_nv_format", "mtk_frp_reset", "mtk_frp_only",
    "mtk_reset_only", "mtk_restore_backup", "mtk_flash",
    "mtk_bl_unlock", "mtk_bl_lock", "mtk_scatter_creator",
    "mtk_meta_imei_restore", "mtk_sn_writer",
    "mtk_rpmb_read", "mtk_rpmb_write", "mtk_rpmb_erase",
)

_SPD_OPS = (
    "spd_switch_diag", "spd_cert_backup", "spd_cert_restore",
    "spd_frp", "spd_reset", "spd_readback",
    "spd_frp_pac_guide", "spd_pac_builder", "spd_launcher",
)

_QC_OPS = (
    "qc_edl_info", "qc_edl_frp", "qc_edl_reset", "qc_edl_flash",
    "qc_edl_backup", "qc_efs_backup", "qc_efs_restore",
    "qc_qcn_backup", "qc_qcn_restore", "qc_diag_enable",
    "qc_loader_library", "qc_sector_read", "qc_sector_write",
)

_SAMSUNG_OPS = (
    "samsung_frp_router", "samsung_firmware_info",
    "samsung_flash", "samsung_flash_keepdata",
    "samsung_kg_status",
)

_XIAOMI_OPS = ("xiaomi_miassistant",)

# (key, title, op_ids, note, stub_labels)
# stub_labels: (name, reason) — button nahi, sirf saaf label.
BRAND_DEFS = (
    ("infinix", "Infinix", _TRANSSION_OPS,
     "Transsion MDM specialty: yehi page Infinix ka asal kaam hai. "
     "Chip ke hisab se MTK / SPD pages ke ops bhi isi phone par "
     "chal sakte hain (chip live detection se confirm karo).",
     ()),
    ("tecno", "Tecno", _TRANSSION_OPS,
     "Transsion MDM specialty: Tecno ka asal kaam isi page par. "
     "Chip ke hisab se MTK / SPD pages ke ops bhi istemal ho "
     "sakte hain.",
     ()),
    ("itel", "Itel", _TRANSSION_OPS,
     "Transsion MDM specialty: Itel ka asal kaam isi page par. "
     "Unisoc (SPD) Itel models ke liye SPD page bhi dekho.",
     ()),
    ("samsung", "Samsung", _SAMSUNG_OPS,
     "Samsung ke liye maujooda engine: FRP router, firmware info, "
     "flash (data ke saath/baghair), KG status.",
     (("FRP Remove (Latest Security)", "SERVER REQUIRED"),
      ("Carrier / Network Unlock", "SERVER REQUIRED"))),
    ("xiaomi", "Xiaomi", _XIAOMI_OPS + _GENERIC_OPS,
     "Xiaomi ke liye MiAssistant + aam Fastboot/ADB ops. "
     "EDL auth wale kaam server ke baghair nahi hote.",
     ()),
    ("oppo", "Oppo / Realme", _GENERIC_OPS,
     "Oppo/Realme ke liye alag engine abhi nahi hai — ye aam "
     "ADB/Fastboot ops hain. MTK/SPD chip ho to us chipset page "
     "ke ops istemal karo (chip panel me nazar ayega).",
     ()),
    ("vivo", "Vivo", _GENERIC_OPS,
     "Vivo ke liye alag engine abhi nahi hai — ye aam "
     "ADB/Fastboot ops hain. Chip ke hisab se MTK/SPD/Qualcomm "
     "page dekho.",
     ()),
    ("huawei", "Huawei", _GENERIC_OPS,
     "Huawei ke liye alag engine abhi nahi hai (Kirin chips "
     "is engine se nahi khulte) — ye aam ADB/Fastboot ops hain.",
     ()),
    ("mtk", "MTK", _MTK_OPS,
     "MediaTek chipset page: BROM/META ops. SN Writer wala button "
     "RETIRED hai — wo dabane par native META IMEI rasta batayega, "
     "koi bahari tool nahi kholega.",
     (("SLA/DAA Auth Bypass (New Chipsets)", "SERVER REQUIRED"),)),
    ("spd", "SPD / Unisoc", _SPD_OPS,
     "Unisoc (SPD) chipset page: tartib Switch Diag -> Cert "
     "Backup -> Cert Restore -> FRP. FDL wale ops ko model ka "
     "PAC chahiye (FDL kabhi bundle nahi hota).",
     ()),
    ("qualcomm", "Qualcomm", _QC_OPS,
     "Qualcomm EDL page: loader library + EDL/QCN/EFS ops. "
     "Auth wali flashing server ke baghair nahi hoti.",
     (("Auth Flashing (Oppo/Vivo/Xiaomi EDL)", "SERVER REQUIRED"),)),
    ("all", "Sab Ops", (),
     "Poori fehrist bayein OPERATIONS tree me hai — wahan har "
     "category (MTK / MDM / Qualcomm / Samsung / Xiaomi / SPD / "
     "Utility) khuli hui hai.",
     ()),
)


def _scrollable(parent):
    """Canvas + inner frame (brand content ke liye)."""
    canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0)
    scroll = tk.Scrollbar(parent, orient="vertical",
                          command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=PANEL)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas(_event=None):
        canvas.itemconfig(win, width=canvas.winfo_width())

    inner.bind("<Configure>", _on_inner)
    canvas.bind("<Configure>", _on_canvas)

    def _wheel(event):
        try:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    canvas.bind_all("<MouseWheel>", _wheel)
    return inner


def build_brand_pages(parent, app):
    """Brand tab row + scrollable content frame. IMEI section is
    frame ke neeche alag pack hota hai (har brand page par wahi)."""
    frame = tk.LabelFrame(parent, text=" BRAND PAGES ",
                          bg=PANEL, fg=MUTED, bd=1,
                          font=("Segoe UI", 9, "bold"))
    tabrow = tk.Frame(frame, bg=PANEL)
    tabrow.pack(fill="x", padx=6, pady=(4, 2))
    content = tk.Frame(frame, bg=PANEL)
    content.pack(fill="both", expand=True, padx=6, pady=(0, 4))
    inner = _scrollable(content)

    state = {"current": None, "btns": {}}

    def _render(key):
        state["current"] = key
        for k, btn in state["btns"].items():
            btn.configure(bg=ACCENT if k == key else PANEL2,
                          fg="#111" if k == key else FG)
        for child in inner.winfo_children():
            child.destroy()
        key_def = next(d for d in BRAND_DEFS if d[0] == key)
        _key, _title, op_ids, note, stubs = key_def
        if note:
            tk.Label(inner, text=note, bg=PANEL, fg=MUTED,
                     wraplength=680, justify="left",
                     font=("Segoe UI", 8)).pack(anchor="w",
                                                pady=(0, 6))
        grid = tk.Frame(inner, bg=PANEL)
        grid.pack(fill="x")
        col = 0
        row_i = 0
        for op_id in op_ids:
            module = None
            try:
                module = app._module_by_id(op_id)
            except Exception:  # noqa: BLE001
                module = None
            if module is None:
                continue
            name = module.OP.get("name", op_id)
            btn = app._action_button(grid, name, module)
            btn.grid(row=row_i, column=col, sticky="ew",
                     padx=2, pady=2)
            col += 1
            if col >= 2:
                col = 0
                row_i += 1
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        for name, reason in stubs:
            tk.Label(inner, text=f"🔒 {name} — {reason} "
                                 "(paid server ke baghair nahi "
                                 "chalega)",
                     bg=PANEL, fg=MUTED, wraplength=680,
                     justify="left", font=("Segoe UI", 8)).pack(
                         anchor="w", pady=(6, 0))
        if key != "all":
            tk.Label(inner,
                     text="IMEI ka kaam isi page ke neeche wale "
                          "IMEI section se hoga (model list ki "
                          "zaroorat nahi).",
                     bg=PANEL, fg=MUTED, wraplength=680,
                     justify="left",
                     font=("Segoe UI", 8)).pack(anchor="w",
                                                pady=(8, 0))

    for key, title, _ops, _note, _stubs in BRAND_DEFS:
        btn = tk.Button(tabrow, text=title, bg=PANEL2, fg=FG,
                        relief="flat", font=("Segoe UI", 8, "bold"),
                        padx=8, pady=2,
                        command=lambda k=key: _render(k))
        btn.pack(side="left", padx=(0, 4))
        state["btns"][key] = btn
    _render("infinix")  # Transsion pehle (dukaan ka asal kaam)
    frame.render_brand = _render
    return frame
