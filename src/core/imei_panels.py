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
   Tab row + content dono scroll hote hain (chhoti window par bhi
   koi tab/button kata hua nahi rehta).
   2026-10-24 (Hamza ka hukm): har brand page par us brand ke
   MODELS ki fehrist bhi hai (search ke saath) — model chunne par
   us ki chip/route nazar ati hai aur reset/FRP buttons khulte
   hain. Buttons hamesha CONNECTED phone par chalte hain (chip
   live detection se); phone connect na ho to connect-first guide
   ati hai, kabhi nakli run nahi hota.

4. FRP section — IMEI section wala aik-click big-button pattern:
   FRP Tools screen ke functions bare buttons ki shakal me; sirf
   wohi FRP ops jo engine se waqai chalte hain, server-required
   sirf label hai.

5. No-button entry (2026-10-24, Hamza ki pakar): META/DIAG me
   koi button nahi — IMEI section me "Enter META Mode (ADB —
   bina button)" button + DIAG subsection me ON-rasta note;
   META/DIAG guide texts se Vol-combo hidayat hatayi gayi (BROM
   flows ki hidayat wahi ki wahi hai).

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
        text=" IMEI Patch — Sirf Original (Dabbe / Sticker wala) ",
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

    # META entry — BINA button wala rasta (Hamza ki pakar, 2026-10-24)
    mrow = tk.Frame(frame, bg=PANEL)
    mrow.pack(fill="x", padx=8, pady=(0, 2))
    tk.Button(mrow, text="Enter META Mode (ADB — bina button)",
               bg=PANEL2, fg=FG, relief="flat",
               font=("Segoe UI", 9, "bold"), padx=10, pady=4,
               command=lambda: _run_op(app, "meta_enter_adb")).pack(
                   side="left", padx=(0, 6))
    tk.Label(mrow, text="Phone ON + ADB se META me jao — META me Vol "
                        "combo nahi chahiye (wo sirf BROM ke liye hai).",
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
    tk.Label(diag,
             text="Bina button: phone ON rakho — Switch Diag Diag "
                  "port khud pakar lega; band phone + boot key "
                  "sirf fallback hai.",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
             font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8,
                                                pady=(0, 2))
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


def build_partition_manager_panel(parent, app):
    """Partition Manager panel — GPT-driven partition view
    (Round 2, §8.13).

    META session se GPT parh kar fehrist dikhata hai (naam + size
    + safety class); har partition par Read / Write / Erase —
    per-partition button op_for() factory se banta hai (wohi
    pattern jo model tab ka download_frp_op istemal karta hai),
    is liye muntakhib partition seedha op ko bandha hota hai,
    PARAMS bar se kuch nahi mangta.

    Hifazat panel par likhi hai: backup-first (write/erase se
    pehle poori partition backup hoti hai), preloader/nvram/
    nvdata/seccfg/proinfo/lk/boot/vbmeta/tee par ERASE mana hai,
    write/erase par PARAMS bar ki ⚠ tasdeeq lazmi hai. Panel
    sirf maujooda ops chalata hai (app._run_action) — koi bahari
    tool kabhi nahi khulta (NO-LAUNCHER).
    """
    from core import meta_gpt  # noqa: E402 — lazy (circular se bachao)
    from ops import meta_partition_manager as _pm  # noqa: E402

    frame = tk.LabelFrame(
        parent,
        text=" PARTITION MANAGER (META Mode) — GPT-driven ",
        bg=PANEL, fg=MUTED, bd=1, font=("Segoe UI", 9, "bold"))

    tk.Label(frame,
             text="Naye models pehle: Helio G200/G100 (Hot 60 Pro/Pro+, "
                  "Spark 40 Pro+, Camon 50/50 Pro) par META entry khuli "
                  "hai. Pehle GPT parho, phir partition chuno — GPT se "
                  "bahir koi naam chhua nahi jayega.",
             bg=PANEL, fg=FG, wraplength=700, justify="left",
             font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8,
                                                pady=(4, 2))
    tk.Label(frame,
             text="⛔ CRITICAL (preloader / nvram / nvdata / lk / boot / "
                  "vbmeta / tee) = ERASE MANA (brick). ⚠ PROTECTED = "
                  "security state. Write/Erase se pehle poori partition "
                  "ka backup khud banta hai; Write ki file tools/"
                  "partitions/ me SIRF AIK .bin honi chahiye.",
             bg=PANEL, fg=WARN_FG, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 2))
    tk.Label(frame,
             text="Write/Erase KHATARNAAK hain — neeche PARAMS bar ki "
                  "⚠ tasdeeq ON kiye baghair gate rok dega. Read/List "
                  "safe hain (tasdeeq nahi chahiye).",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 4))

    # --- GPT parho + listbox (aakhri GPT read se bharti hai) ---
    app.partition_mgr_name_var = tk.StringVar()
    top = tk.Frame(frame, bg=PANEL)
    top.pack(fill="x", padx=8, pady=(0, 2))
    tk.Button(top, text="GPT Parho (META Mode)",
              bg=ACCENT, fg="#111", relief="flat",
              font=("Segoe UI", 9, "bold"), padx=10, pady=4,
              command=lambda: _run_op(app, "meta_gpt_read")).pack(
                  side="left", padx=(0, 6))
    tk.Button(top, text="↻ Fehrist taza karo",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 8, "bold"), padx=8, pady=4,
              command=lambda: _refill()).pack(side="left", padx=(0, 6))
    tk.Label(top, text="Fehrist aakhri GPT read se bharti hai — "
                       "pehle 'GPT Parho' dabao.",
             bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(
                 side="left")

    list_frame = tk.Frame(frame, bg=PANEL)
    list_frame.pack(fill="x", padx=8, pady=(0, 2))
    list_scroll = tk.Scrollbar(list_frame, orient="vertical")
    list_scroll.pack(side="right", fill="y")
    part_list = tk.Listbox(list_frame, bg=PANEL2, fg=FG,
                           relief="flat", font=("Consolas", 8),
                           height=8, exportselection=False,
                           yscrollcommand=list_scroll.set)
    list_scroll.configure(command=part_list.yview)
    part_list.pack(side="left", fill="x", expand=True)

    shown = {"items": []}

    def _refill():
        part_list.delete(0, "end")
        entries = list(getattr(meta_gpt, "LAST_GPT_ENTRIES", None) or [])
        shown["items"] = entries
        for e in entries:
            cls = _pm.classify_partition(e.get("name", ""))
            tag = {"critical": "⛔ CRITICAL",
                   "protected": "⚠ PROTECTED",
                   "normal": "normal"}[cls]
            part_list.insert(
                "end",
                f"{e.get('name', '')} — "
                f"{_pm.fmt_size(e.get('size_bytes', 0))} [{tag}]")

    def _on_select(_event=None):
        sel = part_list.curselection()
        if not sel:
            return
        entry = shown["items"][sel[0]]
        app.partition_mgr_name_var.set(str(entry.get("name", "")))

    part_list.bind("<<ListboxSelect>>", _on_select)

    # --- Partition naam + per-partition actions ---
    nrow = tk.Frame(frame, bg=PANEL)
    nrow.pack(fill="x", padx=8, pady=(2, 2))
    tk.Label(nrow, text="Partition:", bg=PANEL, fg=FG,
             font=("Segoe UI", 9, "bold")).pack(side="left",
                                                padx=(0, 4))
    tk.Entry(nrow, textvariable=app.partition_mgr_name_var,
             bg=PANEL2, fg=FG, insertbackground=FG, relief="flat",
             font=("Consolas", 10), width=24).pack(side="left",
                                                   padx=(0, 6))
    tk.Label(nrow, text="(listbox se chuno ya naam likho)",
             bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(
                 side="left")

    def _run_partition_action(action):
        name = app.partition_mgr_name_var.get().strip()
        _n, _a, err = _pm.parse_request({}, name, action)
        if err:
            app.log_line(err, "ERROR")
            return
        app._run_action(_pm.op_for(name, action))

    arow = tk.Frame(frame, bg=PANEL)
    arow.pack(fill="x", padx=8, pady=(0, 6))
    tk.Button(arow, text="Read (backup me save)",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 9, "bold"), padx=10, pady=4,
              command=lambda: _run_partition_action("read")).pack(
                  side="left", padx=(0, 6))
    tk.Button(arow, text="⚠ Write (backup-first)",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 9, "bold"), padx=10, pady=4,
              command=lambda: _run_partition_action("write")).pack(
                  side="left", padx=(0, 6))
    tk.Button(arow, text="⚠ Erase (backup-first)",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 9, "bold"), padx=10, pady=4,
              command=lambda: _run_partition_action("erase")).pack(
                  side="left", padx=(0, 6))
    tk.Label(arow, text="Har amal se pehle GPT check hota hai — "
                        "naam GPT me na ho to op ruk jayega.",
             bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(
                 side="left")
    _refill()
    return frame


def build_pta_section(parent, app):
    """PTA Rehnumai — blocked phone ka asal (qanooni) rasta.

    Sirf rehnumai (koi button, koi write nahi): PTA-blocked phone
    ka ek hi asal unblock DIRBS tax hai. Bazaar ke 'patch' tareeqe
    aur doosre ka IMEI likhna yahan sakht mana hai — dono jurm
    hain aur phone dobara block ho jata hai. (Hamza se tay shuda,
    2026-10-24.)"""
    frame = tk.LabelFrame(
        parent,
        text=" PTA Rehnumai — Blocked phone ka asal rasta ",
        bg=PANEL, fg=MUTED, bd=1, font=("Segoe UI", 9, "bold"))
    tk.Label(frame,
             text="PTA-blocked phone ka ek hi asal unblock hai: "
                  "DIRBS tax bharo. SMS 8484 par IMEI bhejo ya "
                  "dirbs.pta.gov.pk par status dekho, phir wahan "
                  "bataya gaya tax ada karo — tax clear hote hi "
                  "phone khud unblock ho jata hai.",
             bg=PANEL, fg=FG, wraplength=700, justify="left",
             font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8,
                                                pady=(4, 2))
    tk.Label(frame,
             text="Bazaar wale 'patch' tareeqe (doosre phone ka IMEI "
                  "likhna ya IMEI badalna) JURM hain — PTA dobara "
                  "block kar deta hai aur phone zabt bhi ho sakta "
                  "hai. MEER me IMEI sirf DABBE / STICKER wala ASAL "
                  "number wapas likha jata hai (upar wala 'IMEI "
                  "Patch — Sirf Original' section) — kabhi kisi "
                  "aur ka number nahi.",
             bg=PANEL, fg=WARN_FG, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 4))
    tk.Label(frame,
             text="Dukaan me customer ko yehi batana: CNIC copy + "
                  "khareed ka saboot (bill/dabba) saath rakho; tax "
                  "ki raqam PTA ki site par IMEI daal kar maloom "
                  "hoti hai — andaze se koi raqam mat batana.",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 6))
    return frame


