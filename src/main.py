#!/usr/bin/env python3
"""
MEER TOOL PRO — main application.

Professional layout (UnlockTool / Fenix style):
  upar     : title bar + DEMO MODE
  phir     : DEVICE PANEL (auto-detect: brand/model/chip/serial/mode)
  darmiyan : bayein OPERATIONS TREE — dayein bara LIVE LOG console
  neeche   : progress bar + START / STOP / Clear

Har operation asal plugin (src/ops/) hai jo core/runner.py ke through
engine chalata hai — output live log me stream hoti hai. Koi launcher
nahi, koi nakli success nahi.
"""

import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo as demo_mod                       # noqa: E402
from core import device_watch                 # noqa: E402
from core import firmware_catalog             # noqa: E402
from core import mdm_list                     # noqa: E402
from core import platforms_mtk                # noqa: E402
from core import repair_intel                 # noqa: E402
from core import shop_db                      # noqa: E402
from core import utility                      # noqa: E402
from core.runner import ENGINES_DIR, Runner, TOOLS_DIR     # noqa: E402
from ops import load_operations               # noqa: E402

# ---------------------------------------------------------------- theme ----
BG = "#14181f"
PANEL = "#1b212b"
PANEL2 = "#202834"
LOG_BG = "#0b0e13"
FG = "#e6e9ee"
MUTED = "#8b95a5"
ACCENT = "#ffa028"
GREEN = "#3fb950"
LEVEL_COLORS = {
    "INFO": "#e6e9ee", "OK": "#4ade80", "WARN": "#facc15",
    "ERROR": "#f87171", "CMD": "#60a5fa", "DATA": "#9aa7b8",
}

CHANGELOG_TEXT = """MEER TOOL PRO — Changelog

v1.0 (2026-10-22) — pehli mukammal release
- Modules: HOME / UNLOCK / PLATFORMS / UTILITY / CHANGELOG
- UNLOCK: 75 operations (ops tree) + Fenix-style MDM List — per-model
  database (tools/mdm-models.json, 58 models), mode tabs tags ke
  hisaab se: MTK par Download / Transsion META, Unisoc par Download /
  DIAG / Network / PATCHER, dono par ADB / FASTBOOT.
- MTK (MTKClient): Read Info/GPT, Latest Bypass (Auto) — payload →
  carbonara → heapbait → stock DA chain, FRP + Factory Reset
  (persist ke saath), Full Backup, Scatter Flash, Bootloader
  Unlock/Relock + vbmeta.
- MDM Pack: Proinfo backup/write (library), META guide, ADB MDM
  check, Security Plugin remove, PayJoy — tamam backup-first aur
  imaandar labels ke saath (PayJoy = BYPASSED, kabhi nakli
  "permanent" nahi).
- PLATFORMS → MediaTek workbench: GPT partition table + Identify /
  Backup / Erase / Flash / Reboot, DA picker, Crash PL To Brom,
  As Scatter.
- UTILITY: ADB tools, Fastboot tools, File Manager (ADB browse /
  pull / push).
- Qualcomm EDL (user loaders ke saath), Samsung FRP method-router,
  SPD official-tools launcher + FRP.pac guide.
- Jo cheez server ke baghair nahi ho sakti, wahan tool imaandari se
  🔒 SERVER REQUIRED kehta hai — nakli success kabhi nahi.

v1.0 — Round 4 izafa (REPAIR-METHODS-RESEARCH ke baad, 52 ops):
- Qualcomm FRP v2 (GPT-driven): pehle GPT parh kar asal naam
  (frp / persistent / config) erase hota hai — Samsung QC ke
  A05s/A23 class par ab asal rasta. 'persist' (calibration)
  kabhi nahi chua jata.
- Unisoc ke standalone ops (spd_dump engine, stock PAC ke FDL
  se): FRP Erase, Factory Reset, Cert (prodnv) Backup.
- MTK NV Backup / NV Restore (nvram+nvdata jora) aur SN Writer /
  Modem META launcher+guide — asal IMEI wapas karne ke raste.
- Qualcomm QCN Backup/Restore (QPST/QFIL guide + diag tayyari)
  aur selective EFS Backup/Restore (modemst1/2, fsg, fsc).
- Fastboot FRP Erase + Factory Reset (sirf unlocked bootloader,
  halat pehle getvar se confirm hoti hai).
- IMEI gate mazboot: har tasdeeq tools/imei-audit.log me
  mehfooz hoti hai; restore wale har op par pre-restore
  snapshot lazmi hai.
- Android 15/16 note (imaandari): Android 15/16 ki nayi FRP
  sakhti setup-wizard wali tricks ko rokti hai — partition
  erase wale asal servicing raste (BROM/EDL/FDL/fastboot) is
  se band NAHI hote. Asal rok chipset ki server-signed auth
  (SLA/DAA) hai, Android version nahi — jahan wo lage, tool
  saaf SERVER REQUIRED kehta hai.

v1.0.1 — Round 5 izafa (Pandora sweep ke baad, 75 ops):
- Bundled Python: ENGINES package ke andar Python 3.12 tayyar
  (dependencies ke saath) — ab MTK/EDL engines ke liye alag
  Python install NAHI karna parta. Double-click par sab chalta
  hai; system Python sirf fallback hai.
- Driver Pack + Install Drivers op (Utility): UsbDk + Samsung
  official USB driver bundle; MTK VCOM / Qualcomm 9008 / SPRD
  ke liye sirf official raste ki guide (README-DRIVERS).
- META basic-tier asal ops: Enter META (port verify ke saath),
  META Read Info, META Factory Reset, META Enable ADB — har
  SUCCESS sirf device ke verify-shuda jawab par. EFT Pro ke
  changelog ne Android 16 META FRP 20 taaza Transsion models
  par verify kiya hai — MDM List me 15 models par '✓A16'
  nishan. New-algorithm/new-Auth wala hissa ab bhi
  SERVER REQUIRED hai.
- Samsung Download-Mode Flash (odin4): CSC (full reset) aur
  HOME_CSC (data mehfooz) do ops. KG ab bhi display-only.
- Xiaomi MiAssistant Sideload: Recovery ROM flash; Mi
  Account/FRP server se bandha hai — us ka daawa nahi.
- Fastboot Flash Pack (folder ke .img), Slot Switch (A/B
  verify ke saath), Reboot-to-EDL (ADB + Fastboot), Samsung
  Download reboot, Motorola FRP Erase (locked BL par bhi).
- Unisoc Full Readback (PAC-ready folder) + MTK Restore
  Backup one-click (IMEI gate ke saath); MTK FRP Only /
  Reset Only alag ops; Format NVRAM+NVDATA op.
- Firmware Front Door: ZIP/TGZ scatter seedha kholo, Oppo/
  Realme OFP extract (bkerler oppo_decrypt), OTA payload.bin
  extract (payload-dumper-go). OZIP ke liye upstream package
  me script maujood nahi — wahan guided FAIL hai.
- Reset-honesty label har reset op par (finance/MDM pehle
  check + 'USERDATA-LEVEL RESET' natija label); naye app
  profiles: Samsung Account/Knox Set, Disable OTA Updates
  Set, Demo/Retail Set; Update Check op (GitHub Releases).
- MDM List: tamam 58 models ke codes ab verify-shuda (0
  unverified baqi).
- Guided reh gaya (imaandari se): Samsung Exynos Odin-patch
  FRP (AMT wala) — public verify-shuda mechanism nahi mila,
  is liye op nahi bana; META Partition Manager aur Unisoc
  ADL-mode (ZTE) bhi bench-verification ke baghair guided
  hain. Jhoota button kabhi nahi.

v1.0.1 — Suite Phase 1 (Server Edition ki pehli seedhi; ops
ab bhi 75 hi — ye modules device-ops nahi, dukaan ke records
hain):
- CUSTOMERS module: dukaan ke customers ka LOCAL record
  (SQLite — tools/shop.db) — naam/phone/address/notes,
  add/edit/search. Koi server nahi, koi network nahi:
  record hamesha is PC par mehfooz rehta hai (survival rule).
- JOBS module: repair tickets — auto ticket number (T-0001),
  customer se link, device (brand/model, IMEI sirf record
  ke liye), masla, status (Received / In Progress / Done /
  Delivered — aik click quick buttons), charges (estimate +
  final), received/delivered dates (Delivered par date
  khud lagti hai). Search + status filter.
- RECEIPT: kisi bhi job ki printable receipt (HTML ya
  text) — dukaan ka naam CUSTOMERS screen se badal sakte
  ho; receipt browser me khul kar print hoti hai.
- HOME dashboard barha: DUKAAN — AAJ KA HISAB (aaj ke
  jobs, pending jobs, kul customers, kul jobs).
- BACKUP / EXPORT (CUSTOMERS screen par): shop.db ki
  one-click backup copy (backups/ folder me) + customers/
  jobs ka CSV export — record kabhi aik jagah band nahi
  rehta.

v1.0.1 — Round 6 izafa (TSM/UAT sweep ke baad, 86 ops):
- MTK RPMB ops (MTKClient ka apna `da rpmb` toolset): RPMB
  Read (saboot DA ke 'Done reading' jawab + file size se —
  exit code yahan saboot nahi hota), RPMB Write aur RPMB
  Erase. Write/Erase DESTRUCTIVE hain: naye DANGER GATE ke
  baghair nahi chalte (neeche PARAMS bar ki tasdeeq checkbox
  + tools/danger-audit.log me audit line), aur dono
  BACKUP-FIRST hain — pehle maujooda data parh kar mehfooz
  hota hai, backup na bane to amal hota hi nahi; aakhir me
  read-back verify (write: byte-match; erase: poori range
  zero) lazmi hai.
- Qualcomm Raw Sector Read/Write (edl rs/ws): LUN + Start
  Sector + Sectors + Sector Size window ke neeche PARAMS
  bar se ate hain. Read size-verify ke saath; Write danger
  gate + backup-first + read-back byte-match ke saath.
  Loader lazmi hai — na ho to saaf guided FAIL.
- ADB Servicing Tasks pack: Remove Ads / Restore Ads
  (Xiaomi ads set + generic set — pm disable-user, device
  list se verify), Servicing Menus (network/APN/wireless
  ke public intents; DIAG ka koi public intent nahi hota —
  wo jhoota daawa nahi), Private DNS Toggle (dns.google,
  readback verify), Fix Install Apps (verifier settings,
  har aik ki readback). Har task par root chahiye ya nahi,
  log me saaf likha ata hai; device-side saboot ke baghair
  koi SUCCESS nahi.
- Enable DIAG Port ab alag op hai (Qualcomm) — QCN helper
  hi asal kaam karta hai, saath Samsung *#0808# aur
  OnePlus/Xiaomi *#*#717717#*#* dialer codes ki guide.
- spd_dump refresh check: upstream ki latest official
  release 1.20260403 hi hai — hamari vendored copy wahi
  hai, is liye koi tabdeeli nahi ki gayi (provenance
  engines/spd_dump/README-MEER.md me darj hai).

v1.0.1 — Round 7 izafa (September-security research ke
baad, 96 ops): Fenix ke 'September security' daway ka
asal medan META mode hai — ye izafa wahi META tier wasee
karta hai (sab public FT protocol par; SUCCESS hamesha
sirf verified FT jawab — status 0x00 — par):
- META FRP Erase: FT se sirf 'frp' partition erase —
  userdata nahi mit-ta. Pandora/Octoplus/EFT ka META-FRP
  wala hi rasta, jahan META entry khuli ho.
- META UBL (LK Patch) + Restore LK: GPT check → poora
  LK backup → per-model patch-data se patch → read-back
  verify. Restore poora stock LK wapas karta hai.
  DESTRUCTIVE — danger gate + backup-first lazmi.
- META Security Plugin Patch + Restore MDM (META):
  proinfo/state ka per-model patch, backup record se
  asal halat wapas. Dono danger gate ke saath.
- Patch-data imaandari: byte-pattern sirf
  tools/meta-patch-data.json library se ate hain — jis
  model ka VERIFIED data library me nahi, wahan tool
  guided STOP deta hai. Guessed offset par kabhi NAHI
  likha jata (galat offset = brick).
- META GPT / Partition Table Read: patch ops se pehle
  compatibility check ki deewar — partition maujood na
  ho to patch op aage hi nahi barhta.
- Session completion set: Disable ADB (META), Reboot
  to Normal, Power Off, Reboot to Fastboot — Fenix ke
  TMETA tab se mukammal parity.
- New-Auth guard ab LADDER hai: Dimensity 6300/6400/
  7300/9000 class par META rukne ke saath wajah + doosra
  zinda darwaza khud samne ata hai — DA/Heapbait chain
  (vendored MTKClient me heapbait + carbonara pehle se
  shamil, bypass chain me wired), test-point guidance,
  ADB rasta. META entry ki signed 'new Auth' ab bhi
  server-wali hai — wahan imaandar 🔒 hi rahega.
- MDM List: har model ke label me us ka ROUTE nazar ata
  hai — META (33) / META+DA (7) / new-Auth (8) /
  Kamakiri (1) / DIAG/FDL (9) — aur META tab par 6 naye
  Round-7 buttons (FRP Erase, UBL LK Patch, Restore LK,
  Plugin Patch, Restore MDM (META), GPT).
- Test-point library: tools/testpoints.json — per-model
  TP note ka saaf structure; location sirf verified
  source se bharegi (andaze wali location board kharab
  kar sakti hai).
- Bench note (imaandari): Round-7 ke naye FT message ids
  public FT table se hain, codec software-tested hai —
  asal phone par in ki verification pehle asal test ke
  saath hogi. Galat jawab par ops nakli success ki
  bajaye saaf FAIL dete hain — yahi design hai.

v1.0.1 — Suite Phase 2 izafa (Firmware Center + Repair
Intelligence; 99 ops):
- FIRMWARE module: firmware RECORDS ka catalogue
  (tools/firmware-catalog.json) — brand/model/code/
  version/Android/size/official link/SHA-256 checksum.
  Firmware yahan HOST nahi hoti; sirf official sources
  ke records hain (catalogue source: Hovatek Stock ROM
  Forum). Downloaded file ka checksum record se verify
  karne ka button — match/mismatch log me saaf.
- Firmware → Loader Harvest (naya op): factory firmware
  (.zip/.tgz/.ofp/.ozip/.pac) ke andar se preloader /
  lk / MTK DA / firehose / PAC ke FDL1/FDL2 nikaal kar
  Loaders Library me darj — firehose/DA ki tasdeeq
  magic bytes se, FDL ki PAC table se (Unisoc ke FDL
  khane loaders/unisoc/ me), preloader/lk naam se
  (alag record-khane; auto-select inhe kabhi DA nahi
  samajhta). Har darj par provenance: 'harvested from
  <firmware file>'.
- REPAIR INTELLIGENCE: error-code library
  (tools/repair-intel.json, 18 entries — har aik
  vendored engines ke asal error strings/codes se
  grounded, source darj) + FIRMWARE module me search.
  Runner ab har FAIL hue op ke aakhir me log ko in
  patterns se scan karke '💡 Repair Intelligence' hint
  khud jor deta hai (match ho tab hi).
- Driver rehnumai: koi op device/port na milne par
  fail ho to aakhir me saaf 🔌 wali line — sahi mode
  ki hidayat + UTILITY ke Install Drivers op ki taraf
  ishara.
- Backup-first audit: tamam destructive ops registry
  se gin kar check hue. Do asal gaps band hue — Format
  NVRAM+NVDATA aur Proinfo Write pehle warning-only
  thay, ab dono par DANGER GATE (tasdeeq ke baghair
  zero koshish) lag gaya hai.
"""


