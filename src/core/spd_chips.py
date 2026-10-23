"""
spd_chips.py — Unisoc/SPD chip table (tools/spd-chips.json) ka loader.

SPD-EXPANSION.md §3.1 ki implementation: MTK side par jo loader
library + per-model data hai, SPD side par us ka data-layer ye
module hai. Chip table `tools/spd-chips.json` me rehti hai
(mdm-models.json wali hi pattern — data file, code se alag,
user-editable) aur ye module usay parh kar deta hai:

  load_chips()          tamam chip rows
  chip_by_name(name)    chip naam ('Tiger T606') ya codename
                        ('UMS9230') se row — na mile ya ambiguous
                        ho to None (UMS9230 chhe chips share karte
                        hain, is liye codename akela chip nahi deta)
  chip_for_chipset(s)   mdm-models ke chipset string ('Unisoc
                        T7250', 'Unisoc T606_64') se row
  chip_for_model(m)     model row / model code / 'Brand Model'
                        string / DeviceInfo — har shakl se chip row
  context_for_device(d) {model, chip, model_code} aik saath
  boot_guidance(x)      download-mode rehnumai ki line (boot key
                        + SPRD port VID:PID) — chip/model jo mile

Imaandari: file na ho, JSON kharab ho, ya koi match saaf na ho
to har function khaali/None deta hai — GUI me kabhi raise nahi
karta, aur chip data ke baghair SPD ops apni aam rehnumai par
chalte rehte hain (chip layer sirf izafa hai, rukawat nahi).
"""

import json
import re

from core.runner import TOOLS_DIR

CHIPS_FILE = TOOLS_DIR / "spd-chips.json"
MODELS_FILE = TOOLS_DIR / "mdm-models.json"

# Chip pehchan ke tokens: SC-series (SC9863A), Tiger (T7250),
# platform codenames (UMS9230). Chipset string 'Unisoc T606_64'
# me se 't606' nikalna hi asal kaam hai.
_TOKEN_RE = re.compile(r"sc\d{4}[a-z]?|t\d{3,4}|ums\d{4}",
                       re.IGNORECASE)

# Marketing aliases — chip table ke apne notes me grounded:
# T7255 wahi silicon hai jo T616 hai (Notebookcheck), T8100 =
# T760 aur T9100 = T820 ke rebrand naam hain (2025 rebrand wave).
_ALIASES = {
    "t7255": "t616",
    "t8100": "t760",
    "t9100": "t820",
}


# ---------------------------------------------------------------------------
# Data loading (defensive — kabhi raise nahi)
# ---------------------------------------------------------------------------
def load_chips():
    """tools/spd-chips.json ki chip rows (list of dict).

    File na ho / JSON kharab ho to khaali list.
    """
    try:
        data = json.loads(CHIPS_FILE.read_text(encoding="utf-8"))
        rows = data.get("chips", []) if isinstance(data, dict) \
            else data
        if not isinstance(rows, list):
            return []
        return [r for r in rows
                if isinstance(r, dict) and r.get("chip")]
    except Exception:  # noqa: BLE001 — data layer GUI ko nahi gira sakta
        return []


def load_models():
    """tools/mdm-models.json ki model rows (list of dict).

    Shape mdm_list.load_models wali hi: bare array ya
    {"models": [...]}. File na ho / kharab ho to khaali list.
    """
    try:
        data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
        raw = data if isinstance(data, list) else data.get("models", [])
        if not isinstance(raw, list):
            return []
        return [m for m in raw if isinstance(m, dict)]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Chip resolution
# ---------------------------------------------------------------------------
def _tokens(text):
    """Text se chip tokens (lowercase) — tartib mehfooz, dedup."""
    if not text:
        return []
    out = []
    for m in _TOKEN_RE.finditer(str(text)):
        tok = m.group(0).lower()
        if tok not in out:
            out.append(tok)
    return out