# ---------------------------------------------------------------------------
# FRP section — IMEI section wala aik-click big-button pattern
# ---------------------------------------------------------------------------

# (label, op_id) — sirf wohi FRP ops jo MEER ke engine se waqai
# chalte hain. Har button apna mode khud check karta hai — phone
# us mode me na ho to op saaf FAIL dega, nakli kaam nahi hoga.
_FRP_BUTTONS = (
    ("FRP Only (MTK — BROM)", "mtk_frp_only"),
    ("FRP Erase + Factory Reset (MTK — BROM)", "mtk_frp_reset"),
    ("FRP Erase (META Mode)", "meta_frp_erase"),
    ("FRP Erase (Unisoc — FDL)", "spd_frp"),
    ("FRP Erase (Fastboot)", "fastboot_frp"),
    ("FRP Erase (Motorola Fastboot)", "moto_fastboot_frp"),
    ("FRP Erase (EDL)", "qc_edl_frp"),
    ("FRP Method Router (Samsung)", "samsung_frp_router"),
    ("Reboot (ADB → Normal)", "adb_reboot"),
    ("Reboot to Normal (META)", "meta_reboot_normal"),
    ("Reboot to Fastboot (META)", "meta_reboot_fastboot"),
)


def build_frp_section(parent, app):
    """FRP Tools screen — IMEI section jaisa aik-click pattern:
    bara button = seedha us ka op, koi lambi list nahi, koi doosra
    tool nahi khulta."""
    frame = tk.LabelFrame(
        parent,
        text=" FRP — aik click (big buttons) ",
        bg=PANEL, fg=MUTED, bd=1, font=("Segoe UI", 9, "bold"))

    tk.Label(frame,
             text="Har button seedha apna FRP op chalata hai — koi "
                  "doosra tool nahi khulta. Sirf wohi FRP buttons "
                  "hain jo MEER ke engine se waqai chalte hain; "
                  "har button apna mode khud check karta hai.",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(4, 2))

    grid = tk.Frame(frame, bg=PANEL)
    grid.pack(fill="x", padx=8, pady=(0, 2))
    col = 0
    row_i = 0
    for label, op_id in _FRP_BUTTONS:
        tk.Button(grid, text=label,
                   bg=PANEL2, fg=FG, relief="flat",
                   font=("Segoe UI", 9, "bold"), padx=10, pady=4,
                   command=lambda oid=op_id: _run_op(app, oid)).grid(
                       row=row_i, column=col, sticky="ew",
                       padx=2, pady=2)
        col += 1
        if col >= 2:
            col = 0
            row_i += 1
    grid.columnconfigure(0, weight=1)
    grid.columnconfigure(1, weight=1)

    tk.Label(frame,
             text="🔒 FRP Remove (Latest Security, Samsung) — "
                  "SERVER REQUIRED (paid server ke baghair nahi "
                  "chalega); is liye is ka button nahi, sirf ye "
                  "label hai.",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(2, 0))
    tk.Label(frame,
             text="QR code / MTP wale FRP tareeqe (doosre tools "
                  "wale) MEER ke engine me nahi hain — is liye "
                  "yahan un ka nakli button nahi hai.",
             bg=PANEL, fg=MUTED, wraplength=700, justify="left",
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
    "meta_enter", "meta_enter_adb", "meta_frp_erase", "meta_factory_reset",
    "meta_gpt_read", "meta_poweroff", "meta_read_info",
    "meta_reboot_fastboot", "meta_reboot_normal",
    "meta_restore_patch", "meta_plugin_patch",
    "meta_ubl_unlock", "meta_ubl_restore",
    "meta_partition_manager", "meta_bootloader_unlock",
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
     (("FRP Remove (Latest Security)", "SERVER REQUIRED — pehle "
      "'FRP Method Router (Samsung)' chalao; sirf latest security "
      "par ruke to server case hai"),
      ("Carrier / Network Unlock", "SERVER REQUIRED — asal rasta "
      "original carrier/operator hai; MEER me free engine rasta "
      "nahi"))),
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
     (("SLA/DAA Auth Bypass (New Chipsets)", "SERVER REQUIRED — "
      "pehle MTK ops tree ka 'Latest Bypass (Auto)' chalao "
      "(payload → carbonara → heapbait); Transsion ho to MDM List "
      "ka TMETA route bhi free rasta hai"),)),
    ("spd", "SPD / Unisoc", _SPD_OPS,
     "Unisoc (SPD) chipset page: tartib Switch Diag -> Cert "
     "Backup -> Cert Restore -> FRP. FDL wale ops ko model ka "
     "PAC chahiye (FDL kabhi bundle nahi hota).",
     ()),
    ("qualcomm", "Qualcomm", _QC_OPS,
     "Qualcomm EDL page: loader library + EDL/QCN/EFS ops. "
     "Auth wali flashing server ke baghair nahi hoti.",
     (("Auth Flashing (Oppo/Vivo/Xiaomi EDL)", "SERVER REQUIRED — "
      "koi free engine rasta nahi; asal rasta brand ka authorized "
      "service center ya authorized account hai"),)),
    ("all", "Sab Ops", (),
     "Poori fehrist bayein OPERATIONS tree me hai — wahan har "
     "category (MTK / MDM / Qualcomm / Samsung / Xiaomi / SPD / "
     "Utility) khuli hui hai.",
     ()),
)


