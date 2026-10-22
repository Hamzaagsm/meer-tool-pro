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
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo as demo_mod                       # noqa: E402
from core import device_watch                 # noqa: E402
from core.runner import Runner, TOOLS_DIR     # noqa: E402
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


def tool_path(name):
    """tools/platform-tools me ho to wahan se, warna PATH wala naam."""
    for cand in (TOOLS_DIR / "platform-tools" / f"{name}.exe",
                 TOOLS_DIR / "platform-tools" / name):
        if cand.is_file():
            return str(cand)
    return name


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MEER TOOL PRO v1.0")
        self.geometry("1180x740")
        self.minsize(980, 620)
        self.configure(bg=BG)

        self.ui_q = queue.Queue()
        self.device = device_watch.DeviceInfo()
        self.demo_active = False
        self.op_modules = {}            # tree item id -> plugin module
        self.selected_op = None

        self.runner = Runner(
            log_fn=lambda m, lvl: self.ui_q.put(("log", m, lvl)),
            progress_fn=lambda p, lab: self.ui_q.put(("progress", p, lab)),
            done_fn=lambda res: self.ui_q.put(("done", res)),
            update_device_fn=lambda d: self.ui_q.put(("device", d)),
        )

        self._build_ui()
        self._load_ops_tree()
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

        # Middle: ops tree + log
        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=10, pady=4)
        left = tk.Frame(mid, bg=PANEL, width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="OPERATIONS", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=6)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=4, pady=2)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.op_hint = tk.Label(left, text="Operation select karo.",
                                bg=PANEL, fg=MUTED, wraplength=280,
                                justify="left", font=("Segoe UI", 8))
        self.op_hint.pack(anchor="w", padx=8, pady=6)

        right = tk.Frame(mid, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        tk.Label(right, text="LIVE LOG", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 4))
        self.log = tk.Text(right, bg=LOG_BG, fg=FG, font=("Consolas", 10),
                           relief="flat", wrap="word", state="disabled")
        scroll = ttk.Scrollbar(right, command=self.log.yview)
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

    # ------------------------------------------------------------ actions --
    def start_op(self):
        if self.selected_op is None:
            return
        if self.runner.start(self.selected_op, self.device):
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")

    def start_demo(self):
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
