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
from pathlib import Path
from tkinter import filedialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo as demo_mod                       # noqa: E402
from core import device_watch                 # noqa: E402
from core import mdm_list                     # noqa: E402
from core import platforms_mtk                # noqa: E402
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

        self.runner = Runner(
            log_fn=lambda m, lvl: self.ui_q.put(("log", m, lvl)),
            progress_fn=lambda p, lab: self.ui_q.put(("progress", p, lab)),
            done_fn=lambda res: self.ui_q.put(("done", res)),
            update_device_fn=lambda d: self.ui_q.put(("device", d)),
        )

        self._build_ui()
        self._load_ops_tree()
        self._load_mdm_models()
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

        # Pack tartib ki islah: LIVE LOG aur bottom bar ko bottom se
        # anchor karo, module area darmiyan ki baqi jagah lega — warna
        # baray module (Platforms) par log/buttons window se bahir
        # dhakel jate hain.
        bot.pack_forget()
        logf.pack_forget()
        bot.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        logf.pack(side="bottom", fill="x", padx=10, pady=(0, 2))

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

    def _run_action(self, op_obj):
        """Model panel ke buttons — bilkul START wala rasta (runner)."""
        if op_obj is None:
            return
        # IMEI gate: op par imei_write ka nishan ho to Network tab
        # ke tasdeeq checkbox ki halat ctx tak bhejo — op khud
        # warning chhapega aur baghair tasdeeq wahin ruk jayega.
        confirmed = False
        if getattr(op_obj, "OP", {}).get("imei_write"):
            var = getattr(self, "net_imei_confirm_var", None)
            confirmed = bool(var.get()) if var is not None else False
        if self.runner.start(op_obj, self.device,
                             imei_write_confirmed=confirmed):
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
        files = mdm_list.da_files()
        self._da_paths = files
        labels = []
        for p in files:
            try:
                labels.append(str(p.relative_to(TOOLS_DIR / "loaders")))
            except Exception:
                labels.append(p.name)
        if not labels:
            labels = ["(koi DA nahi — tools/loaders me .bin rakho)"]
        self.da_combo.configure(values=labels)
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
                 lambda: self.show_module("utility"))):
            tk.Button(row, text=text, bg=PANEL2, fg=FG, relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=10, pady=6,
                      command=cmd).pack(side="left", padx=3)
        tk.Label(card, text="Har operation asal engine par chalta hai "
                            "aur output neeche LIVE LOG me stream hota "
                            "hai. Pehle poora flow dekhna ho to upar "
                            "▶ DEMO MODE dabao.",
                 bg=PANEL, fg=MUTED, wraplength=760, justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=8)
        return f

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
        # IMEI gate: ops-tree se chalne wale gated ops ko bhi
        # Network tab ke tasdeeq checkbox ki halat bhejo (MDM
        # panel wala _run_action rasta pehle se ye karta hai).
        confirmed = False
        if getattr(self.selected_op, "OP", {}).get("imei_write"):
            var = getattr(self, "net_imei_confirm_var", None)
            confirmed = bool(var.get()) if var is not None else False
        if self.runner.start(self.selected_op, self.device,
                             imei_write_confirmed=confirmed):
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