def _scrollable(parent):
    """Canvas + inner frame (brand content ke liye) — vertical +
    horizontal scroll, taake chhoti window (1366x768) par bhi koi
    button kat kar nazar se bahir na rahe."""
    canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0)
    scroll = tk.Scrollbar(parent, orient="vertical",
                          command=canvas.yview)
    hscroll = tk.Scrollbar(parent, orient="horizontal",
                           command=canvas.xview)
    canvas.configure(yscrollcommand=scroll.set,
                     xscrollcommand=hscroll.set)
    scroll.pack(side="right", fill="y")
    hscroll.pack(side="bottom", fill="x")
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


# ---------------------------------------------------------------------------
# 3b. Brand-page model lists (2026-10-24, Hamza ka hukm: "name waheen
# hony chahye taky model select krky reset frp kiya ja saky").
# Pure helpers (GUI se azad — logic tests in par chalte hain):
#   - brand_page_models(models, key): is page ki models (naam se sort).
#   - search_models(models, query): naam/code/chipset par search.
#   - model_reset_frp_op_ids(model): selected model ke reset/FRP ops.
# Imaandari: selection sirf CONTEXT batati hai (chip/route). Buttons
# hamesha CONNECTED phone par chalte hain (app._action_button ->
# runner); phone connect na ho to op ka guard connect-first guide
# de kar FAIL karta hai — kabhi nakli run nahi hota.
# ---------------------------------------------------------------------------