def chip_by_name(name):
    """Chip naam ya codename se chip row — na mile to None.

    Tartib: (1) exact chip naam, (2) exact codename (bracket se
    pehle wala hissa), (3) chip-naam ke tokens, (4) codename ke
    tokens. Token wale marhalon par AIK se zyada row match ho to
    None — ambiguous pehchan chip nahi hoti (masalan 'UMS9230'
    akela chhe chips ka platform hai).
    """
    rows = load_chips()
    if not rows or not name:
        return None
    q = str(name).strip().lower()
    if not q:
        return None
    hits = [r for r in rows
            if str(r.get("chip", "")).strip().lower() == q]
    if len(hits) == 1:
        return hits[0]
    hits = [r for r in rows
            if str(r.get("codename", "")).split("(")[0].strip().lower()
            == q]
    if len(hits) == 1:
        return hits[0]
    qtoks = []
    for tok in _tokens(q):
        tok = _ALIASES.get(tok, tok)
        if tok not in qtoks:
            qtoks.append(tok)
    if not qtoks:
        return None
    hits = [r for r in rows
            if any(t in _tokens(r.get("chip", "")) for t in qtoks)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return None
    hits = [r for r in rows
            if any(t in _tokens(r.get("codename", ""))
                   for t in qtoks)]
    if len(hits) == 1:
        return hits[0]
    return None


def chip_for_chipset(chipset):
    """mdm-models ke chipset string se chip row.

    'Unisoc T7250' → Tiger T7250 wali row; 'Unisoc T606_64' ka
    '_64' suffix token talaash me khud nazar-andaz ho jata hai.
    """
    if not chipset:
        return None
    return chip_by_name(chipset)


# ---------------------------------------------------------------------------
# Model resolution (mdm-models.json)
# ---------------------------------------------------------------------------
def model_for_code(code):
    """Model code ('X6725', 'KL4h') se model row — na mile to None."""
    if not code:
        return None
    q = str(code).strip().lower()
    if not q:
        return None
    for m in load_models():
        if str(m.get("code", "")).strip().lower() == q:
            return m
    return None


def model_for_name(brand, model):
    """Brand + model naam se model row — na mile to None.

    Pehle brand+model dono ka exact match; phir sirf model naam
    ka match (aik hi ho to).
    """
    b = str(brand or "").strip().lower()
    mname = str(model or "").strip().lower()
    if not mname:
        return None
    rows = load_models()
    for m in rows:
        rb = str(m.get("brand", "")).strip().lower()
        rm = str(m.get("model", "")).strip().lower()
        if rm == mname and (not b or rb == b):
            return m
    hits = [m for m in rows
            if str(m.get("model", "")).strip().lower() == mname]
    return hits[0] if len(hits) == 1 else None


def model_in_text(text):
    """Kisi text (masalan PAC file ke naam) me model code dhoondo.

    Code poora lafz ban kar mile (aage/peeche harf-rakm na ho)
    tab hi match — pehla match return hota hai, warna None.
    Harvest key nikalne ke liye hai (device context na ho to
    PAC ke naam se model pehchanna).
    """
    if not text:
        return None
    hay = str(text)
    for m in load_models():
        code = str(m.get("code", "")).strip()
        if len(code) < 3:
            continue
        pat = r"(?<![A-Za-z0-9])" + re.escape(code) + r"(?![A-Za-z0-9])"
        if re.search(pat, hay, re.IGNORECASE):
            return m
    return None


def resolve_model(query):
    """Har shakl se model row: model dict khud, model code,
    'Brand Model' / 'Model' string, ya DeviceInfo jaisi object
    (brand/model attributes). Na mile to None."""
    if query is None:
        return None
    if isinstance(query, dict):
        if query.get("chipset") or query.get("code") \
                or query.get("model"):
            if query.get("code") or query.get("model"):
                # pehle DB ki asal row ko tarjeeh (fields mukammal)
                found = None
                if query.get("code"):
                    found = model_for_code(query["code"])
                if found is None and query.get("model"):
                    found = model_for_name(query.get("brand", ""),
                                           query["model"])
                return found if found is not None else query
            return query
        return None
    if isinstance(query, str):
        q = query.strip()
        if not q:
            return None
        found = model_for_code(q)
        if found is not None:
            return found
        found = model_for_name("", q)
        if found is not None:
            return found
        parts = q.split(None, 1)
        if len(parts) == 2:
            return model_for_name(parts[0], parts[1])
        return None
    # DeviceInfo jaisi object
    brand = getattr(query, "brand", "") or ""
    mname = getattr(query, "model", "") or ""
    if brand or mname:
        return model_for_name(brand, mname)
    return None


def chip_for_model(model):
    """Model (row/code/string/DeviceInfo) se chip row.

    Pehle model ki chipset string se; DeviceInfo par model na
    mile to us ke apne chip field se bhi koshish hoti hai.
    """
    row = resolve_model(model)
    if row is not None:
        chip = chip_for_chipset(row.get("chipset"))
        if chip is not None:
            return chip
    if model is not None and not isinstance(model, (dict, str)):
        dchip = getattr(model, "chip", "") or ""
        if dchip:
            return chip_for_chipset(dchip)
    return None


def chip_for_device(device):
    """DeviceInfo se chip row — na mile to None."""
    return chip_for_model(device)


def context_for_device(device):
    """DeviceInfo se {model, chip, model_code} — aik saath.

    Jo hissa na mile wo None / "" rehta hai. Kabhi raise nahi.
    """
    try:
        model = resolve_model(device)
        chip = chip_for_model(device)
        code = ""
        if model is not None:
            code = str(model.get("code", "") or "")
        return {"model": model, "chip": chip, "model_code": code}
    except Exception:  # noqa: BLE001
        return {"model": None, "chip": None, "model_code": ""}


# ---------------------------------------------------------------------------
# Rehnumai (log lines ke liye)
# ---------------------------------------------------------------------------
def chip_summary(chip_row):
    """'Tiger T615 (UMS9230)' jaisi mukhtasar pehchan line."""
    if not chip_row:
        return ""
    name = str(chip_row.get("chip", "") or "")
    codename = str(chip_row.get("codename", "") or "")
    if codename:
        return f"{name} ({codename})"
    return name


def boot_guidance(target):
    """Download-mode rehnumai ki line — chip row / model / string
    jo bhi mile us se. Na mile to None.

    Line me boot key aur SPRD download port (VID:PID) dono hote
    hain, taake technician ko session se pehle saaf hidayat mile.
    """
    row = None
    if isinstance(target, dict) and target.get("boot_key"):
        row = target                       # chip row khud hai
    elif target is not None:
        row = chip_for_model(target)
        if row is None and isinstance(target, str):
            row = chip_by_name(target)
    if not row:
        return None
    boot = str(row.get("boot_key", "") or "")
    port = str(row.get("boot_vid_pid", "") or "1782:4D00")
    if not boot:
        return None
    return (f"Boot key: {boot} | Download port: {port} "
            "(SPRD gadget — Device Manager me yehi port ana "
            "chahiye)")