def tool_path(name):
    """engines/ ya tools/ ke platform-tools me ho to wahan se, warna PATH."""
    for cand in (ENGINES_DIR / "platform-tools" / f"{name}.exe",
                 ENGINES_DIR / "platform-tools" / name,
                 TOOLS_DIR / "platform-tools" / f"{name}.exe",
                 TOOLS_DIR / "platform-tools" / name):
        if cand.is_file():
            return str(cand)
    return name


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MEER TOOL PRO v1.0")
        self.geometry("1220x800")
        self.minsize(980, 620)
        self.configure(bg=BG)

        self.ui_q = queue.Queue()
        self.device = device_watch.DeviceInfo()
        self.demo_active = False
        self.op_modules = {}            # tree item id -> plugin module
        self.selected_op = None
        self.view_mode = "ops"          # "ops" | "mdm"
        self.mdm_models = []            # mdm-models.json wale models
        self.mdm_items = {}             # model tree item id -> model dict
        self.selected_model = None
        self.mdm_tab = None
        self.fdl_exploit_var = tk.BooleanVar(value=False)
        # Module switcher (Fenix-style): home/unlock/platforms/utility/changelog
        self.current_module = "unlock"
        self.module_frames = {}
        self.module_btns = {}
        # Platforms (MTK workbench) ki halat
        self.plat_parts = []            # GPT se aye partitions (+ "file")
        self.plat_selected = set()      # tick kiye hue partition names
        self.plat_sub = "flash"
        # Utility File Manager ki halat
        self.fm_path = "/sdcard/"
        self.fm_items = {}              # fm tree item id -> entry dict
        # Suite Phase 1 (CUSTOMERS / JOBS) ki halat
        self.cust_selected_id = None
        self.cust_items = {}            # cust tree item id -> customer id
        self.job_selected_id = None
        self.job_items = {}             # job tree item id -> job id
        self.job_cust_ids = []          # job form combo ki tartib se ids
        self.job_cust_labels = []       # combo labels (ids ke parallel)
        # Suite Phase 2 (FIRMWARE CENTER) ki halat
        self.fw_selected = None         # catalog entries ka index
        self.fw_items = {}              # fw tree item id -> catalog index
        self.fw_catalog = None          # load shuda catalogue dict

        self.runner = Runner(
            log_fn=lambda m, lvl: self.ui_q.put(("log", m, lvl)),
            progress_fn=lambda p, lab: self.ui_q.put(("progress", p, lab)),
            done_fn=lambda res: self.ui_q.put(("done", res)),
            update_device_fn=lambda d: self.ui_q.put(("device", d)),
        )

        self._build_ui()
        self._load_ops_tree()
        self._load_mdm_models()
        self._init_shop()
        self.after(60, self._drain_queue)
        threading.Thread(target=self._watch_loop, daemon=True).start()
        self.log_line("MEER TOOL PRO tayyar hai. Phone lagao — device "
                      "khud detect hoga. Ya pehle DEMO MODE se flow dekho.",
                      "INFO")

    # ------------------------------------------------------------ UI build -
    def _build_ui(self):
        # Title bar
        head = tk.Frame(self, bg=PANEL, height=52)
        head.pack(fill="x")
        tk.Label(head, text="MEER TOOL PRO", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=14, pady=8)
        tk.Label(head, text="Professional Mobile Servicing", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 10)).pack(side="left", pady=10)
        tk.Button(head, text="▶  DEMO MODE", command=self.start_demo,
                  bg=ACCENT, fg="#111", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=12, pady=4).pack(side="right", padx=12, pady=8)

        # Module switcher (Fenix-style): HOME / UNLOCK / PLATFORMS /
        # UTILITY / CHANGELOG
        mbar = tk.Frame(self, bg=PANEL2)
        mbar.pack(fill="x", padx=10, pady=(8, 0))
        for key, title in (("home", "HOME"), ("unlock", "UNLOCK"),
                           ("platforms", "PLATFORMS"),
                           ("utility", "UTILITY"),
                           ("customers", "CUSTOMERS"),
                           ("jobs", "JOBS"),
                           ("firmware", "FIRMWARE"),
                           ("changelog", "CHANGELOG")):
            btn = tk.Button(mbar, text=title, relief="flat",
                            font=("Segoe UI", 9, "bold"), padx=12, pady=3,
                            bg=ACCENT if key == "unlock" else PANEL,
                            fg="#111" if key == "unlock" else FG,
                            command=lambda k=key: self.show_module(k))
            btn.pack(side="left", padx=(0, 4), pady=3)
            self.module_btns[key] = btn

        # Device panel
        dev = tk.LabelFrame(self, text=" DEVICE ", bg=PANEL, fg=MUTED,
                            font=("Segoe UI", 9, "bold"), bd=1)
        dev.pack(fill="x", padx=10, pady=(8, 4))
        self.dev_status = tk.Label(dev, text="● NO DEVICE", bg=PANEL,
                                   fg="#f87171", font=("Segoe UI", 11, "bold"))
        self.dev_status.grid(row=0, column=0, sticky="w", padx=10, pady=4)
        self.dev_fields = {}
        labels = [("Brand", "brand"), ("Model", "model"), ("Chip", "chip"),
                  ("Serial", "serial"), ("Mode", "mode"), ("Port", "port"),
                  ("Android", "android"), ("Detail", "detail")]
        for i, (title, key) in enumerate(labels):
            col = 1 + (i % 4) * 2
            row = 1 + i // 4
            tk.Label(dev, text=f"{title}:", bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9)).grid(row=row, column=col,
                                                 sticky="e", padx=(10, 2), pady=2)
            val = tk.Label(dev, text="—", bg=PANEL, fg=FG,
                           font=("Segoe UI", 9, "bold"))
            val.grid(row=row, column=col + 1, sticky="w", pady=2)
            self.dev_fields[key] = val

        # Module area — switcher se badalta hai. UNLOCK frame = purana
        # ops tree + MDM List wala layout.
        modarea = tk.Frame(self, bg=BG)
        modarea.pack(fill="both", expand=True, padx=10, pady=4)
        # Window ko content ki requested height par barhne se roko —
        # module area hamesha mili hui jagah me hi rahega (warna
        # Platforms jaisay baray modules window ko screen se bahir
        # dhakel dete hain).
        modarea.pack_propagate(False)
        self._modarea = modarea
        mid = tk.Frame(modarea, bg=BG)
        self.module_frames["unlock"] = mid
        left = tk.Frame(mid, bg=PANEL, width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        # View toggle: OPERATIONS (purana tree) | MDM LIST (Fenix-style)
        toggle = tk.Frame(left, bg=PANEL)
        toggle.pack(fill="x", padx=6, pady=(6, 2))
        self.ops_btn = tk.Button(toggle, text="OPERATIONS", bg=ACCENT,
                                 fg="#111", relief="flat",
                                 font=("Segoe UI", 9, "bold"),
                                 command=self.show_ops_view)
        self.ops_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.mdm_btn = tk.Button(toggle, text="MDM LIST", bg=PANEL2,
                                 fg=FG, relief="flat",
                                 font=("Segoe UI", 9, "bold"),
                                 command=self.show_mdm_view)
        self.mdm_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))
        # --- Operations view (pehle wala tree, bilkul waisa hi) ---
        self.ops_box = tk.Frame(left, bg=PANEL)
        self.ops_box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(self.ops_box, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=4, pady=2)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.op_hint = tk.Label(self.ops_box, text="Operation select karo.",
                                bg=PANEL, fg=MUTED, wraplength=280,
                                justify="left", font=("Segoe UI", 8))
        self.op_hint.pack(anchor="w", padx=8, pady=6)
        # --- MDM List view (search + per-model fehrist) ---
        self.mdm_box = tk.Frame(left, bg=PANEL)
        self.mdm_search_var = tk.StringVar()
        self.mdm_search_var.trace_add(
            "write", lambda *_a: self._fill_model_tree())
        tk.Entry(self.mdm_box, textvariable=self.mdm_search_var,
                 bg=PANEL2, fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9)).pack(fill="x", padx=6, pady=(4, 2))
        self.model_tree = ttk.Treeview(self.mdm_box, show="tree",
                                       selectmode="browse")
        self.model_tree.pack(fill="both", expand=True, padx=4, pady=2)
        self.model_tree.bind("<<TreeviewSelect>>", self._on_model_select)
        tk.Label(self.mdm_box,
                 text="Model select karo — us ke operations dayein "
                      "panel me khulenge. Fehrist tools/mdm-models.json "
                      "me hai (khud barha sakte ho).",
                 bg=PANEL, fg=MUTED, wraplength=280, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=6)

        right = tk.Frame(mid, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        # Model operation panel (MDM List se model select hone par)
        self.model_panel = tk.LabelFrame(right, text=" MODEL ", bg=PANEL,
                                         fg=MUTED, bd=1,
                                         font=("Segoe UI", 9, "bold"))
        self.unlock_right = right

        # Baqi modules ke frames (builder methods) — sirf UNLOCK packed
        self.module_frames["home"] = self._build_home(modarea)
        self.module_frames["platforms"] = self._build_platforms(modarea)
        self.module_frames["utility"] = self._build_utility(modarea)
        self.module_frames["customers"] = self._build_customers(modarea)
        self.module_frames["jobs"] = self._build_jobs(modarea)
        self.module_frames["firmware"] = self._build_firmware(modarea)
        self.module_frames["changelog"] = self._build_changelog(modarea)
        mid.pack(fill="both", expand=True)

        # LIVE LOG — tamam modules ke liye mushtaraka, hamesha nazar
        # ata hai (runner ki output har module se yahin ati hai)
        logf = tk.Frame(self, bg=BG)
        logf.pack(fill="x", padx=10, pady=(0, 2))
        self.log_label = tk.Label(logf, text="LIVE LOG", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 9, "bold"))
        self.log_label.pack(anchor="w", pady=(2, 4))
        self.log = tk.Text(logf, bg=LOG_BG, fg=FG, font=("Consolas", 10),
                           relief="flat", wrap="word", state="disabled",
                           height=7)
        scroll = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        for lvl, color in LEVEL_COLORS.items():
            self.log.tag_configure(lvl, foreground=color)

        # Bottom: progress + buttons
        bot = tk.Frame(self, bg=PANEL)
        bot.pack(fill="x", padx=10, pady=(4, 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Pro.Horizontal.TProgressbar", troughcolor=PANEL2,
                        background=ACCENT, bordercolor=PANEL2)
        self.progress = ttk.Progressbar(bot, style="Pro.Horizontal.TProgressbar",
                                        maximum=100, value=0, length=420)
        self.progress.pack(side="left", padx=10, pady=10)
        self.prog_label = tk.Label(bot, text="0%", bg=PANEL, fg=FG,
                                   font=("Segoe UI", 10, "bold"), width=16,
                                   anchor="w")
        self.prog_label.pack(side="left")
        tk.Button(bot, text="CLEAR LOG", command=self.clear_log, bg=PANEL2,
                  fg=FG, relief="flat", padx=10, pady=5).pack(side="right", padx=4)
        self.stop_btn = tk.Button(bot, text="■ STOP", command=self.runner.stop,
                                  bg="#7f1d1d", fg="#fff", relief="flat",
                                  padx=16, pady=5, state="disabled",
                                  font=("Segoe UI", 10, "bold"))
        self.stop_btn.pack(side="right", padx=4)
        self.start_btn = tk.Button(bot, text="▶ START", command=self.start_op,
                                   bg=GREEN, fg="#0b0e13", relief="flat",
                                   padx=18, pady=5, state="disabled",
                                   font=("Segoe UI", 11, "bold"))
        self.start_btn.pack(side="right", padx=4)

        # PARAMS bar — raw sector / RPMB ops ke numeric inputs
        # (LUN / Start Sector / Sectors / Sector Size) aur
        # khatarnaak (destructive) write ops ki tasdeeq checkbox
        # (danger gate — core/danger_gate.py). Har waqt nazar
        # ati hai taake gated op chalane se pehle user ko pata
        # ho ke tasdeeq kahan deni hai.
        parambar = tk.Frame(self, bg=PANEL)
        self.parambar = parambar
        tk.Label(parambar, text="PARAMS (Sector / RPMB ops):",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side="left",
                                                    padx=(10, 4),
                                                    pady=5)

        def _param_entry(var_name, label, default, width=7):
            tk.Label(parambar, text=label, bg=PANEL, fg=FG,
                     font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            tk.Entry(parambar, textvariable=var, width=width,
                     bg=PANEL2, fg=FG, insertbackground=FG,
                     relief="flat",
                     font=("Consolas", 10)).pack(side="left",
                                                 padx=(2, 10), pady=4)

        _param_entry("param_lun_var", "LUN", "0")
        _param_entry("param_start_sector_var", "Start Sector", "0")
        _param_entry("param_sectors_var", "Sectors", "")
        _param_entry("param_sector_size_var", "Sector Size", "")
        self.danger_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parambar,
            text="⚠ Tasdeeq: KHATARNAAK write — zimmedari meri hai",
            variable=self.danger_confirm_var, bg=PANEL,
            fg="#fbbf24", selectcolor=PANEL2,
            activebackground=PANEL, activeforeground="#fbbf24",
            font=("Segoe UI", 9, "bold")).pack(side="right",
                                               padx=10, pady=4)

        # Pack tartib ki islah: LIVE LOG aur bottom bar ko bottom se
        # anchor karo, module area darmiyan ki baqi jagah lega — warna
        # baray module (Platforms) par log/buttons window se bahir
        # dhakel jate hain.
        bot.pack_forget()
        logf.pack_forget()
        bot.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        logf.pack(side="bottom", fill="x", padx=10, pady=(0, 2))
        parambar.pack(side="bottom", fill="x", padx=10, pady=(2, 0))

    # ------------------------------------------------------------ ops tree -
    def _load_ops_tree(self):
        cats = {}
        try:
            modules = load_operations()
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Operations load nahi ho sakin: {e}", "ERROR")
            return
        for module in modules:
            op = module.OP
            cat = op.get("category", "Other")
            if cat not in cats:
                cats[cat] = self.tree.insert("", "end", text=f"  {cat}", open=True)
            label = f"  {op.get('name', op.get('id'))}"
            if op.get("server_required"):
                label += "   🔒 SERVER REQUIRED"
            item = self.tree.insert(cats[cat], "end", text=label)
            self.op_modules[item] = module
        self.log_line(f"{len(modules)} operations load ho gayeen.", "INFO")

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        module = self.op_modules.get(sel[0]) if sel else None
        self.selected_op = module
        if module is None:
            self.start_btn.configure(state="disabled")
            return
        op = module.OP
        hint = f"Engine: {op.get('engine', '-')}"
        modes = op.get("modes") or ()
        if modes:
            hint += f" · Zaroori mode: {', '.join(modes)}"
        if op.get("server_required"):
            hint += " · Ye operation paid server ke baghair nahi chal sakta."
        if op.get("danger_write"):
            hint += (" · ⚠ KHATARNAAK write: neeche PARAMS bar ki "
                     "tasdeeq checkbox lazmi hai, warna gate rok "
                     "dega.")
        if op.get("params"):
            hint += (" · Inputs neeche PARAMS bar se ate hain "
                     "(LUN / Start Sector / Sectors / Sector Size).")
        self.op_hint.configure(text=hint)
        self.start_btn.configure(state="normal")

    # ------------------------------------------------------- view switch -
    def show_ops_view(self):
        self.view_mode = "ops"
        self.mdm_box.pack_forget()
        self.model_panel.pack_forget()
        self.ops_box.pack(fill="both", expand=True)
        self.ops_btn.configure(bg=ACCENT, fg="#111")
        self.mdm_btn.configure(bg=PANEL2, fg=FG)

    def show_mdm_view(self):
        self.view_mode = "mdm"
        self.ops_box.pack_forget()
        self.mdm_box.pack(fill="both", expand=True)
        self.mdm_btn.configure(bg=ACCENT, fg="#111")
        self.ops_btn.configure(bg=PANEL2, fg=FG)
        if self.selected_model is not None:
            self.model_panel.pack(fill="x", pady=(0, 6))

    # ------------------------------------------------------------ MDM list -
    def _load_mdm_models(self):
        try:
            models, _note = mdm_list.load_models()
        except Exception as e:  # noqa: BLE001
            self.log_line(f"MDM List load nahi ho saki: {e}", "ERROR")
            return
        self.mdm_models = models
        self._fill_model_tree()
        self.log_line(f"MDM List tayyar: {len(models)} models "
                      "(tools/mdm-models.json).", "INFO")

    def _fill_model_tree(self):
        if not hasattr(self, "model_tree"):
            return
        q = ""
        if hasattr(self, "mdm_search_var"):
            q = self.mdm_search_var.get().strip().lower()
        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        self.mdm_items = {}
        for m in self.mdm_models:
            label = mdm_list.model_label(m)
            if q and q not in label.lower():
                continue
            item = self.model_tree.insert("", "end", text=f"  {label}")
            self.mdm_items[item] = m

    def _on_model_select(self, _event=None):
        sel = self.model_tree.selection()
        model = self.mdm_items.get(sel[0]) if sel else None
        if model is None:
            return
        self.selected_model = model
        self._render_model_panel(model)
        if self.view_mode == "mdm":
            self.model_panel.pack(fill="x", pady=(0, 6))

    def _module_by_id(self, op_id):
        for module in self.op_modules.values():
            if module.OP.get("id") == op_id:
                return module
        return None

    def _collect_op_args(self, op_obj):
        """GUI ki gates/params halat ikatthi karo — (imei_confirmed,
        danger_confirmed, params dict). Dono start rastay (ops tree
        aur model panel) yahi istemal karte hain:
          - IMEI gate: op par imei_write ho to Network tab ki
            tasdeeq checkbox ki halat.
          - Danger gate: op par danger_write ho to PARAMS bar ki
            tasdeeq checkbox ki halat.
          - Params: PARAMS bar ke chaaron entries (raw strings —
            parsing/validation op khud karta hai)."""
        op = getattr(op_obj, "OP", {}) or {}
        imei = False
        if op.get("imei_write"):
            var = getattr(self, "net_imei_confirm_var", None)
            imei = bool(var.get()) if var is not None else False
        danger = False
        if op.get("danger_write"):
            var = getattr(self, "danger_confirm_var", None)
            danger = bool(var.get()) if var is not None else False

        def _entry(name):
            var = getattr(self, name, None)
            return var.get() if var is not None else ""

        params = {
            "lun": _entry("param_lun_var"),
            "start_sector": _entry("param_start_sector_var"),
            "sectors": _entry("param_sectors_var"),
            "sector_size": _entry("param_sector_size_var"),
        }
        return imei, danger, params

    def _run_action(self, op_obj):
        """Model panel ke buttons — bilkul START wala rasta (runner)."""
        if op_obj is None:
            return
        imei, danger, params = self._collect_op_args(op_obj)
        if self.runner.start(op_obj, self.device,
                             imei_write_confirmed=imei,
                             danger_confirmed=danger, params=params):
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")

    def _render_model_panel(self, model):
        panel = self.model_panel
        for child in panel.winfo_children():
            child.destroy()
        tk.Label(panel, text=mdm_list.model_label(model), bg=PANEL, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8,
                                                      pady=(6, 0))
        tags = "  ".join(f"[{t}]" for t in model.get("tags", []))
        tk.Label(panel, text=tags, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8,
                                                    pady=(0, 4))
        tabs = mdm_list.model_tabs(model)
        if tabs.get("fdl_exploit"):
            tk.Checkbutton(panel, text="FDL Exploit",
                           variable=self.fdl_exploit_var, bg=PANEL, fg=FG,
                           selectcolor=PANEL2, activebackground=PANEL,
                           activeforeground=FG,
                           font=("Segoe UI", 8, "bold")).pack(
                               anchor="w", padx=8, pady=(0, 2))
        tabrow = tk.Frame(panel, bg=PANEL)
        tabrow.pack(fill="x", padx=8, pady=(0, 4))
        self._model_tab_btns = {}
        for key, title in (("download", "Download"),
                           ("meta", "Transsion META"),
                           ("diag", "DIAG"), ("network", "Network"),
                           ("patcher", "PATCHER"),
                           ("adb", "ADB"), ("fastboot", "FASTBOOT")):
            if not tabs.get(key):
                continue
            btn = tk.Button(tabrow, text=title, bg=PANEL2, fg=FG,
                            relief="flat", font=("Segoe UI", 8, "bold"),
                            padx=8, pady=2,
                            command=lambda k=key: self._render_model_tab(k))
            btn.pack(side="left", padx=(0, 4))
            self._model_tab_btns[key] = btn
        self.model_tab_frame = tk.Frame(panel, bg=PANEL)
        self.model_tab_frame.pack(fill="x", padx=8, pady=(0, 8))
        default = ("download" if tabs.get("download")
                   else "meta" if tabs.get("meta")
                   else "diag" if tabs.get("diag") else "adb")
        self._render_model_tab(default)

    def _render_model_tab(self, key):
        self.mdm_tab = key
        for k, btn in getattr(self, "_model_tab_btns", {}).items():
            btn.configure(bg=ACCENT if k == key else PANEL2,
                          fg="#111" if k == key else FG)
        frame = self.model_tab_frame
        for child in frame.winfo_children():
            child.destroy()
        model = self.selected_model
        if model is None:
            return
        if key == "download":
            if mdm_list.model_tabs(model).get("diag"):
                self._tab_download_spd(frame, model)
            else:
                self._tab_download(frame, model)
        elif key == "meta":
            self._tab_meta(frame, model)
        elif key == "diag":
            self._tab_diag(frame, model)
        elif key == "network":
            self._tab_network(frame, model)
        elif key == "patcher":
            self._tab_patcher(frame, model)
        elif key == "adb":
            self._tab_ops(frame, [
                ("mdm_adb_check", "MDM CHECK - [ADB]"),
                ("mdm_security_plugin", "SECURITY PLUGIN REMOVE - [ADB]"),
                ("mdm_payjoy", "PAYJOY REMOVE - [ADB]")])
        elif key == "fastboot":
            self._tab_ops(frame, [
                ("fastboot_info", "READ INFO - [FASTBOOT]"),
                ("fastboot_reboot", "REBOOT - [FASTBOOT]")])

    def _action_button(self, parent, text, op_obj):
        return tk.Button(parent, text=text, bg=PANEL2, fg=FG,
                         relief="flat", font=("Segoe UI", 8, "bold"),
                         padx=8, pady=4,
                         command=lambda o=op_obj: self._run_action(o))

    def _tab_download(self, frame, model):
        self._da_model = model
        row = tk.Frame(frame, bg=PANEL)
        row.pack(fill="x", pady=(0, 4))
        tk.Label(row, text="DA File:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.da_var = tk.StringVar()
        self.da_combo = ttk.Combobox(row, textvariable=self.da_var,
                                     state="readonly", width=44)
        self.da_combo.pack(side="left", padx=6)
        tk.Button(row, text="↻ Refresh", bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8),
                  command=self._refresh_da_list).pack(side="left")
        self._refresh_da_list()
        tk.Button(frame, text="FACTORY RESET + FRP - [GPT]", bg=PANEL2,
                  fg=FG, relief="flat", font=("Segoe UI", 8, "bold"),
                  padx=8, pady=4,
                  command=lambda: self._run_action(
                      mdm_list.download_frp_op(model,
                                               self._selected_da()))
                  ).pack(anchor="w")

    def _refresh_da_list(self):
        # Model ke liye library-ranked fehrist: best match sab se
        # upar (auto-select); user ka pehle se chuna hua DA agar
        # ab bhi fehrist me ho to wahi barqarar (manual hamesha jeet-ti).
        prev = self._selected_da()
        files = mdm_list.da_files(model=getattr(self, "_da_model", None))
        self._da_paths = files
        labels = []
        for p in files:
            try:
                labels.append(str(p.relative_to(TOOLS_DIR / "loaders")))
            except Exception:
                labels.append(p.name)
        if not labels:
            labels = ["(koi DA nahi — Loaders pack tools/loaders me lagao)"]
        self.da_combo.configure(values=labels)
        if prev is not None and prev in files:
            self.da_combo.current(files.index(prev))
        else:
            self.da_combo.current(0)

    def _selected_da(self):
        idx = self.da_combo.current() if hasattr(self, "da_combo") else -1
        paths = getattr(self, "_da_paths", [])
        if 0 <= idx < len(paths):
            return paths[idx]
        return None

    def _tab_meta(self, frame, model):
        grid = tk.Frame(frame, bg=PANEL)
        grid.pack(fill="x")
        for i, (_label, factory) in enumerate(mdm_list.META_ACTIONS):
            btn = self._action_button(grid, _label, factory(model))
            btn.grid(row=i // 2, column=i % 2, sticky="ew",
                     padx=2, pady=2)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    def _tab_download_spd(self, frame, model):
        tk.Label(frame, text="Unisoc Download route stock PAC + official "
                             "tools se hota hai (PAC/tools tools/spd/ me "
                             "rakho).",
                 bg=PANEL, fg=MUTED, wraplength=520, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
        self._tab_ops(frame, [
            ("spd_launcher", "SPD OFFICIAL TOOLS - [Download]"),
            ("spd_frp_pac_guide", "FRP.PAC GUIDE - [Download]")])

    def _tab_diag(self, frame, model):
        grid = tk.Frame(frame, bg=PANEL)
        grid.pack(fill="x")
        provider = lambda: bool(self.fdl_exploit_var.get())
        for i, (_label, factory) in enumerate(mdm_list.DIAG_ACTIONS):
            btn = self._action_button(grid, _label,
                                      factory(model, provider))
            btn.grid(row=i // 2, column=i % 2, sticky="ew",
                     padx=2, pady=2)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    def _tab_network(self, frame, model):
        self.net_vars = {}
        for key, title in (("imei1", "Original IMEI 1 (dabbe/sticker wala)"),
                           ("imei2", "Original IMEI 2 (dabbe/sticker wala)"),
                           ("bt_mac", "BT MAC"), ("wifi_mac", "WiFi MAC")):
            row = tk.Frame(frame, bg=PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{title}:", bg=PANEL, fg=MUTED, width=32,
                     anchor="e", font=("Segoe UI", 8)).pack(side="left")
            var = tk.StringVar()
            self.net_vars[key] = var
            tk.Entry(row, textvariable=var, bg=PANEL2, fg=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=26).pack(side="left",
                                                          padx=4)
        tk.Label(frame, text="IMEI yahan sirf ORIGINAL (dabbe/sticker "
                             "wala) restore hota hai — pehle Backup "
                             "Cert lazmi hai.",
                 bg=PANEL, fg=MUTED, wraplength=520, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 2))
        # IMEI GATE ki tasdeeq: ye checkbox ON kiye baghair RESTORE
        # CERT / RESTORE ORIGINAL IMEI live log me warning dikha kar
        # wahi ruk jayenge — koi write shuru nahi hogi.
        self.net_imei_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame,
            text="Tasdeeq: ye IMEI is phone ke DABBE / STICKER wala "
                 "ASAL IMEI hai — doosra IMEI likhna JURM hai",
            variable=self.net_imei_confirm_var, bg=PANEL, fg=FG,
            selectcolor=PANEL2, activebackground=PANEL,
            activeforeground=FG, font=("Segoe UI", 8),
            anchor="w").pack(anchor="w", pady=(2, 2))
        provider = lambda: (self.net_vars["imei1"].get(),
                            self.net_vars["imei2"].get())
        btnrow = tk.Frame(frame, bg=PANEL)
        btnrow.pack(fill="x")
        for text, op_obj in (
                ("READ IMEI", mdm_list.network_read_op(model)),
                ("BACKUP CERT", mdm_list.network_backup_cert_op(model)),
                ("RESTORE CERT", mdm_list.network_restore_cert_op(model)),
                ("RESTORE ORIGINAL IMEI",
                 mdm_list.network_restore_imei_op(model, provider))):
            self._action_button(btnrow, text, op_obj).pack(side="left",
                                                           padx=2, pady=2)

    def _tab_patcher(self, frame, model):
        tk.Label(frame, text="Stock .pac select karo — tool working "
                             "copy + patch report banayega. Anticrack "
                             "ka asal byte-patch abhi research-pending "
                             "hai (log me imaandar wazahat ayegi).",
                 bg=PANEL, fg=MUTED, wraplength=520, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _pick_and_run():
            path = filedialog.askopenfilename(
                title="Stock .pac firmware select karo",
                filetypes=[("PAC firmware", "*.pac"),
                           ("Tamam files", "*.*")])
            if path:
                self._run_action(mdm_list.pac_patch_op(model, path))

        tk.Button(frame, text="PATCH ANTICRACK DISABLE - [PAC FIRMWARE]",
                  bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                  command=_pick_and_run).pack(anchor="w")

    def _tab_ops(self, frame, pairs):
        for op_id, label in pairs:
            module = self._module_by_id(op_id)
            btn = self._action_button(frame, label, module)
            if module is None:
                btn.configure(state="disabled")
            btn.pack(anchor="w", pady=2)

    # ---------------------------------------------------- module switch --
    def show_module(self, name):
        """Fenix-style module switcher — sirf muntakhib module ka frame
        nazar ata hai; device panel, LIVE LOG aur progress hamesha rehte
        hain."""
        if name not in self.module_frames:
            return
        self.current_module = name
        for key, frame in self.module_frames.items():
            if key == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for key, btn in self.module_btns.items():
            active = key == name
            btn.configure(bg=ACCENT if active else PANEL,
                          fg="#111" if active else FG)
        # Suite screens har dafa taza data ke saath khulen
        if name == "home":
            self._refresh_home_shop()
        elif name == "customers":
            self._refresh_customers()
        elif name == "jobs":
            self._refresh_job_customers()
            self._refresh_jobs()
        elif name == "firmware":
            self._refresh_firmware()

    def _run_lazy(self, op_id):
        """Click ke waqt registry se module dhoondo (builders GUI banne
        ke waqt chalte hain, ops us ke baad load hote hain)."""
        module = self._module_by_id(op_id)
        if module is not None:
            self._run_action(module)

    def _tab_ops_lazy(self, parent, pairs):
        for op_id, label in pairs:
            tk.Button(parent, text=label, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                      command=lambda oid=op_id: self._run_lazy(oid)
                      ).pack(anchor="w", pady=2, fill="x")

    # ------------------------------------------------------------ HOME ---
    def _build_home(self, parent):
        f = tk.Frame(parent, bg=BG)
        card = tk.Frame(f, bg=PANEL)
        card.pack(fill="both", expand=True)
        tk.Label(card, text="MEER TOOL PRO", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 20, "bold")).pack(pady=(16, 0))
        tk.Label(card, text="Professional Mobile Servicing — MTK · MDM "
                            "(Transsion) · Qualcomm · Samsung · SPD",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(pady=(0, 10))
        devf = tk.LabelFrame(card, text=" DEVICE ", bg=PANEL, fg=MUTED,
                             font=("Segoe UI", 9, "bold"), bd=1)
        devf.pack(fill="x", padx=14, pady=4)
        self.home_dev_label = tk.Label(
            devf, text="Koi device nahi laga — phone lagao, khud "
                       "detect hoga.",
            bg=PANEL, fg=FG, font=("Segoe UI", 10, "bold"))
        self.home_dev_label.pack(anchor="w", padx=10, pady=8)
        nav = tk.LabelFrame(card, text=" MODULES ", bg=PANEL, fg=MUTED,
                            font=("Segoe UI", 9, "bold"), bd=1)
        nav.pack(fill="x", padx=14, pady=6)
        row = tk.Frame(nav, bg=PANEL)
        row.pack(fill="x", padx=8, pady=8)

        def _go_unlock_mdm():
            self.show_module("unlock")
            self.show_mdm_view()

        def _go_unlock_ops():
            self.show_module("unlock")
            self.show_ops_view()

        for text, cmd in (
                ("🔓 UNLOCK — Operations", _go_unlock_ops),
                ("📋 MDM LIST", _go_unlock_mdm),
                ("🧰 PLATFORMS — MediaTek",
                 lambda: self.show_module("platforms")),
                ("🛠 UTILITY",
                 lambda: self.show_module("utility")),
                ("👥 CUSTOMERS",
                 lambda: self.show_module("customers")),
                ("🎫 REPAIR JOBS",
                 lambda: self.show_module("jobs")),
                ("📀 FIRMWARE CENTER",
                 lambda: self.show_module("firmware"))):
            tk.Button(row, text=text, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=10, pady=6,
                      command=cmd).pack(side="left", padx=3)
        shopf = tk.LabelFrame(card, text=" DUKAAN — AAJ KA HISAB ",
                              bg=PANEL, fg=MUTED,
                              font=("Segoe UI", 9, "bold"), bd=1)
        shopf.pack(fill="x", padx=14, pady=6)
        self.home_shop_label = tk.Label(
            shopf, text="Records load ho rahe hain...",
            bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold"))
        self.home_shop_label.pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(shopf, text="Records sirf is PC par mehfooz hain "
                             "(local SQLite) — koi server nahi, "
                             "internet ho ya na ho dukaan chalti hai.",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        srow = tk.Frame(shopf, bg=PANEL)
        srow.pack(fill="x", padx=8, pady=8)
        for text, key in (("👥 CUSTOMERS", "customers"),
                          ("🎫 REPAIR JOBS", "jobs")):
            tk.Button(srow, text=text, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=10, pady=6,
                      command=lambda k=key: self.show_module(k)
                      ).pack(side="left", padx=3)
        tk.Label(card, text="Har operation asal engine par chalta hai "
                            "aur output neeche LIVE LOG me stream hota "
                            "hai. Pehle poora flow dekhna ho to upar "
                            "▶ DEMO MODE dabao.",
                 bg=PANEL, fg=MUTED, wraplength=760, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=8)
        return f

    def _refresh_home_shop(self):
        """HOME ke dukaan hisab wale label ko taza numbers do."""
        lbl = getattr(self, "home_shop_label", None)
        if lbl is None:
            return
        try:
            st = shop_db.stats()
        except Exception as e:  # noqa: BLE001
            lbl.configure(text=f"Dukaan records load nahi ho sake: {e}")
            return
        lbl.configure(
            text=f"Aaj ke jobs: {st['today_jobs']}      ·      "
                 f"Pending (deliver baqi): {st['pending_jobs']}      "
                 f"·      Kul customers: {st['total_customers']}      "
                 f"·      Kul jobs: {st['total_jobs']}")

    # ------------------------------------------------------- PLATFORMS ---
    def _build_platforms(self, parent):
        f = tk.Frame(parent, bg=BG)
        hdr = tk.Frame(f, bg=PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="MediaTek", bg=PANEL, fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=10,
                                                     pady=6)
        self.plat_android_var = tk.BooleanVar(value=True)
        self.plat_realme_var = tk.BooleanVar(value=False)
        self.plat_xiaomi_var = tk.BooleanVar(value=False)
        self.plat_isp_var = tk.BooleanVar(value=False)
        for text, var in (("Android Info", self.plat_android_var),
                          ("Realme Auth", self.plat_realme_var),
                          ("Xiaomi Auth", self.plat_xiaomi_var),
                          ("ISP Mode", self.plat_isp_var)):
            tk.Checkbutton(hdr, text=text, variable=var, bg=PANEL, fg=FG,
                           selectcolor=PANEL2, activebackground=PANEL,
                           activeforeground=FG,
                           font=("Segoe UI", 8)).pack(side="left", padx=4)
        tk.Label(hdr, text="(Auth routes SERVER REQUIRED hain — log me "
                           "wazahat ayegi)",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=6)
        sub = tk.Frame(f, bg=BG)
        sub.pack(fill="x", pady=(4, 2))
        self.plat_sub_btns = {}
        for key, title in (("flash", "Flash"), ("fastboot", "Fastboot"),
                           ("meta", "Meta"),
                           ("filemgr", "File Manager"),
                           ("network", "Network")):
            btn = tk.Button(sub, text=title, relief="flat",
                            font=("Segoe UI", 9, "bold"), padx=10, pady=3,
                            bg=ACCENT if key == "flash" else PANEL2,
                            fg="#111" if key == "flash" else FG,
                            command=lambda k=key: self._plat_subtab(k))
            btn.pack(side="left", padx=(0, 4))
            self.plat_sub_btns[key] = btn
        self.plat_sub_frames = {
            "flash": self._plat_flash_tab(f),
            "fastboot": self._plat_simple_tab(
                f, "Fastboot mode wale asal ops:",
                [("fastboot_info", "READ INFO - [FASTBOOT]"),
                 ("fastboot_reboot", "REBOOT - [FASTBOOT]")]),
            "meta": self._plat_simple_tab(
                f, "META mode (Transsion service mode) ka guided flow:",
                [("mdm_meta_guide", "META GUIDE - [Platforms]")]),
            "filemgr": self._plat_fm_tab(f),
            "network": self._plat_simple_tab(
                f, "MTK Network/IMEI ka kaam is build me MDM List ke "
                   "Network tab (Unisoc) aur ops tree se hota hai — "
                   "yahan koi nakli button nahi rakha gaya.", []),
        }
        self.plat_sub_frames["flash"].pack(fill="both", expand=True)
        return f

    def _plat_simple_tab(self, parent, note, pairs):
        fr = tk.Frame(parent, bg=PANEL)
        tk.Label(fr, text=note, bg=PANEL, fg=MUTED, wraplength=760,
                 justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=8,
                                            pady=(6, 4))
        box = tk.Frame(fr, bg=PANEL)
        box.pack(fill="x", padx=8, pady=(0, 8))
        self._tab_ops_lazy(box, pairs)
        return fr

    def _plat_fm_tab(self, parent):
        fr = tk.Frame(parent, bg=PANEL)
        tk.Label(fr, text="MTK File Manager ka Windows par seedha rasta "
                          "is build me nahi hai — asal wajah aur chalta "
                          "hua rasta (Utility File Manager) is guide me "
                          "hai:",
                 bg=PANEL, fg=MUTED, wraplength=760, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=8,
                                            pady=(6, 4))
        tk.Button(fr, text="FILE MANAGER GUIDE - [MTK]", bg=PANEL2,
                  fg=FG, relief="flat", font=("Segoe UI", 8, "bold"),
                  padx=8, pady=4,
                  command=lambda: self._run_action(
                      platforms_mtk.file_manager_guide_op())
                  ).pack(anchor="w", padx=8, pady=(0, 8))
        return fr

    def _plat_flash_tab(self, parent):
        fr = tk.Frame(parent, bg=PANEL)
        cfg = tk.LabelFrame(fr, text=" CONFIG ", bg=PANEL, fg=MUTED,
                            font=("Segoe UI", 8, "bold"), bd=1)
        cfg.pack(fill="x", padx=8, pady=(6, 2))
        r1 = tk.Frame(cfg, bg=PANEL)
        r1.pack(fill="x", padx=6, pady=3)
        tk.Label(r1, text="Devices:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.plat_brand_var = tk.StringVar(value="Infinix")
        ttk.Combobox(r1, textvariable=self.plat_brand_var, width=14,
                     state="readonly",
                     values=["Infinix", "Tecno", "Itel", "Samsung",
                             "Xiaomi", "Realme", "Oppo", "Vivo"]
                     ).pack(side="left", padx=4)
        tk.Label(r1, text="Mode:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))
        ttk.Combobox(r1, values=["Download Only"], width=15,
                     state="readonly").pack(side="left", padx=4)
        tk.Label(r1, text="DA Mode:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))
        ttk.Combobox(r1, values=["AUTO"], width=8,
                     state="readonly").pack(side="left", padx=4)
        r2 = tk.Frame(cfg, bg=PANEL)
        r2.pack(fill="x", padx=6, pady=3)
        tk.Label(r2, text="DA File:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.plat_da_var = tk.StringVar()
        self.plat_da_combo = ttk.Combobox(
            r2, textvariable=self.plat_da_var, state="readonly", width=46)
        self.plat_da_combo.pack(side="left", padx=4)
        tk.Button(r2, text="↻ Refresh", bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8),
                  command=self._plat_refresh_da).pack(side="left")
        r3 = tk.Frame(cfg, bg=PANEL)
        r3.pack(fill="x", padx=6, pady=3)
        tk.Label(r3, text="Firmware (scatter):", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.plat_scatter_var = tk.StringVar()
        tk.Entry(r3, textvariable=self.plat_scatter_var, bg=PANEL2,
                 fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 8), width=52).pack(side="left", padx=4)
        tk.Button(r3, text="Browse…", bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8),
                  command=self._plat_pick_scatter).pack(side="left")
        self.plat_scatter_on_var = tk.BooleanVar(value=False)
        tk.Checkbutton(r3, text="As Scatter", bg=PANEL, fg=FG,
                       variable=self.plat_scatter_on_var,
                       selectcolor=PANEL2, activebackground=PANEL,
                       activeforeground=FG,
                       font=("Segoe UI", 8)).pack(side="left", padx=6)
        # Toolbar: search + checkboxes
        tb = tk.Frame(fr, bg=PANEL)
        tb.pack(fill="x", padx=8, pady=2)
        tk.Label(tb, text="Search partition…", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.plat_search_var = tk.StringVar()
        self.plat_search_var.trace_add(
            "write", lambda *_a: self._plat_fill_table())
        tk.Entry(tb, textvariable=self.plat_search_var, bg=PANEL2, fg=FG,
                 insertbackground=FG, relief="flat",
                 font=("Segoe UI", 8), width=22).pack(side="left", padx=4)
        self.plat_reboot_var = tk.BooleanVar(value=False)
        self.plat_crash_var = tk.BooleanVar(value=False)
        for text, var in (("Auto Reboot", self.plat_reboot_var),
                          ("Crash PL To Brom", self.plat_crash_var)):
            tk.Checkbutton(tb, text=text, variable=var, bg=PANEL, fg=FG,
                           selectcolor=PANEL2, activebackground=PANEL,
                           activeforeground=FG,
                           font=("Segoe UI", 8)).pack(side="left", padx=6)
        # Actions — bottom se anchor (pehle bana kar pack karo taake
        # table ki expand inhen dhakel na de)
        act = tk.Frame(fr, bg=PANEL)
        act.pack(side="bottom", fill="x", padx=8, pady=(2, 8))
        for text, cmd in (
                ("Identify", self._plat_identify),
                ("Backup", self._plat_backup),
                ("Erase", self._plat_erase),
                ("Flash", self._plat_flash),
                ("Reboot", self._plat_reboot)):
            tk.Button(act, text=text, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=14, pady=4,
                      command=cmd).pack(side="left", padx=3)
        tk.Label(act, text="Partition par click = select; File column "
                           "par double-click = file chuno. Pehle "
                           "Identify se GPT table bharo.",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=8)
        # Partition table
        cols = ("sel", "name", "file", "start", "size", "region", "block")
        self.plat_tree = ttk.Treeview(fr, columns=cols, show="headings",
                                      height=8, selectmode="browse")
        for col, title, width in (
                ("sel", "✓", 32), ("name", "Partition", 150),
                ("file", "File", 250), ("start", "Start", 110),
                ("size", "Size", 90), ("region", "Region", 70),
                ("block", "Block", 80)):
            self.plat_tree.heading(col, text=title)
            self.plat_tree.column(col, width=width, anchor="w")
        plat_sb = ttk.Scrollbar(fr, command=self.plat_tree.yview)
        self.plat_tree.configure(yscrollcommand=plat_sb.set)
        plat_sb.pack(side="right", fill="y", pady=2)
        self.plat_tree.pack(fill="both", expand=True, padx=(8, 0), pady=2)
        self.plat_tree.bind("<Button-1>", self._plat_on_click)
        self.plat_tree.bind("<Double-1>", self._plat_on_dblclick)
        self._plat_refresh_da()
        return fr

    def _plat_subtab(self, key):
        self.plat_sub = key
        for k, frame in self.plat_sub_frames.items():
            if k == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for k, btn in self.plat_sub_btns.items():
            active = k == key
            btn.configure(bg=ACCENT if active else PANEL2,
                          fg="#111" if active else FG)

    def _plat_refresh_da(self):
        if not hasattr(self, "plat_da_combo"):
            return
        files = mdm_list.da_files()
        self._plat_da_paths = files
        labels = []
        for p in files:
            try:
                labels.append(str(p.relative_to(TOOLS_DIR / "loaders")))
            except Exception:
                labels.append(p.name)
        if not labels:
            labels = ["(koi DA nahi — tools/loaders me .bin rakho)"]
        self.plat_da_combo.configure(values=labels)
        self.plat_da_combo.current(0)

    def _plat_selected_da(self):
        idx = self.plat_da_combo.current() \
            if hasattr(self, "plat_da_combo") else -1
        paths = getattr(self, "_plat_da_paths", [])
        if 0 <= idx < len(paths):
            return paths[idx]
        return None

    def _plat_pick_scatter(self):
        path = filedialog.askopenfilename(
            title="Scatter file select karo",
            filetypes=[("Scatter", "*scatter*.txt"),
                       ("Text", "*.txt"), ("Tamam files", "*.*")])
        if path:
            self.plat_scatter_var.set(path)
            self.plat_scatter_on_var.set(True)

    def _plat_opts(self):
        auth = None
        if self.plat_realme_var.get():
            auth = "Realme"
        elif self.plat_xiaomi_var.get():
            auth = "Xiaomi"
        return {"da": self._plat_selected_da(),
                "crash_first": bool(self.plat_crash_var.get()),
                "auto_reboot": bool(self.plat_reboot_var.get()),
                "android_info": bool(self.plat_android_var.get()),
                "auth": auth}

    def _plat_pre(self):
        if self.plat_isp_var.get():
            self.log_line("ISP Mode: is build me MTKClient ka koi ISP "
                          "(tash-khass pinout) rasta nahi hai — aam "
                          "BROM/Preloader route hi chalega.", "WARN")

    def _plat_set_parts(self, parts):
        keep = {p["name"]: p.get("file", "")
                for p in self.plat_parts}
        self.plat_parts = []
        for p in parts:
            entry = dict(p)
            entry["file"] = keep.get(p["name"], "")
            self.plat_parts.append(entry)
        self.plat_selected &= {p["name"] for p in self.plat_parts}
        self._plat_fill_table()

    @staticmethod
    def _human_size(size):
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size // 1024} KB"
        return f"{size} B"

    def _plat_fill_table(self):
        if not hasattr(self, "plat_tree"):
            return
        q = self.plat_search_var.get().strip().lower() \
            if hasattr(self, "plat_search_var") else ""
        for item in self.plat_tree.get_children():
            self.plat_tree.delete(item)
        self._plat_items = {}
        for p in self.plat_parts:
            if q and q not in p["name"].lower():
                continue
            fpath = p.get("file") or ""
            item = self.plat_tree.insert(
                "", "end", values=(
                    "☑" if p["name"] in self.plat_selected else "☐",
                    p["name"],
                    str(fpath).replace("\\", "/").split("/")[-1]
                    if fpath else "—",
                    f"0x{p['start']:x}", self._human_size(p["size"]),
                    p.get("region", "—"), p.get("block", 0)))
            self._plat_items[item] = p["name"]

    def _plat_on_click(self, event):
        if self.plat_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.plat_tree.identify_column(event.x) != "#1":
            return
        item = self.plat_tree.identify_row(event.y)
        name = getattr(self, "_plat_items", {}).get(item)
        if not name:
            return
        if name in self.plat_selected:
            self.plat_selected.discard(name)
        else:
            self.plat_selected.add(name)
        self._plat_fill_table()

    def _plat_on_dblclick(self, event):
        if self.plat_tree.identify_column(event.x) != "#3":
            return
        item = self.plat_tree.identify_row(event.y)
        name = getattr(self, "_plat_items", {}).get(item)
        if not name:
            return
        path = filedialog.askopenfilename(
            title=f"{name} ke liye file select karo",
            filetypes=[("Binary/images", "*.bin *.img"),
                       ("Tamam files", "*.*")])
        if not path:
            return
        for p in self.plat_parts:
            if p["name"] == name:
                p["file"] = path
        self.plat_selected.add(name)
        self._plat_fill_table()

    def _plat_names(self):
        return [p["name"] for p in self.plat_parts
                if p["name"] in self.plat_selected]

    def _plat_identify(self):
        self._plat_pre()
        op = platforms_mtk.identify_op(
            lambda parts: self.ui_q.put(("plat_gpt", parts)),
            self._plat_opts())
        self._run_action(op)

    def _plat_backup(self):
        self._plat_pre()
        self._run_action(platforms_mtk.backup_op(self._plat_names(),
                                                 self._plat_opts()))

    def _plat_erase(self):
        self._plat_pre()
        self._run_action(platforms_mtk.erase_op(self._plat_names(),
                                                self._plat_opts()))

    def _plat_flash(self):
        self._plat_pre()
        names = self._plat_names()
        if self.plat_scatter_on_var.get() \
                and self.plat_scatter_var.get().strip():
            self._run_action(platforms_mtk.flash_scatter_op(
                self.plat_scatter_var.get().strip(), names,
                self._plat_opts()))
            return
        pairs = [(p["name"], p["file"]) for p in self.plat_parts
                 if p["name"] in self.plat_selected and p.get("file")]
        self._run_action(platforms_mtk.flash_op(pairs, self._plat_opts()))

    def _plat_reboot(self):
        self._plat_pre()
        self._run_action(platforms_mtk.reboot_op(self._plat_opts()))

    # --------------------------------------------------------- UTILITY ---
    def _build_utility(self, parent):
        f = tk.Frame(parent, bg=BG)
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x")
        adb_box = tk.LabelFrame(top, text=" ADB TOOLS ", bg=PANEL,
                                fg=MUTED, font=("Segoe UI", 9, "bold"),
                                bd=1)
        adb_box.pack(side="left", fill="both", expand=True,
                     padx=(0, 4), pady=2)
        self._tab_ops_lazy(adb_box, [
            ("adb_info", "READ DEVICE INFO - [ADB]"),
            ("adb_reboot", "REBOOT - [ADB]"),
            ("adb_reboot_bootloader", "REBOOT → BOOTLOADER - [ADB]"),
            ("adb_reboot_recovery", "REBOOT → RECOVERY - [ADB]"),
            ("mdm_adb_check", "MDM CHECK - [ADB]")])
        fb_box = tk.LabelFrame(top, text=" FASTBOOT TOOLS ", bg=PANEL,
                               fg=MUTED, font=("Segoe UI", 9, "bold"),
                               bd=1)
        fb_box.pack(side="left", fill="both", expand=True,
                    padx=(4, 0), pady=2)
        self._tab_ops_lazy(fb_box, [
            ("fastboot_info", "READ INFO - [FASTBOOT]"),
            ("fastboot_reboot", "REBOOT - [FASTBOOT]")])
        row2 = tk.Frame(f, bg=BG)
        row2.pack(fill="x", pady=(6, 0))
        pc_box = tk.LabelFrame(row2, text=" PC TOOLS ", bg=PANEL,
                               fg=MUTED, font=("Segoe UI", 9, "bold"),
                               bd=1)
        pc_box.pack(side="left", fill="both", expand=True,
                    padx=(0, 4), pady=2)
        self._tab_ops_lazy(pc_box, [
            ("util_install_drivers", "INSTALL DRIVERS - [PC]"),
            ("util_update_check", "UPDATE CHECK - [PC]")])
        fw_box = tk.LabelFrame(row2, text=" FIRMWARE FRONT DOOR ", bg=PANEL,
                               fg=MUTED, font=("Segoe UI", 9, "bold"),
                               bd=1)
        fw_box.pack(side="left", fill="both", expand=True,
                    padx=(4, 0), pady=2)
        self._tab_ops_lazy(fw_box, [
            ("fw_archive_extract", "ARCHIVE KHOLO (ZIP/TGZ → SCATTER)"),
            ("fw_ofp_extract", "OFP / OZIP EXTRACT (OPPO/REALME)"),
            ("fw_payload_extract", "PAYLOAD.BIN EXTRACT (OTA)")])
        fm = tk.LabelFrame(f, text=" FILE MANAGER (ADB) ", bg=PANEL,
                           fg=MUTED, font=("Segoe UI", 9, "bold"), bd=1)
        fm.pack(fill="both", expand=True, pady=(6, 0))
        row = tk.Frame(fm, bg=PANEL)
        row.pack(fill="x", padx=6, pady=4)
        tk.Label(row, text="Path:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.fm_path_var = tk.StringVar(value="/sdcard/")
        tk.Entry(row, textvariable=self.fm_path_var, bg=PANEL2, fg=FG,
                 insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9), width=44).pack(side="left", padx=4)
        for text, cmd in (("LIST", self._fm_list),
                          ("⬆ UP", self._fm_up),
                          ("⬇ PULL (PC par)", self._fm_pull),
                          ("⬆ PUSH (phone par)", self._fm_push)):
            tk.Button(row, text=text, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 8, "bold"), padx=8, pady=3,
                      command=cmd).pack(side="left", padx=2)
        self.fm_tree = ttk.Treeview(
            fm, columns=("name", "size", "when"), show="headings",
            height=8, selectmode="browse")
        for col, title, width in (("name", "Name", 320),
                                  ("size", "Size", 110),
                                  ("when", "Date", 150)):
            self.fm_tree.heading(col, text=title)
            self.fm_tree.column(col, width=width, anchor="w")
        self.fm_tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.fm_tree.bind("<Double-1>", self._fm_open_selected)
        return f

    def _fm_list(self):
        path = self.fm_path_var.get().strip() or "/"
        op = utility.list_op(
            path, lambda p, e: self.ui_q.put(("fm_entries", p, e)))
        self._run_action(op)

    def _fm_set_entries(self, path, entries):
        self.fm_path = path
        self.fm_path_var.set(path)
        for item in self.fm_tree.get_children():
            self.fm_tree.delete(item)
        self.fm_items = {}
        for e in entries:
            label = ("📁 " if e["is_dir"] else "📄 ") + e["name"]
            item = self.fm_tree.insert(
                "", "end", values=(label, e["size"], e["when"]))
            self.fm_items[item] = e

    def _fm_selected_entry(self):
        sel = self.fm_tree.selection()
        return self.fm_items.get(sel[0]) if sel else None

    def _fm_open_selected(self, _event=None):
        entry = self._fm_selected_entry()
        if not entry or not entry["is_dir"]:
            return
        base = (self.fm_path_var.get().strip() or "/").rstrip("/")
        self.fm_path_var.set(base + "/" + entry["name"] + "/")
        self._fm_list()

    def _fm_up(self):
        path = (self.fm_path_var.get().strip() or "/").rstrip("/")
        parent = path.rsplit("/", 1)[0] or "/"
        self.fm_path_var.set(parent + ("/" if parent != "/" else ""))
        self._fm_list()

    def _fm_pull(self):
        entry = self._fm_selected_entry()
        if entry is None:
            self.log_line("PULL ke liye pehle list se file/folder "
                          "select karo.", "WARN")
            return
        base = (self.fm_path_var.get().strip() or "/").rstrip("/")
        self._run_action(utility.pull_op(base + "/" + entry["name"]))

    def _fm_push(self):
        path = filedialog.askopenfilename(
            title="Phone par bhejne wali file select karo")
        if not path:
            return
        dest = self.fm_path_var.get().strip() or "/sdcard/"
        self._run_action(utility.push_op(path, dest))

    # ------------------------------------------- SUITE: SHOP (Phase 1) --
    def _init_shop(self):
        """Dukaan records (SQLite, LOCAL) tayyar karo + pehla refresh."""
        try:
            path = shop_db.init_db()
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Dukaan records (shop.db) nahi ban sake: {e}",
                          "ERROR")
            return
        try:
            st = shop_db.stats()
            self.log_line(
                f"Dukaan records tayyar (local): "
                f"{st['total_customers']} customers, {st['total_jobs']} "
                f"jobs — {path}", "INFO")
            self.shop_name_var.set(shop_db.shop_name())
        except Exception:  # noqa: BLE001
            pass
        self._refresh_home_shop()
        self._refresh_customers()
        self._refresh_job_customers()
        self._refresh_jobs()

    @staticmethod
    def _parse_money(text):
        t = str(text or "").replace(",", "").replace("Rs", "").strip()
        try:
            return float(t) if t else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _money_text(value):
        try:
            v = float(value or 0)
        except (TypeError, ValueError):
            v = 0.0
        return "%g" % v if v else ""

    # ---------------------------------------------------- CUSTOMERS -----
    def _build_customers(self, parent):
        f = tk.Frame(parent, bg=BG)
        top = tk.Frame(f, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text="👥 CUSTOMER MANAGER", bg=PANEL, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=10,
                                                      pady=6)
        tk.Label(top, text="Dukaan ka naam (receipt par):", bg=PANEL,
                 fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(14, 2))
        self.shop_name_var = tk.StringVar(
            value=shop_db.DEFAULT_SHOP_NAME)
        tk.Entry(top, textvariable=self.shop_name_var, bg=PANEL2,
                 fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9), width=24).pack(side="left")
        tk.Button(top, text="Naam Save", bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8, "bold"), padx=8, pady=3,
                  command=self._cust_save_shop_name).pack(side="left",
                                                          padx=4)
        tk.Button(top, text="📤 CSV EXPORT", bg=PANEL2, fg=FG,
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=8,
                  pady=3,
                  command=self._cust_export).pack(side="right", padx=4)
        tk.Button(top, text="💾 BACKUP (shop.db)", bg=PANEL2, fg=FG,
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=8,
                  pady=3,
                  command=self._cust_backup).pack(side="right",
                                                  padx=(4, 0))

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, pady=(6, 0))
        form = tk.LabelFrame(body, text=" CUSTOMER ", bg=PANEL,
                             fg=MUTED, font=("Segoe UI", 9, "bold"),
                             bd=1, width=336)
        form.pack(side="left", fill="y")
        form.pack_propagate(False)
        self.cust_name_var = tk.StringVar()
        self.cust_phone_var = tk.StringVar()
        self.cust_addr_var = tk.StringVar()
        for row, (label, var) in enumerate((
                ("Naam *", self.cust_name_var),
                ("Phone", self.cust_phone_var),
                ("Address", self.cust_addr_var))):
            tk.Label(form, text=label, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8)).grid(
                         row=row, column=0, sticky="w", padx=8, pady=3)
            tk.Entry(form, textvariable=var, bg=PANEL2, fg=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=30).grid(
                         row=row, column=1, sticky="w", pady=3)
        tk.Label(form, text="Notes", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=3, column=0, sticky="nw",
                                            padx=8, pady=3)
        self.cust_notes_txt = tk.Text(
            form, bg=PANEL2, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 9), height=4, width=30, wrap="word")
        self.cust_notes_txt.grid(row=3, column=1, sticky="w", pady=3)
        self.cust_info_label = tk.Label(
            form, text="", bg=PANEL, fg=ACCENT, wraplength=300,
            justify="left", font=("Segoe UI", 8))
        self.cust_info_label.grid(row=4, column=0, columnspan=2,
                                  sticky="w", padx=8, pady=(6, 2))
        btnrow = tk.Frame(form, bg=PANEL)
        btnrow.grid(row=5, column=0, columnspan=2, sticky="w",
                    padx=8, pady=4)
        self.cust_save_btn = tk.Button(
            btnrow, text="➕ NAYA CUSTOMER", bg=GREEN, fg="#0b0e13",
            relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
            pady=5, command=self._cust_save)
        self.cust_save_btn.pack(side="left")
        tk.Button(btnrow, text="🧹 Saaf", bg=PANEL2, fg=FG,
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
                  pady=5, command=self._cust_clear).pack(side="left",
                                                         padx=4)
        tk.Label(form, text="Record sirf is PC par rehta hai "
                            "(tools/shop.db) — koi server, koi "
                            "internet nahi. Backup/Export upar hai.",
                 bg=PANEL, fg=MUTED, wraplength=300, justify="left",
                 font=("Segoe UI", 8)).grid(row=6, column=0, columnspan=2,
                                            sticky="w", padx=8, pady=6)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        srow = tk.Frame(right, bg=BG)
        srow.pack(fill="x", pady=(0, 4))
        tk.Label(srow, text="Talash:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.cust_search_var = tk.StringVar()
        self.cust_search_var.trace_add(
            "write", lambda *_a: self._refresh_customers())
        tk.Entry(srow, textvariable=self.cust_search_var, bg=PANEL2,
                 fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9), width=36).pack(side="left", padx=4)
        self.cust_tree = ttk.Treeview(
            right, columns=("name", "phone", "address", "jobs"),
            show="headings", selectmode="browse")
        for col, title, width in (("name", "Naam", 210),
                                  ("phone", "Phone", 140),
                                  ("address", "Address", 300),
                                  ("jobs", "Jobs", 60)):
            self.cust_tree.heading(col, text=title)
            self.cust_tree.column(col, width=width, anchor="w")
        self.cust_tree.pack(fill="both", expand=True)
        self.cust_tree.bind("<<TreeviewSelect>>", self._cust_on_select)
        return f

    def _refresh_customers(self):
        tree = getattr(self, "cust_tree", None)
        if tree is None:
            return
        try:
            rows = shop_db.search_customers(self.cust_search_var.get())
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Customers load nahi ho sake: {e}", "ERROR")
            return
        for item in tree.get_children():
            tree.delete(item)
        self.cust_items = {}
        for c in rows:
            item = tree.insert("", "end", values=(
                c["name"], c["phone"], c["address"], c["jobs_count"]))
            self.cust_items[item] = c["id"]

    def _cust_on_select(self, _event=None):
        sel = self.cust_tree.selection()
        cid = self.cust_items.get(sel[0]) if sel else None
        if cid is None:
            return
        try:
            c = shop_db.get_customer(cid)
            njobs = len(shop_db.customer_jobs(cid))
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Customer load nahi ho saka: {e}", "ERROR")
            return
        if c is None:
            return
        self.cust_selected_id = cid
        self.cust_name_var.set(c["name"])
        self.cust_phone_var.set(c["phone"])
        self.cust_addr_var.set(c["address"])
        self.cust_notes_txt.delete("1.0", "end")
        self.cust_notes_txt.insert("1.0", c["notes"])
        self.cust_info_label.configure(
            text=f"Customer #{cid} — is ke {njobs} repair jobs hain.")
        self.cust_save_btn.configure(text="💾 SAVE (UPDATE)")

    def _cust_clear(self):
        self.cust_selected_id = None
        self.cust_name_var.set("")
        self.cust_phone_var.set("")
        self.cust_addr_var.set("")
        self.cust_notes_txt.delete("1.0", "end")
        self.cust_info_label.configure(text="")
        self.cust_save_btn.configure(text="➕ NAYA CUSTOMER")
        if hasattr(self, "cust_tree"):
            self.cust_tree.selection_remove(
                self.cust_tree.selection())

    def _cust_save(self):
        name = self.cust_name_var.get().strip()
        if not name:
            self.log_line("Customer ka naam lazmi hai — pehle naam "
                          "likho.", "WARN")
            return
        notes = self.cust_notes_txt.get("1.0", "end").strip()
        try:
            if self.cust_selected_id:
                shop_db.update_customer(
                    self.cust_selected_id, name,
                    self.cust_phone_var.get(), self.cust_addr_var.get(),
                    notes)
                self.log_line(f"Customer update ho gaya: {name}", "OK")
            else:
                cid = shop_db.add_customer(
                    name, self.cust_phone_var.get(),
                    self.cust_addr_var.get(), notes)
                self.log_line(f"Naya customer ban gaya: {name} "
                              f"(#{cid})", "OK")
        except ValueError as e:
            self.log_line(str(e), "WARN")
            return
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Customer save nahi ho saka: {e}", "ERROR")
            return
        self._cust_clear()
        self._refresh_customers()
        self._refresh_home_shop()
        self._refresh_job_customers()

    def _cust_save_shop_name(self):
        name = self.shop_name_var.get().strip()
        if not name:
            self.log_line("Dukaan ka naam khali nahi ho sakta.",
                          "WARN")
            return
        try:
            shop_db.set_setting("shop_name", name)
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Naam save nahi ho saka: {e}", "ERROR")
            return
        self.log_line(f"Dukaan ka naam save ho gaya: {name} — ab "
                      "receipts par yahi ayega.", "OK")

    def _cust_backup(self):
        try:
            p = shop_db.backup_db()
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Backup nahi ban saka: {e}", "ERROR")
            return
        self.log_line(f"shop.db ki backup copy tayyar: {p} — isay "
                      "kahin mehfooz rakh lo (USB/email).", "OK")

    def _cust_export(self):
        d = filedialog.askdirectory(
            title="Customers/Jobs CSV kahan export karoon?",
            initialdir=str(TOOLS_DIR.parent))
        if not d:
            return
        try:
            cp, jp = shop_db.export_csv(Path(d))
        except Exception as e:  # noqa: BLE001
            self.log_line(f"CSV export nahi ho saka: {e}", "ERROR")
            return
        self.log_line(f"CSV export tayyar: {cp}", "OK")
        self.log_line(f"CSV export tayyar: {jp}", "OK")

    # ------------------------------------------------- FIRMWARE -------
    def _build_firmware(self, parent):
        f = tk.Frame(parent, bg=BG)
        top = tk.Frame(f, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text="📀 FIRMWARE CENTER", bg=PANEL, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left",
                                                     padx=10, pady=3)
        tk.Label(top, text="Firmware files yahan HOST nahi hotin — "
                           "sirf official links + records + "
                           "checksums. Asal file official source "
                           "se ati hai.",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=6)

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, pady=(3, 0))
        form = tk.LabelFrame(body, text=" FIRMWARE RECORD ",
                             bg=PANEL, fg=MUTED,
                             font=("Segoe UI", 9, "bold"), bd=1,
                             width=424)
        form.pack(side="left", fill="y")
        form.pack_propagate(False)
        self.fw_vars = {}

        def _fw_field(row, col, label, key, width, span=1):
            tk.Label(form, text=label, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8)).grid(
                         row=row, column=col, sticky="w",
                         padx=(8 if col == 0 else 4), pady=2)
            var = tk.StringVar()
            self.fw_vars[key] = var
            tk.Entry(form, textvariable=var, bg=PANEL2, fg=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=width).grid(
                         row=row, column=col + 1, columnspan=span,
                         sticky="w", pady=1)

        _fw_field(0, 0, "Brand *", "brand", 41, span=3)
        _fw_field(1, 0, "Model *", "model", 41, span=3)
        _fw_field(2, 0, "Code", "code", 14)
        _fw_field(2, 2, "Version", "version", 14)
        _fw_field(3, 0, "Android", "android", 14)
        _fw_field(3, 2, "Size", "size", 14)
        _fw_field(4, 0, "Official Link", "official_link", 41, span=3)
        _fw_field(5, 0, "SHA-256", "checksum_sha256", 41, span=3)
        nrow = 6
        tk.Label(form, text="Note", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=nrow, column=0,
                                            sticky="nw", padx=8,
                                            pady=2)
        self.fw_note_txt = tk.Text(
            form, bg=PANEL2, fg=FG, insertbackground=FG,
            relief="flat", font=("Segoe UI", 9), height=2, width=41,
            wrap="word")
        self.fw_note_txt.grid(row=nrow, column=1, columnspan=3,
                              sticky="w", pady=3)
        self.fw_info_label = tk.Label(
            form, text="", bg=PANEL, fg=ACCENT, wraplength=368,
            justify="left", font=("Segoe UI", 8))
        self.fw_info_label.grid(row=nrow + 1, column=0, columnspan=4,
                                sticky="w", padx=8, pady=(3, 0))
        btnrow = tk.Frame(form, bg=PANEL)
        btnrow.grid(row=nrow + 2, column=0, columnspan=4, sticky="w",
                    padx=8, pady=3)
        self.fw_save_btn = tk.Button(
            btnrow, text="➕ NAYA RECORD", bg=GREEN, fg="#0b0e13",
            relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
            pady=3, command=self._fw_save)
        self.fw_save_btn.pack(side="left")
        tk.Button(btnrow, text="🧹 Saaf", bg=PANEL2, fg=FG,
                  relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=10, pady=3,
                  command=self._fw_clear).pack(side="left", padx=4)
        tk.Label(form, text="Records: tools/firmware-catalog.json "
                            "(khud bhi edit ho sakti hai).",
                 bg=PANEL, fg=MUTED, wraplength=368, justify="left",
                 font=("Segoe UI", 8)).grid(
                     row=nrow + 3, column=0, columnspan=4,
                     sticky="w", padx=8, pady=(2, 4))

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True,
                   padx=(8, 0))
        srow = tk.Frame(right, bg=BG)
        srow.pack(fill="x", pady=(0, 4))
        tk.Label(srow, text="Talash:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.fw_search_var = tk.StringVar()
        self.fw_search_var.trace_add(
            "write", lambda *_a: self._refresh_firmware())
        tk.Entry(srow, textvariable=self.fw_search_var, bg=PANEL2,
                 fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9), width=36).pack(side="left",
                                                      padx=4)
        self.fw_tree = ttk.Treeview(
            right, columns=("brand", "model", "code", "version",
                            "android", "size"),
            show="headings", selectmode="browse", height=4)
        for col, title, width in (("brand", "Brand", 110),
                                  ("model", "Model", 170),
                                  ("code", "Code", 80),
                                  ("version", "Version", 90),
                                  ("android", "Android", 70),
                                  ("size", "Size", 90)):
            self.fw_tree.heading(col, text=title)
            self.fw_tree.column(col, width=width, anchor="w")
        self.fw_tree.pack(fill="x")
        self.fw_tree.bind("<<TreeviewSelect>>", self._fw_on_select)

        arow = tk.Frame(right, bg=BG)
        arow.pack(fill="x", pady=(6, 2))
        tk.Button(arow, text="📁 Downloaded File — Checksum Verify",
                  bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                  command=self._fw_verify_checksum).pack(
                      side="left")
        tk.Button(arow, text="🌾 Firmware → Loader Harvest",
                  bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                  command=lambda: self._run_lazy(
                      "fw_loader_harvest")).pack(side="left", padx=6)
        self.fw_verify_label = tk.Label(
            arow, text="Verify: pehle record select karo, phir "
                       "downloaded file chuno.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.fw_verify_label.pack(side="left", padx=4)
        tk.Label(right, text="Harvest: firmware file pehle "
                             "tools/firmware-inbox/ me rakho — "
                             "DA / firehose / preloader / lk / FDL "
                             "khud Loaders Library me darj ho "
                             "jayenge.",
                 bg=BG, fg=MUTED, wraplength=820, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))

        intel = tk.LabelFrame(right, text=" 🔧 REPAIR INTELLIGENCE ",
                              bg=PANEL, fg=MUTED,
                              font=("Segoe UI", 9, "bold"), bd=1)
        intel.pack(fill="both", expand=True)
        irow = tk.Frame(intel, bg=PANEL)
        irow.pack(fill="x", padx=6, pady=(3, 2))
        tk.Label(irow, text="Error code / naam:", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        self.fw_intel_var = tk.StringVar()
        tk.Entry(irow, textvariable=self.fw_intel_var, bg=PANEL2,
                 fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9), width=30).pack(side="left",
                                                      padx=4)
        tk.Button(irow, text="🔍 Dhoondo", bg=PANEL2, fg=FG,
                  relief="flat", font=("Segoe UI", 8, "bold"),
                  padx=8, pady=3,
                  command=self._fw_intel_search).pack(side="left")
        self.fw_intel_count = tk.Label(
            irow, text="", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 8))
        self.fw_intel_count.pack(side="left", padx=8)
        self.fw_intel_txt = tk.Text(
            intel, bg=PANEL2, fg=FG, insertbackground=FG,
            relief="flat", font=("Segoe UI", 8), height=3,
            wrap="word", state="disabled")
        self.fw_intel_txt.pack(fill="both", expand=True, padx=6,
                               pady=(2, 4))
        try:
            n = len(repair_intel.load_entries())
            self.fw_intel_count.configure(
                text=f"Library me {n} error patterns hain.")
            self._fw_intel_show(repair_intel.load_entries())
        except Exception:  # noqa: BLE001
            pass
        return f

    def _fw_intel_show(self, entries):
        txt = getattr(self, "fw_intel_txt", None)
        if txt is None:
            return
        lines = []
        for e in entries:
            head = e["title"]
            if e["code"]:
                head += f"  [{e['code']}]"
            lines.append(head)
            if e["wajah"]:
                lines.append(f"  Wajah: {e['wajah']}")
            for step in e["hal_steps"]:
                lines.append(f"  Hal: {step}")
            if e["source"]:
                lines.append(f"  Source: {e['source']}")
            lines.append("")
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("1.0", "\n".join(lines) if lines
                   else "Koi entry nahi mili.")
        txt.configure(state="disabled")

    def _fw_intel_search(self):
        q = self.fw_intel_var.get().strip()
        try:
            results = repair_intel.search(q)
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Repair Intelligence search fail: {e}",
                          "ERROR")
            return
        self.fw_intel_count.configure(
            text=f"{len(results)} entries mili"
                 + (f" — '{q}'" if q else " (tamam)."))
        self._fw_intel_show(results)

    def _refresh_firmware(self):
        tree = getattr(self, "fw_tree", None)
        if tree is None:
            return
        try:
            self.fw_catalog = firmware_catalog.load_catalog()
            rows = firmware_catalog.search_entries(
                self.fw_catalog, self.fw_search_var.get())
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Firmware catalogue load nahi ho saka: "
                          f"{e}", "ERROR")
            return
        for item in tree.get_children():
            tree.delete(item)
        self.fw_items = {}
        for idx, e in rows:
            item = tree.insert("", "end", values=(
                e["brand"], e["model"], e["code"], e["version"],
                e["android"], e["size"]))
            self.fw_items[item] = idx

    def _fw_on_select(self, _event=None):
        sel = self.fw_tree.selection()
        idx = self.fw_items.get(sel[0]) if sel else None
        if idx is None or self.fw_catalog is None:
            return
        try:
            e = self.fw_catalog["entries"][idx]
        except Exception:  # noqa: BLE001
            return
        self.fw_selected = idx
        for key, var in self.fw_vars.items():
            var.set(e.get(key, ""))
        self.fw_note_txt.delete("1.0", "end")
        self.fw_note_txt.insert("1.0", e.get("note", ""))
        self.fw_info_label.configure(
            text=f"Record #{idx + 1} — {e['brand']} {e['model']}.")
        self.fw_save_btn.configure(text="💾 SAVE (UPDATE)")

    def _fw_clear(self):
        self.fw_selected = None
        for var in self.fw_vars.values():
            var.set("")
        self.fw_note_txt.delete("1.0", "end")
        self.fw_info_label.configure(text="")
        self.fw_save_btn.configure(text="➕ NAYA RECORD")
        if hasattr(self, "fw_tree"):
            self.fw_tree.selection_remove(self.fw_tree.selection())

    def _fw_save(self):
        entry = {key: var.get() for key, var in self.fw_vars.items()}
        entry["note"] = self.fw_note_txt.get("1.0", "end").strip()
        try:
            if self.fw_catalog is None:
                self.fw_catalog = firmware_catalog.load_catalog()
            if self.fw_selected is not None:
                firmware_catalog.update_entry(
                    self.fw_catalog, self.fw_selected, entry)
                msg = (f"Firmware record update ho gaya: "
                       f"{entry['brand']} {entry['model']}")
            else:
                firmware_catalog.add_entry(self.fw_catalog, entry)
                msg = (f"Naya firmware record ban gaya: "
                       f"{entry['brand']} {entry['model']}")
            firmware_catalog.save_catalog(self.fw_catalog)
        except ValueError as e:
            self.log_line(str(e), "WARN")
            return
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Firmware record save nahi ho saka: {e}",
                          "ERROR")
            return
        self.log_line(msg + " (tools/firmware-catalog.json).", "OK")
        self._fw_clear()
        self._refresh_firmware()

    def _fw_verify_checksum(self):
        if self.fw_selected is None or self.fw_catalog is None:
            self.log_line("Checksum verify ke liye pehle upar ki "
                          "fehrist se aik firmware record select "
                          "karo.", "WARN")
            return
        entry = self.fw_catalog["entries"][self.fw_selected]
        if not str(entry.get("checksum_sha256", "")).strip():
            self.log_line("Is record me SHA-256 checksum darj "
                          "NAHI hai — pehle record me checksum "
                          "likho (official source se mila hua), "
                          "phir verify hoga.", "WARN")
            return
        path = filedialog.askopenfilename(
            title="Downloaded firmware file select karo",
            initialdir=str(TOOLS_DIR.parent))
        if not path:
            return
        status, actual = firmware_catalog.verify_checksum(entry,
                                                          path)
        name = Path(path).name
        if status == "match":
            self.fw_verify_label.configure(
                text=f"✔ MATCH — {name}", fg=GREEN)
            self.log_line(f"✔ CHECKSUM MATCH: {name} bilkul wahi "
                          "file hai jo record kehta hai "
                          f"({entry['brand']} {entry['model']} "
                          f"{entry['version']}). Flash ki taraf "
                          "barh sakte ho.", "OK")
        elif status == "mismatch":
            self.fw_verify_label.configure(
                text=f"✖ MISMATCH — {name}", fg="#f87171")
            self.log_line(f"✖ CHECKSUM MISMATCH: {name} record "
                          "wali file NAHI hai!", "ERROR")
            self.log_line(f"Record ka checksum: "
                          f"{entry['checksum_sha256']}", "DATA")
            self.log_line(f"Is file ka checksum: {actual}", "DATA")
            self.log_line("File badli hui ya kharab download ho "
                          "sakti hai — isay flash MAT karo. "
                          "Official source se dobara download "
                          "karo.", "WARN")
        else:
            self.log_line(f"File parhi nahi ja saki: {path}",
                          "ERROR")

    # --------------------------------------------------------- JOBS -------
    def _build_jobs(self, parent):
        f = tk.Frame(parent, bg=BG)
        top = tk.Frame(f, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text="🎫 REPAIR JOBS", bg=PANEL, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left",
                                                     padx=10, pady=6)
        tk.Label(top, text="Select kiye job ka status aik click me:",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 2))
        for text, status in (("▶ IN PROGRESS", "In Progress"),
                             ("✔ DONE", "Done"),
                             ("📦 DELIVERED", "Delivered")):
            tk.Button(top, text=text, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 8, "bold"), padx=8, pady=3,
                      command=lambda s=status: self._job_quick_status(s)
                      ).pack(side="left", padx=2)
        tk.Button(top, text="🧾 RECEIPT", bg=ACCENT, fg="#111",
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=10,
                  pady=3,
                  command=self._job_receipt).pack(side="right", padx=6)

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, pady=(6, 0))
        form = tk.LabelFrame(body, text=" JOB CARD ", bg=PANEL,
                             fg=MUTED, font=("Segoe UI", 9, "bold"),
                             bd=1, width=348)
        form.pack(side="left", fill="y")
        form.pack_propagate(False)
        self.job_cust_var = tk.StringVar()
        self.job_brand_var = tk.StringVar()
        self.job_model_var = tk.StringVar()
        self.job_imei_var = tk.StringVar()
        self.job_status_var = tk.StringVar(value="Received")
        self.job_est_var = tk.StringVar()
        self.job_final_var = tk.StringVar()
        self.job_received_var = tk.StringVar(
            value=date.today().isoformat())
        self.job_delivered_var = tk.StringVar()
        tk.Label(form, text="Customer *", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w",
                                            padx=8, pady=3)
        crow = tk.Frame(form, bg=PANEL)
        crow.grid(row=0, column=1, sticky="w", pady=3)
        self.job_cust_combo = ttk.Combobox(
            crow, textvariable=self.job_cust_var, state="readonly",
            width=26)
        self.job_cust_combo.pack(side="left")
        tk.Button(crow, text="↻", bg=PANEL2, fg=FG, relief="flat",
                  font=("Segoe UI", 8),
                  command=self._refresh_job_customers).pack(side="left",
                                                            padx=2)
        for row, (label, var) in enumerate((
                ("Brand", self.job_brand_var),
                ("Model", self.job_model_var),
                ("IMEI (record)", self.job_imei_var)), start=1):
            tk.Label(form, text=label, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8)).grid(
                         row=row, column=0, sticky="w", padx=8, pady=3)
            tk.Entry(form, textvariable=var, bg=PANEL2, fg=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=28).grid(
                         row=row, column=1, sticky="w", pady=3)
        tk.Label(form, text="Masla *", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=4, column=0, sticky="nw",
                                            padx=8, pady=3)
        self.job_problem_txt = tk.Text(
            form, bg=PANEL2, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 9), height=3, width=28, wrap="word")
        self.job_problem_txt.grid(row=4, column=1, sticky="w", pady=3)
        tk.Label(form, text="Status", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=5, column=0, sticky="w",
                                            padx=8, pady=3)
        ttk.Combobox(form, textvariable=self.job_status_var,
                     values=list(shop_db.STATUSES), state="readonly",
                     width=26).grid(row=5, column=1, sticky="w", pady=3)
        for row, (label, var) in enumerate((
                ("Estimate (Rs)", self.job_est_var),
                ("Final (Rs)", self.job_final_var),
                ("Received date", self.job_received_var),
                ("Delivered date", self.job_delivered_var)), start=6):
            tk.Label(form, text=label, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8)).grid(
                         row=row, column=0, sticky="w", padx=8, pady=3)
            tk.Entry(form, textvariable=var, bg=PANEL2, fg=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=28).grid(
                         row=row, column=1, sticky="w", pady=3)
        self.job_info_label = tk.Label(
            form, text="", bg=PANEL, fg=ACCENT, wraplength=310,
            justify="left", font=("Segoe UI", 8))
        self.job_info_label.grid(row=10, column=0, columnspan=2,
                                 sticky="w", padx=8, pady=(6, 2))
        btnrow = tk.Frame(form, bg=PANEL)
        btnrow.grid(row=11, column=0, columnspan=2, sticky="w",
                    padx=8, pady=4)
        self.job_save_btn = tk.Button(
            btnrow, text="➕ NAYA JOB", bg=GREEN, fg="#0b0e13",
            relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
            pady=5, command=self._job_save)
        self.job_save_btn.pack(side="left")
        tk.Button(btnrow, text="🧹 Saaf", bg=PANEL2, fg=FG,
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
                  pady=5, command=self._job_clear).pack(side="left",
                                                        padx=4)
        tk.Label(form, text="IMEI yahan sirf job card ke record ke "
                            "liye hai — koi device write nahi hota. "
                            "Delivered karne par date khud lag jati "
                            "hai.",
                 bg=PANEL, fg=MUTED, wraplength=310, justify="left",
                 font=("Segoe UI", 8)).grid(row=12, column=0,
                                            columnspan=2, sticky="w",
                                            padx=8, pady=6)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        frow = tk.Frame(right, bg=BG)
        frow.pack(fill="x", pady=(0, 4))
        tk.Label(frow, text="Talash:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.job_search_var = tk.StringVar()
        self.job_search_var.trace_add(
            "write", lambda *_a: self._refresh_jobs())
        tk.Entry(frow, textvariable=self.job_search_var, bg=PANEL2,
                 fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9), width=30).pack(side="left", padx=4)
        tk.Label(frow, text="Status:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(8, 2))
        self.job_filter_var = tk.StringVar(value="All")
        fcombo = ttk.Combobox(frow, textvariable=self.job_filter_var,
                              values=["All", *shop_db.STATUSES],
                              state="readonly", width=14)
        fcombo.pack(side="left")
        fcombo.bind("<<ComboboxSelected>>",
                    lambda _e: self._refresh_jobs())
        self.job_tree = ttk.Treeview(
            right,
            columns=("ticket", "customer", "device", "problem",
                     "status", "final", "received"),
            show="headings", selectmode="browse")
        for col, title, width in (("ticket", "Ticket", 76),
                                  ("customer", "Customer", 150),
                                  ("device", "Device", 170),
                                  ("problem", "Masla", 220),
                                  ("status", "Status", 95),
                                  ("final", "Final Rs", 80),
                                  ("received", "Received", 95)):
            self.job_tree.heading(col, text=title)
            self.job_tree.column(col, width=width, anchor="w")
        self.job_tree.pack(fill="both", expand=True)
        self.job_tree.bind("<<TreeviewSelect>>", self._job_on_select)
        return f

    def _refresh_job_customers(self):
        combo = getattr(self, "job_cust_combo", None)
        if combo is None:
            return
        try:
            rows = shop_db.list_customers()
        except Exception:  # noqa: BLE001
            rows = []
        current = self.job_cust_var.get()
        self.job_cust_ids = [c["id"] for c in rows]
        self.job_cust_labels = [
            (f"#{c['id']} — {c['name']} ({c['phone']})"
             if c["phone"] else f"#{c['id']} — {c['name']}")
            for c in rows]
        combo.configure(values=self.job_cust_labels)
        if current in self.job_cust_labels:
            self.job_cust_var.set(current)
        elif self.job_cust_labels:
            self.job_cust_var.set(self.job_cust_labels[0])
        else:
            self.job_cust_var.set("")

    def _job_customer_id(self):
        label = self.job_cust_var.get()
        try:
            idx = self.job_cust_labels.index(label)
            return self.job_cust_ids[idx]
        except (ValueError, IndexError):
            return None

    def _refresh_jobs(self):
        tree = getattr(self, "job_tree", None)
        if tree is None:
            return
        try:
            rows = shop_db.search_jobs(self.job_search_var.get(),
                                       self.job_filter_var.get())
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Jobs load nahi ho sake: {e}", "ERROR")
            return
        for item in tree.get_children():
            tree.delete(item)
        self.job_items = {}
        for j in rows:
            device = f"{j['brand']} {j['model']}".strip() or "—"
            final = (shop_db.fmt_money(j["final_charges"])
                     if float(j["final_charges"] or 0) else "—")
            item = tree.insert("", "end", values=(
                j["ticket_no"], j["customer_name"], device,
                (j["problem"] or "")[:60], j["status"], final,
                j["received_date"]))
            self.job_items[item] = j["id"]

    def _job_fill(self, job):
        self.job_selected_id = job["id"]
        cid = job["customer_id"]
        if cid in self.job_cust_ids:
            self.job_cust_var.set(
                self.job_cust_labels[self.job_cust_ids.index(cid)])
        self.job_brand_var.set(job["brand"])
        self.job_model_var.set(job["model"])
        self.job_imei_var.set(job["imei"])
        self.job_problem_txt.delete("1.0", "end")
        self.job_problem_txt.insert("1.0", job["problem"])
        self.job_status_var.set(job["status"])
        self.job_est_var.set(self._money_text(job["est_charges"]))
        self.job_final_var.set(self._money_text(job["final_charges"]))
        self.job_received_var.set(job["received_date"])
        self.job_delivered_var.set(job["delivered_date"])
        self.job_info_label.configure(
            text=f"Ticket {job['ticket_no']} — "
                 f"{job.get('customer_name', '')}")
        self.job_save_btn.configure(text="💾 SAVE (UPDATE)")

    def _job_on_select(self, _event=None):
        sel = self.job_tree.selection()
        jid = self.job_items.get(sel[0]) if sel else None
        if jid is None:
            return
        try:
            job = shop_db.get_job(jid)
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Job load nahi ho saka: {e}", "ERROR")
            return
        if job is not None:
            self._job_fill(job)

    def _job_clear(self):
        self.job_selected_id = None
        self.job_brand_var.set("")
        self.job_model_var.set("")
        self.job_imei_var.set("")
        self.job_problem_txt.delete("1.0", "end")
        self.job_status_var.set("Received")
        self.job_est_var.set("")
        self.job_final_var.set("")
        self.job_received_var.set(date.today().isoformat())
        self.job_delivered_var.set("")
        self.job_info_label.configure(text="")
        self.job_save_btn.configure(text="➕ NAYA JOB")
        if hasattr(self, "job_tree"):
            self.job_tree.selection_remove(self.job_tree.selection())

    def _job_save(self):
        cid = self._job_customer_id()
        if cid is None:
            self.log_line("Pehle customer select karo — naya "
                          "customer CUSTOMERS module me banta hai.",
                          "WARN")
            return
        problem = self.job_problem_txt.get("1.0", "end").strip()
        if not problem:
            self.log_line("Masla (problem) likhna lazmi hai.", "WARN")
            return
        fields = dict(
            customer_id=cid,
            brand=self.job_brand_var.get().strip(),
            model=self.job_model_var.get().strip(),
            imei=self.job_imei_var.get().strip(),
            problem=problem,
            status=self.job_status_var.get(),
            est_charges=self._parse_money(self.job_est_var.get()),
            final_charges=self._parse_money(self.job_final_var.get()),
            received_date=self.job_received_var.get().strip(),
            delivered_date=self.job_delivered_var.get().strip())
        try:
            if self.job_selected_id:
                shop_db.update_job(self.job_selected_id, **fields)
                job = shop_db.get_job(self.job_selected_id)
                self.log_line(f"Job update ho gaya: "
                              f"{job['ticket_no']}", "OK")
            else:
                _jid, ticket = shop_db.add_job(**fields)
                self.log_line(f"Naya job ban gaya — Ticket {ticket}",
                              "OK")
        except ValueError as e:
            self.log_line(str(e), "WARN")
            return
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Job save nahi ho saka: {e}", "ERROR")
            return
        self._job_clear()
        self._refresh_jobs()
        self._refresh_customers()
        self._refresh_home_shop()

    def _job_quick_status(self, status):
        if not self.job_selected_id:
            self.log_line("Pehle list se aik job select karo — phir "
                          "status badlo.", "WARN")
            return
        try:
            shop_db.set_job_status(self.job_selected_id, status)
            job = shop_db.get_job(self.job_selected_id)
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Status nahi badla: {e}", "ERROR")
            return
        self.log_line(f"{job['ticket_no']} → {status}", "OK")
        self._refresh_jobs()
        self._refresh_home_shop()
        if job is not None:
            self._job_fill(job)

    def _job_receipt(self):
        if not self.job_selected_id:
            self.log_line("Pehle list se aik job select karo — "
                          "receipt usi ki banegi.", "WARN")
            return
        try:
            job = shop_db.get_job(self.job_selected_id)
            cust = shop_db.get_customer(job["customer_id"])
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Receipt data nahi mila: {e}", "ERROR")
            return
        rdir = shop_db.receipts_dir()
        path = filedialog.asksaveasfilename(
            title="Receipt kahan save karoon?",
            initialdir=str(rdir),
            initialfile=f"receipt-{job['ticket_no']}.html",
            defaultextension=".html",
            filetypes=[("HTML (print ke liye)", "*.html"),
                       ("Text", "*.txt")])
        if not path:
            return
        try:
            if str(path).lower().endswith(".txt"):
                content = shop_db.receipt_text(job, cust)
            else:
                content = shop_db.receipt_html(job, cust)
            Path(path).write_text(content, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            self.log_line(f"Receipt save nahi ho saki: {e}", "ERROR")
            return
        self.log_line(f"Receipt tayyar: {path} — browser me khol "
                      "kar print kar lo.", "OK")
        try:
            webbrowser.open(Path(path).as_uri())
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------- CHANGELOG ---
    def _build_changelog(self, parent):
        f = tk.Frame(parent, bg=BG)
        txt = tk.Text(f, bg=PANEL, fg=FG, font=("Consolas", 10),
                      relief="flat", wrap="word")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", CHANGELOG_TEXT)
        txt.configure(state="disabled")
        return f

    # ------------------------------------------------------------ actions --
    def start_op(self):
        if self.selected_op is None:
            return
        # Gates + params: IMEI tasdeeq (Network tab), danger
        # tasdeeq aur PARAMS bar — _collect_op_args dono raston
        # (tree + model panel) me mushtaraka hai.
        imei, danger, params = self._collect_op_args(self.selected_op)
        if self.runner.start(self.selected_op, self.device,
                             imei_write_confirmed=imei,
                             danger_confirmed=danger, params=params):
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")

    def start_demo(self):
        self.show_module("unlock")
        self.show_ops_view()
        demo_item = None
        for item, module in self.op_modules.items():
            if module.OP.get("id") == "demo_session":
                demo_item = item
                break
        self.demo_active = True
        self.set_device(demo_mod.fake_device())
        if demo_item:
            self.tree.selection_set(demo_item)
            self.tree.see(demo_item)
            self._on_select()
        self.start_op()

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ device ---
    def set_device(self, dev):
        self.device = dev
        if dev.connected:
            self.dev_status.configure(text="● CONNECTED", fg=GREEN)
        else:
            self.dev_status.configure(text="● NO DEVICE", fg="#f87171")
        vals = {"brand": dev.brand, "model": dev.model, "chip": dev.chip,
                "serial": dev.serial, "mode": dev.mode, "port": dev.port,
                "android": dev.android, "detail": dev.detail}
        for key, lbl in self.dev_fields.items():
            lbl.configure(text=vals.get(key) or "—")
        if hasattr(self, "home_dev_label"):
            if dev.connected:
                self.home_dev_label.configure(
                    text=f"{dev.brand} {dev.model} · {dev.chip} · "
                         f"Mode: {dev.mode} · {dev.serial}")
            else:
                self.home_dev_label.configure(
                    text="Koi device nahi laga — phone lagao, khud "
                         "detect hoga.")

    def _watch_loop(self):
        adb = tool_path("adb")
        fb = tool_path("fastboot")
        last_sig = ""
        while True:
            try:
                # Demo chal raha ho to asal watcher nakli panel ko na cherre
                if not (self.demo_active and self.runner.busy):
                    dev = device_watch.poll_once(adb, fb)
                    sig = f"{dev.mode}|{dev.serial}|{dev.model}"
                    if sig != last_sig:
                        last_sig = sig
                        if dev.connected:
                            # Asal phone lag gaya — demo mode khatam
                            self.demo_active = False
                            self.ui_q.put(("device", dev))
                        elif self.device.connected and not self.demo_active:
                            self.ui_q.put(("device", dev))
            except Exception:
                pass
            time.sleep(2)

    # ------------------------------------------------------------ queue ----
    def log_line(self, msg, level="INFO"):
        ts = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n", level if level in LEVEL_COLORS else "INFO")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_queue(self):
        try:
            while True:
                item = self.ui_q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log_line(item[1], item[2])
                elif kind == "progress":
                    self.progress.configure(value=item[1])
                    self.prog_label.configure(text=f"{item[1]}%  {item[2]}")
                elif kind == "device":
                    self.set_device(item[1])
                elif kind == "plat_gpt":
                    self._plat_set_parts(item[1])
                elif kind == "fm_entries":
                    self._fm_set_entries(item[1], item[2])
                elif kind == "done":
                    self.stop_btn.configure(state="disabled")
                    if self.selected_op is not None:
                        self.start_btn.configure(state="normal")
        except queue.Empty:
            pass
        self.after(60, self._drain_queue)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