# Brand page key -> DB brand values (Oppo page me Realme bhi, Vivo
# page me iQOO bhi — dono apne bare brand ki family hain).
_BRAND_PAGE_BRANDS = {
    "infinix": ("Infinix",),
    "tecno": ("Tecno",),
    "itel": ("Itel",),
    "samsung": ("Samsung",),
    "xiaomi": ("Xiaomi",),
    "oppo": ("Oppo", "Realme"),
    "vivo": ("Vivo", "iQOO"),
    "huawei": ("Huawei",),
}

# Chipset page key -> DB tag values.
_BRAND_PAGE_TAG_FILTER = {
    "mtk": ("MediaTek",),
    "spd": ("Unisoc", "SPD"),
    "qualcomm": ("Qualcomm",),
}

_MTK_CHIP_RE = re.compile(r"\bMT\d|helio|dimensity|mediatek", re.I)
_SPD_CHIP_RE = re.compile(r"unisoc|\bSC\d{4}\b|\bUMS\d{4}\b|\bT\d{3,4}\b",
                           re.I)

_MTK_RESET_OPS = ("mtk_frp_reset", "mtk_reset_only", "mtk_frp_only")
_SPD_RESET_OPS = ("spd_reset", "spd_frp")
_QC_RESET_OPS = ("qc_edl_reset", "qc_edl_frp")
_SAMSUNG_RESET_OPS = ("samsung_frp_router",)


