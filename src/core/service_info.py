"""service_info.py — Unified "Service Info" screen (Round 2, Group 6).

SERVER-REQUIRED-ROUTES-RESEARCH-2 §8.20 / §9.10: Pandora ("Read device
service info"), Chimera (Get Info) aur UnlockTool jaisi depth — ME_ID,
SOC_ID, KG state, BIT, CSC, lock states — maujooda engines se parhi
ja sakti hai (MTK gettargetconfig, EDL info, ADB getprop, fastboot
getvar). Is liye unified screen chahiye, naya engine nahi.

Usool (sakht):
  - Har field ka SOURCE screen par likha hota hai (kis engine se
    parha gaya). Jo field is device / is mode se readable nahi,
    use "—" dikhao — GUESS KABHI NAHI.
  - IMEI is screen par NAHI parha jata (adb_info wala usool).
  - Screen sirf dikhati hai — koi write, koi bahari tool nahi.
  - Pure helpers (extract_service_fields / service_rows) GUI se
    azad hain — logic tests in par chalte hain.

Wiring: src/main.py ko DIRECTLY EDIT MAT KARO. Wiring snippet
(parent agent ki report me) — imei_panels.build_phone_info_panel
wale pattern par: UNLOCK ke dayein panel me phone_info_frame ke
neeche pack karo, aur App.set_device me phone_info_refresh ke
saath service_info_refresh bhi call karo.
"""

from __future__ import annotations

import re
import tkinter as tk

# Rang imei_panels.py ke barabar (main se import nahi — circular
# import se bachne ke liye yahan dohrane hain).
BG = "#14181f"
PANEL = "#1b212b"
PANEL2 = "#202834"
FG = "#e6e9ee"
MUTED = "#8b95a5"
ACCENT = "#ffa028"
WARN_FG = "#fbbf24"

MISSING = "—"

# (key, label, source) — source wahi engine hai jo field parh sakta
# hai; screen par har row ke saath dikhta hai.
SERVICE_FIELDS = (
    ("brand", "Brand", "ADB getprop / Fastboot getvar / BROM identify"),
    ("model", "Model", "ADB getprop / Fastboot getvar / BROM identify"),
    ("chip", "Chipset", "ADB getprop ro.board.platform / BROM identify"),
    ("mode", "Mode", "Device watch (live detection)"),
    ("serial", "Serial", "ADB / Fastboot / COM port"),
    ("android", "Android", "ADB getprop ro.build.version.release"),
    ("patch", "Security Patch", "ADB getprop ro.build.version.security_patch"),
    ("build", "Build", "ADB getprop ro.build.display.id"),
    ("me_id", "ME_ID", "MTK gettargetconfig (BROM identify)"),
    ("soc_id", "SOC_ID", "MTK gettargetconfig / EDL info"),
    ("kg_state", "KG State", "Samsung KG Status op / ADB getprop (knox)"),
    ("bit", "BIT (Binary)", "Samsung Download Mode / Fastboot getvar"),
    ("csc", "CSC", "ADB getprop ro.csc.sales_code"),
    ("frp_lock", "FRP Lock", "Fastboot getvar / EDL GPT (frp partition)"),
    ("mdm_lock", "MDM / Finance Lock", "MDM check / ADB packages"),
    ("oem_unlock", "OEM Unlock", "Fastboot getvar / ro.oem_unlock_supported"),
    ("bl_lock", "Bootloader Lock", "Fastboot getvar 'unlocked'"),
)

_NOTE = (
    "Jo field '—' hai wo is device / is mode se readable nahi — "
    "guess nahi kiya gaya. Read Info ops (ADB / Fastboot / META / "
    "EDL) chalane se fields bharte hain; KG State ke liye 'KG Status "
    "(Knox Guard)' op chalao."
)

_TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*([^\s,;]+)")


def _token_value(text, key):
    """'key: value' / 'key=value' token detail string se nikalo."""
    if not text:
        return ""
    for found_key, val in _TOKEN_RE.findall(str(text)):
        if found_key.lower() == key.lower():
            return val.strip()
    return ""


def _kg_from_props(props):
    """raw_props me knox/kg keys dhoondo — pehli readable value."""
    for key, val in (props or {}).items():
        low = str(key).lower()
        if ("knox" in low or "kgstate" in low or "kg_state" in low
                or low.startswith("kg_")) and str(val).strip():
            return f"{key}={val}"
    return ""


