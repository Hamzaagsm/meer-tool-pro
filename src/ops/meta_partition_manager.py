"""
meta_partition_manager.py — META Partition Manager (Round 2, §8.1/§8.13).

Pandora Ultra 10.3.0 (Oct 2026) ka "META Partition Manager" aur
UMT/Pandora ka GPT-driven partition kaam — MEER ke APNE META
engine par: META session → GPT parho (naam + LBA range + size)
→ usi table se per-partition read / write / erase.

Naye models pehle (Helio G200/G100 class — Hot 60 Pro/Pro+,
Spark 40 Pro+, Camon 50/50 Pro): in par META entry bina
SLA/server ke khulti hai (SERVER-REQUIRED-ROUTES-RESEARCH-2
§1.8 — Fenix X6886 demo, UMT v3.8 META UBL, MDMFixTool
v1.0.0.5). New-Auth class (Dimensity 6300/6400/7100/7300/7400
/9000/9400/9500) par LADDER guard rukta hai — wahan META entry
hi gated hai, is op ka koi rasta nahi.

HIFAZAT (sakht — kabhi nahi tooti):
  1. Har amal se pehle GPT check — jo partition GPT me NAHI,
     use chhua hi nahi jata (andaze wala naam kabhi nahi).
  2. BACKUP-FIRST: kisi bhi write/erase se pehle poori partition
     ki EXACT size (GPT LBA range se) parh kar
     backups/meta-partitions/ me mehfooz hoti hai. Backup na
     bane (ya size GPT se match na kare) to write/erase hota
     hi nahi — adhoora backup = brick ka rasta, is liye exact
     read (ft_part_read, tolerant reader nahi) istemal hota hai.
  3. ERASE MANA: preloader / nvram / nvdata / seccfg / proinfo /
     lk / boot / vbmeta / tee-class partitions ko ERASE karna
     seedha brick hai — in par erase ki koshish hi nahi hoti,
     guided refusal milta hai. userdata erase bhi yahan mana
     hai — us ke liye Factory Reset op hai.
  4. DANGER GATE: write/erase par PARAMS bar ki tasdeeq lazmi
     (read/list par gate nahi — wo safe hain).
  5. WRITE: input file tools/partitions/ me SIRF AIK .bin
     (RPMB write wala hi usool — galat file khud nahi chunte);
     file ka size partition ki GPT size se bara ho to STOP;
     write ke baad poori read-back byte-compare — match na ho
     to FAIL, nakli SUCCESS kabhi nahi.
  6. ERASE: FT_ERASE_PARTITION (wahi msg-id jo meta_frp_erase
     istemal karta hai); verify = erase ke baad pehle 4 KB
     parh kar all-0x00 ya all-0xFF (donon standard erased
     halatein) — warna FAIL.

Amal (params se ya op_for() factory se):
  - list  (default): GPT table + har partition ki safety class.
  - read:  poori partition parh kar backups/meta-partitions/
           <name>-<ts>.bin me save.
  - write: tools/partitions/ wali .bin likho (backup-first).
  - erase: partition mitayo (backup-first, mana wali list se bahir).

IMAANDARI: FT part read/write ids public FT table ki agli class
se hain; codec software-tested hai, asal phone par bench-
verification baqi hai (meta_session docstring wala usool).
Firmware FT partition read support na kare to op saaf FAIL
dega — andaze par kaam nahi hota.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core import meta_gpt, meta_guard, meta_patch, meta_session
from core.danger_gate import danger_gate
from core.runner import BACKUPS_DIR, TOOLS_DIR

OP = {
    "id": "meta_partition_manager",
    "category": "MDM / Transsion",
    "name": "Partition Manager (META Mode) — Round 2",
    "engine": "meta",
    "modes": (),
    "server_required": False,
    "danger_write": True,
    "params": ("partition", "action"),
}

PARTITIONS_INBOX = TOOLS_DIR / "partitions"
PARTITION_BACKUP_DIR = BACKUPS_DIR / "meta-partitions"

ACTIONS = ("list", "read", "write", "erase")

# ERASE kabhi nahi — in me se aik bhi mit jaye to phone seedha
# brick / secure-boot kharab (preloader = boot hi nahi; nvram/
# nvdata = IMEI + calibration; seccfg/proinfo = security state;
# lk/boot/vbmeta/tee = boot chain).
NEVER_ERASE = frozenset({
    "preloader", "nvram", "nvdata", "seccfg", "proinfo",
    "lk", "lk2", "boot", "boot_a", "boot_b",
    "vbmeta", "vbmeta_a", "vbmeta_b", "vbmeta_system",
    "vbmeta_vendor", "tee1", "tee2", "trustzone",
    "md1img", "md1dsp", "spmfw", "scp1", "scp2",
    "sspm_1", "sspm_2", "dtbo", "dtbo_a", "dtbo_b",
})

# ERASE yahan mana — alag (safer) op hai us ka:
# userdata -> Factory Reset op (meta_factory_reset).
ERASE_REDIRECT = {
    "userdata": "meta_factory_reset",
    "frp": None,  # frp erase yahin allowed hai (neeche dekho)
}

# WRITE par izafi warning (backup ke bawajood) — ye partitions
# phone ki pehchan/boot hain; likhne se pehle user dobara soche.
WRITE_SENSITIVE = frozenset({
    "preloader", "nvram", "nvdata", "seccfg", "proinfo",
    "lk", "lk2", "boot", "boot_a", "boot_b",
    "vbmeta", "vbmeta_a", "vbmeta_b",
})

_NAME_RE = re.compile(r"[A-Za-z0-9_]+")


# ---------------------------------------------------------------------------
# Pure helpers (bench ke baghair test ho sakte hain)
# ---------------------------------------------------------------------------
def parse_request(params, partition=None, action=None):
    """(partition|None, action, err|None).

    action: list/read/write/erase (default list). partition sirf
    list ke baghair lazmi hai. Naam sirf [A-Za-z0-9_] — FT
    payload ASCII+NUL banta hai, ajeeb naam se device ko
    kabhi kuch nahi bheja jayega.
    """
    params = params or {}
    act = str(action if action is not None else
              params.get("action", "") or "list").strip().lower()
    if act not in ACTIONS:
        return None, "list", (f"Action '{act}' ghalat hai — "
                              "list / read / write / erase me se "
                              "aik chuno.")
    name = str(partition if partition is not None else
               params.get("partition", "") or "").strip()
    if act == "list":
        return None, "list", None
    if not name:
        return None, act, ("Partition ka naam nahi diya — pehle "
                           "GPT list se naam chuno (list action), "
                           "phir wahi naam de kar read/write/erase "
                           "chalao.")
    if not _NAME_RE.fullmatch(name):
        return None, act, (f"Partition naam '{name}' durust nahi — "
                           "sirf harf, number aur _ chalte hain.")
    return name, act, None


def classify_partition(name):
    """'critical' | 'protected' | 'normal' — UI legend + log ke liye.

    critical: erase mana + write par izafi warning (boot/pehchan).
    protected: erase mana (security state) lekin write backup ke
      saath allowed. normal: backup-first ke saath read/write/
      erase allowed.
    """
    n = str(name or "").strip().lower()
    if n in NEVER_ERASE:
        if n in WRITE_SENSITIVE:
            return "critical"
        return "protected"
    return "normal"


def can_erase(name):
    """(True, '') ya (False, wajah) — pure."""
    n = str(name or "").strip().lower()
    if n in NEVER_ERASE:
        return False, (f"Partition '{name}' ko ERASE karna MANA hai "
                       "— ye phone ki boot/security/pehchan ka "
                       "hissa hai; mitane par phone seedha brick "
                       "ho jayega. Is ke liye koi tasdeeq kaafi "
                       "nahi — ye hifazat hai, rukawat nahi.")
    if n in ERASE_REDIRECT and ERASE_REDIRECT[n]:
        return False, (f"Partition '{name}' ko yahan se erase nahi "
                       f"karte — us ke liye '{ERASE_REDIRECT[n]}' "
                       "op istemal karo (wohi sahi rasta hai).")
    return True, ""


def can_write(name):
    """(True, note) — write har GPT partition par allowed hai
    (backup-first + danger gate + read-back ke saath); critical
    partitions par note me izafi warning hoti hai."""
    n = str(name or "").strip().lower()
    if n in WRITE_SENSITIVE:
        return True, (f"Partition '{name}' phone ki boot/pehchan "
                      "ka hissa hai — backup ban chuka hoga, phir "
                      "bhi likhne se pehle yaqeen kar lo ke file "
                      "BILKUL isi device/model ki hai.")
    return True, ""


def find_entry(entries, name):
    """GPT entries me naam dhoondo (case-insensitive) — asal
    case wali entry ya None."""
    want = str(name or "").strip().lower()
    for e in entries or []:
        if str(e.get("name", "")).lower() == want:
            return e
    return None


def fmt_size(n):
    """Bytes -> '12.5 MB' jaisi readable shakal (pure)."""
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _sha256(data):
    return hashlib.sha256(bytes(data or b"")).hexdigest()


def backup_partition(ctx, session, entry):
    """Poori partition EXACT size se parh kar backup file banao.

    Returns Path ya None (nakami par wajah log ho chuki hoti
    hai). Tolerant reader NAHI — ft_part_read exact size mangta
    hai aur adhoora data par MetaError deta hai; adhoora backup
    kabhi qabool nahi.
    """
    name = entry["name"]
    size = int(entry["size_bytes"])
    ctx.progress(20, f"'{name}' ka backup parha ja raha hai "
                     f"({fmt_size(size)})...")
    try:
        data = meta_patch.ft_part_read(session, name, 0, size)
    except meta_session.MetaError as e:
        ctx.log(f"Backup NAHI ban saka — '{name}' ({fmt_size(size)}) "
                f"mukammal parhi nahi gayi: {e}", "ERROR")
        ctx.log("Backup-first usool: baghair mukammal backup ke "
                "write/erase NAHI hoga.", "ERROR")
        return None
    if len(data) != size:
        ctx.log(f"Backup NAHI ban saka — '{name}' se {size} bytes "
                f"mange, mile {len(data)} (adhoora backup qabool "
                "nahi).", "ERROR")
        return None
    try:
        PARTITION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")
        path = PARTITION_BACKUP_DIR / f"{safe}-before-{ts}.bin"
        path.write_bytes(data)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Backup file nahi ban saki: {e}", "ERROR")
        return None
    ctx.log(f"Backup tayyar: {path} ({fmt_size(size)}, "
            f"sha256 {_sha256(data)[:16]}…)", "DATA")
    return path


def single_bin(ctx, folder):
    """Folder me bilkul AIK .bin ho to wahi, warna guided FAIL
    ke saath None (RPMB write wala hi usool — galat file khud
    kabhi nahi chunte)."""
    if not folder.is_dir():
        ctx.log(f"Input folder nahi mila: {folder} — pehle ye "
                "folder banao aur is me SIRF AIK .bin file rakho "
                "(jo partition me likhni hai).", "ERROR")
        return None
    bins = sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() == ".bin")
    if not bins:
        ctx.log(f"{folder} me koi .bin file nahi — likhne ke "
                "liye kuch nahi.", "ERROR")
        return None
    if len(bins) > 1:
        names = ", ".join(p.name for p in bins)
        ctx.log(f"{folder} me {len(bins)} .bin files hain: "
                f"{names} — galat file khud nahi chuni jayegi. "
                "Sirf wohi AIK file rakho jo is device/partition "
                "ke liye hai, baqi hata do.", "ERROR")
        return None
    return bins[0]


def _log_table(ctx, entries):
    """GPT table log me — naam + size + safety class (saboot)."""
    for i, e in enumerate(entries, 1):
        cls = classify_partition(e["name"])
        tag = {"critical": "⛔ CRITICAL",
               "protected": "⚠ PROTECTED",
               "normal": "normal"}[cls]
        ctx.log(f"  {i:>2}. {e['name']} — {fmt_size(e['size_bytes'])}"
                f" [{tag}]", "DATA")


def op_for(partition, action):
    """UI factory (mdm_list.download_frp_op wala pattern):
    muntakhib partition + action ke saath chalane wala op
    namespace — panel is se per-partition button banata hai.
    run(ctx) seedha run() ko bandha hua partition/action deta
    hai; PARAMS bar se kuch nahi mangta."""
    name, act, _err = parse_request({}, partition, action)
    label = {"list": "GPT List (META)",
             "read": f"Read '{partition}' (META)",
             "write": f"⚠ Write '{partition}' (META)",
             "erase": f"⚠ Erase '{partition}' (META)"}.get(
                 act, f"Partition '{partition}' (META)")
    op = dict(OP)
    op["name"] = f"{label} — Round 2"

    def _run(ctx, _p=name, _a=act):
        return run(ctx, partition=_p, action=_a)

    return SimpleNamespace(OP=op, run=_run)


# ---------------------------------------------------------------------------
# Op
# ---------------------------------------------------------------------------
def run(ctx, partition=None, action=None, model=None) -> bool:
    name, act, err = parse_request(getattr(ctx, "params", {}),
                                   partition, action)
    if err:
        ctx.log(err, "ERROR")
        return False

    # LADDER guard — new-Auth class par META entry hi gated hai.
    if not meta_guard.guard_or_ladder(ctx, model):
        return False
    if model:
        ctx.log(f"Model: {model.get('name', '')} "
                f"({model.get('code', '')})", "INFO")
    ctx.log("META Partition Manager — naye models pehle (Helio "
            "G200/G100: Hot 60 Pro/Pro+, Spark 40 Pro+, Camon "
            "50/50 Pro — in par META entry khuli hai). GPT se "
            "bahir koi partition chhui nahi jayegi.", "INFO")

    # DANGER GATE — sirf write/erase par (read/list safe hain).
    if act in ("write", "erase"):
        if not danger_gate(ctx, f"META PARTITION {act.upper()}"):
            return False
        if act == "erase":
            ok, why = can_erase(name)
            if not ok:
                ctx.log(why, "ERROR")
                return False
        else:
            _ok, note = can_write(name)
            if note:
                ctx.log(note, "WARN")

    session = meta_session.open_session(ctx)
    if session is None:
        return False
    try:
        with session:
            entries, _err = meta_gpt.read_gpt_entries(ctx, session)
            if entries is None:
                return False
            if act == "list":
                _log_table(ctx, entries)
                ctx.log("GPT list mukammal — har partition ki "
                        "safety class saath likhi hai (⛔ CRITICAL "
                        "= erase mana; ⚠ PROTECTED = security "
                        "state).", "OK")
                ctx.progress(95, "GPT list mukammal")
                return True

            entry = find_entry(entries, name)
            if entry is None:
                ctx.log(f"Partition '{name}' GPT me NAHI mili — "
                        "andaze par kaam nahi hota, op yahin ruk "
                        "raha hai. Pehle 'list' se asal naam "
                        "dekho.", "ERROR")
                return False
            real_name = entry["name"]
            size = int(entry["size_bytes"])
            ctx.log(f"Partition '{real_name}': {fmt_size(size)} "
                    f"[{classify_partition(real_name)}]", "DATA")
            if ctx.is_cancelled():
                return False

            if act == "read":
                ctx.progress(30, f"'{real_name}' parhi ja rahi "
                                 "hai...")
                try:
                    data = meta_patch.ft_part_read(session, real_name,
                                                   0, size)
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    return False
                if len(data) != size:
                    ctx.log(f"Read adhoora: {size} bytes mange, "
                            f"mile {len(data)} — SUCCESS nahi.",
                            "ERROR")
                    return False
                try:
                    PARTITION_BACKUP_DIR.mkdir(parents=True,
                                               exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    safe = re.sub(r"[^A-Za-z0-9]+", "-",
                                  real_name).strip("-")
                    path = (PARTITION_BACKUP_DIR /
                            f"{safe}-{ts}.bin")
                    path.write_bytes(data)
                except Exception as e:  # noqa: BLE001
                    ctx.log(f"Read file nahi ban saki: {e}", "ERROR")
                    return False
                ctx.log(f"Read mukammal: {path} ({fmt_size(size)}, "
                        f"sha256 {_sha256(data)[:16]}…)", "OK")
                ctx.progress(95, "Partition read mukammal")
                return True

            # write / erase — BACKUP-FIRST (dono par lazmi).
            backup = backup_partition(ctx, session, entry)
            if backup is None:
                return False
            if ctx.is_cancelled():
                return False

            if act == "write":
                src = single_bin(ctx, PARTITIONS_INBOX)
                if src is None:
                    return False
                data = src.read_bytes()
                if not data:
                    ctx.log(f"Input file khali hai: {src}", "ERROR")
                    return False
                if len(data) > size:
                    ctx.log(f"Input file {fmt_size(len(data))} hai — "
                            f"partition '{real_name}' sirf "
                            f"{fmt_size(size)} ki hai. Bari file "
                            "likhna mana hai (overflow = brick).",
                            "ERROR")
                    return False
                ctx.log(f"File: {src} ({fmt_size(len(data))})",
                        "INFO")
                ctx.progress(45, f"'{real_name}' likhi ja rahi "
                                 "hai...")
                try:
                    meta_patch.ft_part_write(session, real_name, 0,
                                             data)
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    ctx.log(f"Backup mehfooz hai: {backup} — "
                            "restore ke liye wahi file istemal "
                            "hogi.", "WARN")
                    return False
                if ctx.is_cancelled():
                    return False
                ctx.progress(75, "Read-back verify ho raha hai...")
                try:
                    back = meta_patch.ft_part_read(session, real_name,
                                                   0, len(data))
                except meta_session.MetaError as e:
                    ctx.log(str(e), "ERROR")
                    return False
                if back != data:
                    ctx.log("READ-BACK MATCH NAHI HUA — likha hua "
                            "data device se wapas parh kar match "
                            "nahi hua. Natija MASHKOOK hai; SUCCESS "
                            f"nahi diya ja raha. Backup: {backup}",
                            "ERROR")
                    return False
                ctx.log("Read-back verify PASS — poora likha hua "
                        "data byte-to-byte match hua.", "OK")
                ctx.log(f"Partition write mukammal — backup: "
                        f"{backup}", "OK")
                ctx.progress(95, "Partition write mukammal "
                                 "(verify shuda)")
                return True

            # erase — ft_checked NAHI (wo apna alag session kholta
            # hai; hum pehle se khule session ke andar hain).
            # Seedha isi session par request + status check.
            ctx.progress(45, f"'{real_name}' erase ho rahi hai...")
            try:
                status, _ = session.request(
                    meta_session.FT_ERASE_PARTITION,
                    payload=real_name.encode("ascii") + b"\x00",
                    timeout=25)
            except meta_session.MetaError as e:
                ctx.log(str(e), "ERROR")
                ctx.log(f"Backup mehfooz hai: {backup}", "WARN")
                return False
            if status != meta_session.FT_STATUS_OK:
                ctx.log(f"Erase '{real_name}': FT jawab aya lekin "
                        f"status token theek nahi (0x{status & 0xFF:02X}) "
                        "— amal qabool nahi hua mana jayega. Kuch "
                        "firmwares ye FT command support hi nahi "
                        "karte. " + f"Backup mehfooz hai: {backup}",
                        "ERROR")
                return False
            if ctx.is_cancelled():
                return False
            ctx.progress(75, "Erase verify ho raha hai (pehle 4 KB "
                             "zero/0xFF hone chahiyen)...")
            try:
                head = meta_patch.ft_part_read(session, real_name, 0,
                                               min(4096, size))
            except meta_session.MetaError as e:
                ctx.log(f"Erase verify ke liye read nahi ho saka: "
                        f"{e} — SUCCESS nahi diya ja raha. Backup: "
                        f"{backup}", "ERROR")
                return False
            if not head or (set(head) not in ({0}, {0xFF})):
                ctx.log("ERASE VERIFY FAIL — erase ke baad pehle "
                        "bytes zero/0xFF nahi mile (partition "
                        "shayad miti nahi). SUCCESS nahi diya ja "
                        f"raha. Backup: {backup}", "ERROR")
                return False
            ctx.log("Erase verify PASS — partition erased "
                    f"(pehle bytes {'0x00' if head[0] == 0 else '0xFF'}).",
                    "OK")
            ctx.log(f"Partition erase mukammal — backup: {backup}",
                    "OK")
            ctx.progress(95, "Partition erase mukammal "
                             "(verify shuda)")
            return True
    except meta_session.MetaError as e:
        ctx.log(str(e), "ERROR")
        return False
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Partition Manager ke doran ghalti: {e}", "ERROR")
        return False
    if ctx.is_cancelled():
        return False
    return True