def brand_page_models(models, key):
    """Is brand/chipset page ki models, naam se sort. 'all' (Sab Ops)
    koi brand nahi — us par [] (poori fehrist bayein MDM tree me
    hai, wahi rehti hai)."""
    if key == "all":
        return []
    brands = _BRAND_PAGE_BRANDS.get(key)
    if brands is not None:
        wanted = {b.lower() for b in brands}
        out = [m for m in models
               if str(m.get("brand", "")).lower() in wanted]
    else:
        tags = _BRAND_PAGE_TAG_FILTER.get(key)
        if not tags:
            return []
        wanted = {t.lower() for t in tags}
        out = [m for m in models
               if wanted & {str(t).lower() for t in m.get("tags", [])}]
    out.sort(key=lambda m: str(m.get("name", "")).lower())
    return out


def search_models(models, query):
    """Naam/code/chipset par case-insensitive search (MDM tree wali
    q-filter jaisa). Khali query par poori fehrist."""
    q = (query or "").strip().lower()
    if not q:
        return list(models)
    return [m for m in models
            if q in " ".join(str(m.get(f, "")) for f in
                             ("name", "code", "chipset")).lower()]


def model_reset_frp_op_ids(model):
    """Selected model ke reset/FRP op ids — chip family se. Chip
    maloom na ho to () — ghalat family ka button dikhane se behtar
    hai ke koi button na dikhe, sirf rehnumai ho."""
    tags = {str(t).lower() for t in model.get("tags", [])}
    chipset = str(model.get("chipset", ""))
    if "mediatek" in tags or _MTK_CHIP_RE.search(chipset):
        return _MTK_RESET_OPS
    if "unisoc" in tags or "spd" in tags or _SPD_CHIP_RE.search(chipset):
        return _SPD_RESET_OPS
    if "qualcomm" in tags or "snapdragon" in chipset.lower():
        return _QC_RESET_OPS
    if str(model.get("brand", "")).lower() == "samsung":
        return _SAMSUNG_RESET_OPS
    return ()