def extract_service_fields(device):
    """Device (DeviceInfo / FakeDevice / None) → {key: (value, source)}.

    Har field: value mile to wahi, warna MISSING ("—"). Koi andaza
    nahi, koi default bhara hua nahi."""
    props = {}
    detail = ""
    attrs = {}
    if device is not None:
        props = getattr(device, "raw_props", None) or {}
        if not isinstance(props, dict):
            props = {}
        detail = getattr(device, "detail", "") or ""
        attrs = {
            "brand": getattr(device, "brand", "") or "",
            "model": getattr(device, "model", "") or "",
            "chip": getattr(device, "chip", "") or "",
            "mode": getattr(device, "mode", "") or "",
            "serial": getattr(device, "serial", "") or "",
            "android": getattr(device, "android", "") or "",
        }

    vals = {}
    vals["brand"] = attrs.get("brand", "")
    vals["model"] = attrs.get("model", "")
    vals["chip"] = attrs.get("chip", "")
    vals["mode"] = attrs.get("mode", "")
    vals["serial"] = attrs.get("serial", "")
    vals["android"] = attrs.get("android", "")
    vals["patch"] = props.get("ro.build.version.security_patch", "")
    vals["build"] = props.get("ro.build.display.id", "")
    vals["me_id"] = _token_value(detail, "ME_ID") \
        or _token_value(detail, "me-id")
    vals["soc_id"] = _token_value(detail, "SOC_ID") \
        or _token_value(detail, "soc-id")
    vals["kg_state"] = _kg_from_props(props) \
        or _token_value(detail, "KG")
    vals["bit"] = _token_value(detail, "BIT")
    vals["csc"] = (props.get("ro.csc.sales_code", "")
                   or props.get("ro.csc.country_code", ""))
    vals["frp_lock"] = _token_value(detail, "FRP")
    vals["mdm_lock"] = _token_value(detail, "MDM")
    oem = props.get("ro.oem_unlock_supported", "")
    if oem == "1":
        vals["oem_unlock"] = "Supported"
    elif oem == "0":
        vals["oem_unlock"] = "Not supported"
    else:
        vals["oem_unlock"] = _token_value(detail, "OEM_UNLOCK")
    unlocked = _token_value(detail, "unlocked")
    if unlocked.lower() == "yes":
        vals["bl_lock"] = "Unlocked"
    elif unlocked.lower() == "no":
        vals["bl_lock"] = "Locked"
    else:
        vals["bl_lock"] = ""

    out = {}
    for key, _label, source in SERVICE_FIELDS:
        val = str(vals.get(key, "") or "").strip()
        out[key] = (val if val else MISSING, source)
    return out


def service_rows(device):
    """Display order me (label, value, source) rows."""
    fields = extract_service_fields(device)
    rows = []
    for key, label, source in SERVICE_FIELDS:
        value, _src = fields[key]
        rows.append((label, value, source))
    return rows


# ---------------------------------------------------------------------------
# GUI — imei_panels.build_phone_info_panel wala pattern
# ---------------------------------------------------------------------------

def _run_op(app, op_id):
    """Op module dhoondh kar chalao; na mile to log me saaf wajah."""
    module = None
    try:
        module = app._module_by_id(op_id)
    except Exception:  # noqa: BLE001
        module = None
    if module is None:
        app.log_line(f"Operation '{op_id}' is build me nahi mila — "
                     "pehle poora pack (EXE + tools) update karo.",
                     "ERROR")
        return
    app._run_action(module)


def build_service_info(parent, app):
    """LabelFrame + refresh(dev) — App.set_device se call hota hai.

    Har row: label | value | source. Jo field readable nahi, us ki
    value '—' hoti hai — guess nahi. Neeche do chhote buttons:
    Read Info (ADB) aur KG Status — taake fields bharne ka rasta
    screen par hi ho (dono MEER ke apne ops hain)."""
    frame = tk.LabelFrame(parent, text=" SERVICE INFO ",
                          bg=PANEL, fg=MUTED, bd=1,
                          font=("Segoe UI", 9, "bold"))
    labels = {}
    row_i = 0
    for _key, label, source in SERVICE_FIELDS:
        tk.Label(frame, text=f"{label}:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=row_i, column=0,
                                            sticky="e",
                                            padx=(10, 2), pady=1)
        val = tk.Label(frame, text=MISSING, bg=PANEL, fg=FG,
                       font=("Segoe UI", 9, "bold"))
        val.grid(row=row_i, column=1, sticky="w", pady=1)
        tk.Label(frame, text=f"({source})", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=row_i, column=2,
                                            sticky="w", pady=1)
        labels[_key] = val
        row_i += 1

    tk.Label(frame, text=_NOTE, bg=PANEL, fg=MUTED,
             wraplength=700, justify="left",
             font=("Segoe UI", 8)).grid(row=row_i, column=0,
                                        columnspan=3, sticky="w",
                                        padx=10, pady=(4, 2))
    row_i += 1
    btnrow = tk.Frame(frame, bg=PANEL)
    btnrow.grid(row=row_i, column=0, columnspan=3, sticky="w",
                padx=10, pady=(0, 4))
    tk.Button(btnrow, text="Read Info (ADB)",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 8, "bold"), padx=8, pady=3,
              command=lambda: _run_op(app, "adb_info")).pack(
                  side="left", padx=(0, 6))
    tk.Button(btnrow, text="KG Status (Samsung)",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 8, "bold"), padx=8, pady=3,
              command=lambda: _run_op(app, "samsung_kg_status")).pack(
                  side="left", padx=(0, 6))
    tk.Button(btnrow, text="Read Info (Fastboot)",
              bg=PANEL2, fg=FG, relief="flat",
              font=("Segoe UI", 8, "bold"), padx=8, pady=3,
              command=lambda: _run_op(app, "fastboot_info")).pack(
                  side="left")

    def refresh(dev):
        fields = extract_service_fields(dev)
        for key, lbl in labels.items():
            try:
                lbl.configure(text=fields[key][0])
            except tk.TclError:
                pass

    frame.refresh = refresh
    return frame, refresh