def _brand_page_model_data(app):
    """Brand pages ke liye models — app.mdm_models (startup par load)
    ya, khali ho to, mdm_list se lazy load (app par cache). Kabhi
    exception nahi phenkta — khali fehrist hi sahi."""
    models = list(getattr(app, "mdm_models", None) or [])
    if models:
        return models
    try:
        from core import mdm_list as _mdm_list
        models, _note = _mdm_list.load_models()
        app.mdm_models = models
        return list(models)
    except Exception:  # noqa: BLE001
        return []


def _render_brand_models(inner, app, key):
    """Brand page ke neeche: searchable model list + selection par
    chip/route + reset/FRP buttons. Listbox ka apna scrollbar hai
    (page ke canvas scroll se alag); wheel listbox par usi ko
    scroll karta hai."""
    try:
        from core import mdm_list as _mdm_list
    except Exception:  # noqa: BLE001
        _mdm_list = None

    def _get_models():
        # Har refill par TAAZA data — pehle `models` aik dafa render
        # waqt pakar liye jate the (stale snapshot): startup par DB
        # abhi load na hua ho ya baad me reload ho to fehrist purani
        # rehti thi aur nayi rows page par kabhi nahi ati theen
        # (sirf tab badalne par dobara banti thi). Ab har search /
        # refill par app ki maujooda fehrist dobara parhi jati hai.
        return brand_page_models(_brand_page_model_data(app), key)

    tk.Label(inner, text="MODELS — is page ke models (naam likh kar "
                          "dhoondo, model chuno, phir neeche reset/FRP "
                          "dabao):",
             bg=PANEL, fg=FG, wraplength=680, justify="left",
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
    search_var = tk.StringVar()
    search_row = tk.Frame(inner, bg=PANEL)
    search_row.pack(fill="x", pady=(0, 2))
    tk.Label(search_row, text="Dhoondo:", bg=PANEL, fg=MUTED,
             font=("Segoe UI", 8)).pack(side="left")
    search_entry = tk.Entry(search_row, textvariable=search_var,
                            bg=PANEL2, fg=FG, insertbackground=FG,
                            relief="flat", font=("Segoe UI", 8))
    search_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
    list_frame = tk.Frame(inner, bg=PANEL)
    list_frame.pack(fill="x", pady=(0, 2))
    list_scroll = tk.Scrollbar(list_frame, orient="vertical")
    list_scroll.pack(side="right", fill="y")
    model_list = tk.Listbox(list_frame, bg=PANEL2, fg=FG,
                            relief="flat", font=("Segoe UI", 8),
                            height=10, exportselection=False,
                            yscrollcommand=list_scroll.set)
    list_scroll.configure(command=model_list.yview)
    model_list.pack(side="left", fill="x", expand=True)

    def _list_wheel(event):
        try:
            model_list.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass
        return "break"

    model_list.bind("<MouseWheel>", _list_wheel)
    info_frame = tk.Frame(inner, bg=PANEL)
    info_frame.pack(fill="x", pady=(2, 0))
    btn_frame = tk.Frame(inner, bg=PANEL)
    btn_frame.pack(fill="x", pady=(2, 0))
    tk.Label(inner,
             text="Ye buttons CONNECTED phone par chalte hain — "
                  "phone connect na ho to dabane par connect-first "
                  "guide ayegi, koi nakli run nahi hoga. Model "
                  "chunna sirf context batata hai; chip live "
                  "detection se confirm hoti hai.",
             bg=PANEL, fg=MUTED, wraplength=680, justify="left",
             font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))

    shown = {"items": []}

    def _refill():
        model_list.delete(0, "end")
        shown["items"] = search_models(_get_models(), search_var.get())
        for m in shown["items"]:
            label = (_mdm_list.model_label(m) if _mdm_list is not None
                     else str(m.get("name", "")))
            model_list.insert("end", label)
        for child in info_frame.winfo_children():
            child.destroy()
        for child in btn_frame.winfo_children():
            child.destroy()

    def _on_select(_event=None):
        sel = model_list.curselection()
        if not sel:
            return
        model = shown["items"][sel[0]]
        try:
            app.selected_model = model
        except Exception:  # noqa: BLE001
            pass
        for child in info_frame.winfo_children():
            child.destroy()
        for child in btn_frame.winfo_children():
            child.destroy()
        label = (_mdm_list.model_label(model) if _mdm_list is not None
                 else str(model.get("name", "")))
        tk.Label(info_frame, text=label, bg=PANEL, fg=FG,
                 wraplength=680, justify="left",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tags = "  ".join(f"[{t}]" for t in model.get("tags", []))
        if tags:
            tk.Label(info_frame, text=tags, bg=PANEL, fg=ACCENT,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
        if _mdm_list is not None:
            for line in _mdm_list.route_hint_lines(model):
                tk.Label(info_frame, text=line, bg=PANEL, fg=MUTED,
                         wraplength=680, justify="left",
                         font=("Segoe UI", 8)).pack(anchor="w")
        op_ids = model_reset_frp_op_ids(model)
        if not op_ids:
            tk.Label(btn_frame,
                     text="Is model ki chip maloom nahi — phone "
                          "connect karo, live detection se sahi "
                          "rasta khulega; neeche FRP section se bhi "
                          "reset/FRP chala sakte ho.",
                     bg=PANEL, fg=WARN_FG, wraplength=680,
                     justify="left",
                     font=("Segoe UI", 8)).pack(anchor="w")
            return
        for op_id in op_ids:
            module = None
            try:
                module = app._module_by_id(op_id)
            except Exception:  # noqa: BLE001
                module = None
            if module is None:
                continue
            app._action_button(
                btn_frame, module.OP.get("name", op_id),
                module).pack(side="left", padx=(0, 4))

    search_entry.bind("<KeyRelease>", lambda _e: _refill())
    # Trace bhi — programmatic set par bhi fehrist chhan jaye (sirf
    # KeyRelease par inhesar nahi; asli typing me focus hota hai,
    # is liye dono raste mehfooz hain).
    search_var.trace_add("write", lambda *_a: _refill())
    model_list.bind("<<ListboxSelect>>", _on_select)
    _refill()


def build_brand_pages(parent, app):
    """Brand tab row + scrollable content frame. IMEI section is
    frame ke neeche alag pack hota hai (har brand page par wahi)."""
    frame = tk.LabelFrame(parent, text=" BRAND PAGES ",
                          bg=PANEL, fg=MUTED, bd=1,
                          font=("Segoe UI", 9, "bold"))
    # Brand tab row — khud horizontal scroll hoti hai, taake chhoti
    # window par bhi 12 tabs me se koi kata hua na rahe.
    tab_container = tk.Frame(frame, bg=PANEL)
    tab_container.pack(fill="x", padx=6, pady=(4, 2))
    tab_canvas = tk.Canvas(tab_container, bg=PANEL,
                           highlightthickness=0, height=32)
    tab_scroll = tk.Scrollbar(tab_container, orient="horizontal",
                              command=tab_canvas.xview)
    tab_canvas.configure(xscrollcommand=tab_scroll.set)
    tab_scroll.pack(side="bottom", fill="x")
    tab_canvas.pack(side="top", fill="x")
    tabrow = tk.Frame(tab_canvas, bg=PANEL)
    tab_canvas.create_window((0, 0), window=tabrow, anchor="nw")

    def _on_tab_inner(_event=None):
        tab_canvas.configure(scrollregion=tab_canvas.bbox("all"))

    tabrow.bind("<Configure>", _on_tab_inner)
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
                          "\"IMEI Patch — Sirf Original\" section se "
                          "hoga (model list ki zaroorat nahi).",
                     bg=PANEL, fg=MUTED, wraplength=680,
                     justify="left",
                     font=("Segoe UI", 8)).pack(anchor="w",
                                                pady=(8, 0))
            # 2026-10-24 (Hamza ka hukm): isi page par us brand ke
            # models — naam dhoondo, model chuno, reset/FRP dabao.
            _render_brand_models(inner, app, key)

    for key, title, _ops, _note, _stubs in BRAND_DEFS:
        btn = tk.Button(tabrow, text=title, bg=PANEL2, fg=FG,
                        relief="flat", font=("Segoe UI", 8, "bold"),
                        padx=8, pady=2,
                        command=lambda k=key: _render(k))
        btn.pack(side="left", padx=(0, 4))
        state["btns"][key] = btn
    _render("infinix")  # Transsion pehle (dukaan ka asal kaam)
    frame.render_brand = _render
    # DB load / reload ke baad maujooda brand page dobara banao
    # (main._load_mdm_models is se fehrist taaza karta hai — pehle
    # render ke baad ki load ka asar page par nahi parta tha).
    frame.refresh_brand = (
        lambda: _render(state["current"]) if state["current"] else None)
    return frame
