"""
spd_fdl.py — Unisoc FDL session ki mushtarak plumbing (spd_dump).

Char ops isay istemal karte hain: spd_frp (FRP = erase persist),
spd_reset (userdata + metadata erase), spd_cert_backup (prodnv
read) aur spd_cert_restore (prodnv write). Session ka imaandar
design (REPAIR-METHODS-RESEARCH §1.2, §4 P1#2):

  - Engine: spd_dump (open-source, Unlicense) — engines/spd_dump/.
  - FDL1/FDL2: model ke APNE stock PAC se nikle hue (signed stock
    FDL hi BootROM accept karta hai). PAC ke item table se
    extraction yahin hoti hai (core/pac_builder ka layout).
  - FDL load addresses (Base): model ke firmware XML se parhe
    jate hain (PAC ke andar ki XML entry, ya tools/spd/ me rakhi
    XML). Base na mile to session NAHI banta — andaze se address
    lagana hardware ke liye khatarnak hai (upstream warning).
  - spd_dump erase/write par terminal par "yes" poochta hai;
    stream_yes() stdin par "yes" bhejta hai kyun ke GUI me op
    chalana hi user ki tasdeeq hai — ye baat log me likhi jati hai.
  - Chip layer (core/spd_chips): device se model/chip resolve
    karke session ki shuruaat me chip + boot-key line log hoti
    hai. Chip na mile to bhi session aam rehnumai par chalta
    hai — chip layer sirf izafa hai, rukawat kabhi nahi.
  - FDL Library (tools/loaders/spd/): PAC se nikla FDL set
    model code ke naam par mehfooz ho jata hai (index.json ke
    saath). Agli dafa usi model ke liye PAC na ho to library
    wala set session deta hai. Library hamesha MODEL CODE par
    keyed hai — doosre model ka FDL kabhi istemal nahi hota
    (FDL2 ka pinmap per-model hota hai, upstream warning).
"""

import json
import re
import shutil
import struct
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from core import pac_builder
from core.runner import TOOLS_DIR

WAIT_SECONDS = 120


# ---------------------------------------------------------------------------
# PAC se FDL / XML extraction
# ---------------------------------------------------------------------------
def _pac_entries(pac_path):
    """PAC item table parho — [{file_id, file_name, size, pos}]."""
    data_head = Path(pac_path).read_bytes()[
        : pac_builder.HEADER_SIZE + pac_builder.ITEM_SIZE * 512]
    if len(data_head) < pac_builder.HEADER_SIZE:
        raise ValueError("PAC file header se chhoti hai.")
    file_count = struct.unpack_from("<I", data_head, 1076)[0]
    if file_count == 0 or file_count > 512:
        raise ValueError(f"PAC dwFileCount ghair-mamooli hai: {file_count}")
    entries = []
    for i in range(file_count):
        off = pac_builder.HEADER_SIZE + i * pac_builder.ITEM_SIZE
        item = data_head[off:off + pac_builder.ITEM_SIZE]
        if len(item) < pac_builder.ITEM_SIZE:
            raise ValueError("PAC item table na-mukammal hai.")
        entries.append({
            "file_id": pac_builder._read_wchar(item[4:516]),
            "file_name": pac_builder._read_wchar(item[516:1028]),
            "file_size": struct.unpack_from("<I", item, 1540)[0],
            "download_pos": struct.unpack_from("<I", item, 1548)[0],
        })
    return entries


def _extract_entry(pac_path, entry, out_path):
    """Aik PAC entry ka data out_path par nikalo (seek-based)."""
    with open(pac_path, "rb") as fh:
        fh.seek(entry["download_pos"])
        blob = fh.read(entry["file_size"])
    if len(blob) != entry["file_size"]:
        raise ValueError(f"{entry['file_name']} ka data PAC se "
                         "mukammal nahi nikla.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    return out_path


def find_stock_pac():
    """(pac_path|None, note) — tools/spd/ me stock PAC dhoondo.

    Aik se zyada PAC hon to None (galat model ka PAC = brick risk;
    technician ko sirf nishana model ki PAC rakhni hai).
    """
    spd_dir = TOOLS_DIR / "spd"
    if not spd_dir.is_dir():
        return None, "tools/spd/ folder hi nahi mila."
    pacs = sorted(p for p in spd_dir.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".pac")
    if not pacs:
        return None, ("tools/spd/ me koi stock .pac nahi mila — pehle "
                      "is model ka asal stock PAC firmware wahan rakho.")
    if len(pacs) > 1:
        names = ", ".join(p.name for p in pacs)
        return None, (f"{len(pacs)} PAC files milin ({names}) — galat "
                      "model ki PAC se FDL lena phone brick kar sakta "
                      "hai. Sirf is model ki PAC rakho, baqi hata do.")
    return pacs[0], ""


# ---------------------------------------------------------------------------
# FDL Library — tools/loaders/spd/<model-code>/ (harvest + reuse)
# ---------------------------------------------------------------------------
# PAC se nikla har FDL set model code ke naam par yahan mehfooz
# hota hai (fdl1.bin + fdl2.bin + bases.json), aur index.json me
# us ki entry banti hai. Reuse SIRF usi model code par hai —
# doosre model ka FDL2 (pinmap per-model) kabhi istemal nahi
# hota. PAC tools/spd/ me maujood ho to PAC hamesha jeet-ta hai
# (taaza firmware purani library se behtar); library sirf tab
# session deti hai jab PAC na ho, ya jab library ka source yehi
# PAC ho (naam + size match — extraction dohrana bekaar hai).
SPD_LIB_DIR = TOOLS_DIR / "loaders" / "spd"
SPD_LIB_INDEX = SPD_LIB_DIR / "index.json"


def _lib_index_entries():
    """index.json ki entries (list of dict) — kharab/na ho to []."""
    try:
        data = json.loads(SPD_LIB_INDEX.read_text(encoding="utf-8"))
        entries = data.get("entries", []) if isinstance(data, dict) \
            else []
        if not isinstance(entries, list):
            return []
        return [e for e in entries if isinstance(e, dict)]
    except Exception:  # noqa: BLE001
        return []


def _save_lib_index(entries):
    SPD_LIB_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": "MEER Tool Pro — SPD FDL Library Index",
        "version": 1,
        "note": "Har entry AIK model code ki hai; FDL reuse sirf "
                "usi model code par — cross-model reuse kabhi "
                "nahi (FDL2 pinmap per-model hota hai).",
        "entries": entries,
    }
    SPD_LIB_INDEX.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False),
        encoding="utf-8")


def library_entry(model_code):
    """Model code ke liye library entry — files asal me maujood
    aur bases mehfooz hon tab hi normalized dict, warna None.

    Return: {model_code, chip, fdl1_path, fdl2_path, base1,
    base2, source_pac, source_pac_size, harvested_at}
    """
    if not model_code:
        return None
    q = str(model_code).strip().lower()
    if not q:
        return None
    for e in _lib_index_entries():
        if str(e.get("model_code", "")).strip().lower() != q:
            continue
        rel1 = str(e.get("fdl1", "") or "")
        rel2 = str(e.get("fdl2", "") or "")
        if not rel1 or not rel2:
            continue
        p1 = SPD_LIB_DIR / rel1
        p2 = SPD_LIB_DIR / rel2
        if not p1.is_file() or not p2.is_file():
            continue
        if not e.get("base1") or not e.get("base2"):
            continue
        return {
            "model_code": e.get("model_code", ""),
            "chip": e.get("chip", ""),
            "fdl1_path": p1,
            "fdl2_path": p2,
            "base1": e["base1"],
            "base2": e["base2"],
            "source_pac": e.get("source_pac", ""),
            "source_pac_size": e.get("source_pac_size"),
            "harvested_at": e.get("harvested_at", ""),
        }
    return None


def harvest_to_library(ctx, pac, fdl1_path, fdl2_path, base1, base2,
                       model_code, chip_name):
    """Extract hue FDL set ko library me mehfooz karo.

    model_code na mile to PAC ke file naam (stem) par key banti
    hai. Nakami session ko NAHI rokti — sirf log hota hai
    (asal FDL tools/spd/fdl-*/ me pehle se mehfooz hai).
    """
    try:
        code = str(model_code or "").strip() or Path(pac).stem
        dest_dir = SPD_LIB_DIR / code
        dest_dir.mkdir(parents=True, exist_ok=True)
        d1 = dest_dir / "fdl1.bin"
        d2 = dest_dir / "fdl2.bin"
        shutil.copy2(fdl1_path, d1)
        shutil.copy2(fdl2_path, d2)
        if d1.stat().st_size != Path(fdl1_path).stat().st_size \
                or d2.stat().st_size != Path(fdl2_path).stat().st_size:
            ctx.log("FDL library copy ka size match nahi — entry "
                    "nahi banayi gayi (session par asar nahi).",
                    "WARN")
            return False
        stamp = datetime.now().isoformat(timespec="seconds")
        bases = {
            "base1": base1, "base2": base2,
            "source_pac": Path(pac).name, "model_code": code,
            "chip": chip_name or "", "harvested_at": stamp,
        }
        (dest_dir / "bases.json").write_text(
            json.dumps(bases, indent=1, ensure_ascii=False),
            encoding="utf-8")
        entries = [e for e in _lib_index_entries()
                   if str(e.get("model_code", "")).strip().lower()
                   != code.lower()]
        entries.append({
            "model_code": code,
            "chip": chip_name or "",
            "fdl1": f"{code}/fdl1.bin",
            "fdl2": f"{code}/fdl2.bin",
            "base1": base1,
            "base2": base2,
            "source_pac": Path(pac).name,
            "source_pac_size": Path(pac).stat().st_size,
            "harvested_at": stamp,
        })
        entries.sort(key=lambda e: str(e.get("model_code", "")).lower())
        _save_lib_index(entries)
        ctx.log(f"FDL library me mehfooz ho gaya: "
                f"tools/loaders/spd/{code}/ (model code: {code}) — "
                "agli dafa is model ke liye yehi set library se "
                "mil jayega.", "INFO")
        return True
    except Exception as e:  # noqa: BLE001 — harvest kabhi rukawat nahi
        ctx.log(f"FDL library me mehfooz nahi ho saka ({e}) — "
                "session par asar nahi, FDL tools/spd/ me "
                "maujood hai.", "WARN")
        return False


def _count_stock_pacs():
    """tools/spd/ me .pac files ki taadad (library branch ke liye)."""
    spd_dir = TOOLS_DIR / "spd"
    if not spd_dir.is_dir():
        return 0
    return len([p for p in spd_dir.rglob("*")
                if p.is_file() and p.suffix.lower() == ".pac"])


def parse_fdl_bases(xml_text):
    """Firmware XML se (fdl1_base, fdl2_base) hex strings ya (None, None).

    XML me FDL ke hisay mukhtalif shaklon me ate hain — tolerant
    talaash: 'FDL'/'FDL2' ke qareeb 'Base' ki value (attribute ya
    element text, hex). Kuch na mile to (None, None) — caller
    guided FAIL dega, andaza NAHI lagega.
    """
    if not xml_text:
        return None, None

    def _base_near(tag_pattern):
        for m in re.finditer(tag_pattern, xml_text, re.IGNORECASE):
            window = xml_text[m.start():m.start() + 600]
            b = re.search(r"[Bb]ase\s*=\s*\"(0x[0-9a-fA-F]+)\"", window)
            if b:
                return b.group(1)
            b = re.search(r"<\s*[Bb]ase\s*>\s*(0x[0-9a-fA-F]+)", window)
            if b:
                return b.group(1)
        return None

    fdl2 = _base_near(r"FDL2")
    fdl1 = _base_near(r"FDL(?!2)")
    return fdl1, fdl2


def prepare_fdl(ctx):
    """Poori tayyari: (session_dict|None) — nakami par log de chuka hoga.

    session = {exe, fdl1_path, fdl2_path, base1, base2, pac}
    """
    from core import engines
    exe, note = engines.find_spd_dump()
    if exe is None:
        ctx.log(note, "ERROR")
        return None
    ctx.log(note, "INFO")

    # --- Chip layer: device se model/chip resolve (additive —
    # nakami par session aam tareeqe se chalta hai, rukawat nahi)
    model_row = None
    chip_row = None
    model_code = ""
    try:
        from core import spd_chips
        _ctx3 = spd_chips.context_for_device(
            getattr(ctx, "device", None))
        model_row = _ctx3.get("model")
        chip_row = _ctx3.get("chip")
        model_code = _ctx3.get("model_code") or ""
    except Exception:  # noqa: BLE001
        model_row = chip_row = None
    if chip_row is not None:
        _line = "Chip: " + spd_chips.chip_summary(chip_row)
        if model_row is not None:
            _line = (f"Model: {model_row.get('brand', '')} "
                     f"{model_row.get('model', '')} "
                     f"({model_row.get('code', '')}) → " + _line)
        ctx.log(_line, "INFO")
        _guide = spd_chips.boot_guidance(chip_row)
        if _guide:
            ctx.log(_guide, "INFO")
    elif model_row is not None:
        ctx.log("Model pehchana gaya lekin is ki chipset ki "
                "chip-table row nahi mili — session aam rehnumai "
                "par chalega.", "WARN")

    # --- FDL Library: is model code ka harvested set (agar hai)
    lib = None
    if model_code:
        try:
            lib = library_entry(model_code)
        except Exception:  # noqa: BLE001
            lib = None

    pac, pnote = find_stock_pac()
    if pac is not None and lib is not None:
        # Library ka source YEHI PAC hai (naam + size match) to
        # extraction dohrana bekaar hai — library copy chalegi.
        try:
            _same = (lib["source_pac"] == pac.name and
                     (lib["source_pac_size"] is None or
                      lib["source_pac_size"] == pac.stat().st_size))
        except Exception:  # noqa: BLE001
            _same = False
        if _same:
            ctx.log(f"FDL library se mila (model code "
                    f"{model_code}) — yehi PAC ({lib['source_pac']}, "
                    f"harvest: {lib['harvested_at']}) pehle se "
                    "library me mehfooz hai, library copy istemal "
                    "hogi.", "OK")
            return {"exe": exe, "fdl1": lib["fdl1_path"],
                    "fdl2": lib["fdl2_path"], "base1": lib["base1"],
                    "base2": lib["base2"], "pac": pac}
    if pac is None:
        # PAC nahi mila. Zyada-PAC wali surat me library se bhi
        # nahi lenge (wohi brick-risk wali confusion) — sirf
        # 0-PAC par library is model ki kami poori karti hai.
        if lib is not None and _count_stock_pacs() == 0:
            ctx.log(f"FDL library se mila (model code "
                    f"{model_code}) — source PAC: "
                    f"{lib['source_pac']} (harvest: "
                    f"{lib['harvested_at']}). tools/spd/ me PAC "
                    "nahi hai, is liye library wala set session "
                    "de raha hai.", "OK")
            ctx.log(f"FDL Base addresses (library): "
                    f"FDL1={lib['base1']}, FDL2={lib['base2']}",
                    "INFO")
            return {"exe": exe, "fdl1": lib["fdl1_path"],
                    "fdl2": lib["fdl2_path"], "base1": lib["base1"],
                    "base2": lib["base2"], "pac": None}
        ctx.log(pnote, "ERROR")
        ctx.log("Guide: FDL hamesha model ke APNE stock PAC se ata "
                "hai (signed stock FDL) — doosre model ka FDL "
                "hardware risk hai.", "WARN")
        return None
    ctx.log(f"Stock PAC: {pac.name}", "INFO")

    try:
        entries = _pac_entries(pac)
    except (ValueError, OSError) as e:
        ctx.log(f"PAC parha nahi ja saka: {e}", "ERROR")
        return None

    by_id = {}
    for ent in entries:
        fid = (ent["file_id"] or "").strip().upper()
        if fid and fid not in by_id:
            by_id[fid] = ent
    fdl1_ent = by_id.get("FDL")
    fdl2_ent = by_id.get("FDL2")
    if fdl1_ent is None:
        # kuch PACs me FDL1 ka FileID naam se hota hai (fdl1-sign.bin)
        for ent in entries:
            if "fdl1" in (ent["file_name"] or "").lower():
                fdl1_ent = ent
                break
    if fdl2_ent is None:
        for ent in entries:
            if "fdl2" in (ent["file_name"] or "").lower():
                fdl2_ent = ent
                break
    if fdl1_ent is None or fdl2_ent is None:
        ctx.log("PAC me FDL1/FDL2 entries nahi milin — ye PAC is "
                "session ke qabil nahi hai (mukammal stock PAC "
                "chahiye jis me FDL shamil ho).", "ERROR")
        return None

    out_dir = TOOLS_DIR / "spd" / ("fdl-" + pac.stem)
    try:
        fdl1_path = _extract_entry(pac, fdl1_ent, out_dir / "fdl1.bin")
        fdl2_path = _extract_entry(pac, fdl2_ent, out_dir / "fdl2.bin")
    except (ValueError, OSError) as e:
        ctx.log(f"FDL extraction fail: {e}", "ERROR")
        return None
    ctx.log(f"FDL1 nikala: {fdl1_path} ({fdl1_ent['file_size']} bytes)",
            "INFO")
    ctx.log(f"FDL2 nikala: {fdl2_path} ({fdl2_ent['file_size']} bytes)",
            "INFO")

    # --- FDL base addresses: pehle PAC ki XML, phir tools/spd ki XML
    xml_text = ""
    for ent in entries:
        if (ent["file_name"] or "").lower().endswith(".xml"):
            try:
                tmp = _extract_entry(pac, ent, out_dir / "pac.xml")
                xml_text = tmp.read_text(encoding="utf-8",
                                         errors="ignore")
            except (ValueError, OSError):
                xml_text = ""
            break
    if not xml_text:
        spd_dir = TOOLS_DIR / "spd"
        for cand in sorted(spd_dir.glob("*.xml")):
            try:
                xml_text = cand.read_text(encoding="utf-8",
                                         errors="ignore")
            except OSError:
                continue
            if xml_text:
                break
    base1, base2 = parse_fdl_bases(xml_text)
    if not base1 or not base2:
        ctx.log("FDL load addresses (Base) nahi mile — na PAC ki XML "
                "me, na tools/spd/ ki kisi XML me. Andaze se address "
                "NAHI lagega (galat Base hardware ko nuqsan de sakta "
                "hai).", "ERROR")
        ctx.log("Guide: model ke firmware ki XML file (Research "
                "Download PAC load karne par ImageFiles folder me "
                "nikalti hai) tools/spd/ me rakho — us me FDL aur "
                "FDL2 ke Base likhe hote hain. Phir dobara chalao.",
                "WARN")
        return None
    ctx.log(f"FDL Base addresses: FDL1={base1}, FDL2={base2}", "INFO")

    # --- Harvest: ye set model code ke naam par library me bhi
    # mehfooz ho jaye (agli dafa PAC na ho to library kaam aye).
    # Device se model code na mila ho to PAC ke naam me code
    # dhoondhne ki koshish — phir bhi na mile to key PAC stem hai.
    _harvest_code = model_code
    _chip_name = chip_row.get("chip", "") if chip_row else ""
    if not _harvest_code:
        try:
            from core import spd_chips as _sc
            _m2 = _sc.model_in_text(pac.stem)
            if _m2 is not None:
                _harvest_code = str(_m2.get("code", "") or "")
                if not _chip_name:
                    _c2 = _sc.chip_for_chipset(_m2.get("chipset"))
                    if _c2 is not None:
                        _chip_name = _c2.get("chip", "")
        except Exception:  # noqa: BLE001
            pass
    harvest_to_library(ctx, pac, fdl1_path, fdl2_path, base1, base2,
                       _harvest_code, _chip_name)

    return {"exe": exe, "fdl1": fdl1_path, "fdl2": fdl2_path,
            "base1": base1, "base2": base2, "pac": pac}


def session_args(session, commands):
    """spd_dump argv: wait + keep_charge + FDL dono + commands."""
    return [session["exe"], "--wait", str(WAIT_SECONDS),
            "keep_charge", "1",
            "fdl", str(session["fdl1"]), session["base1"],
            "fdl", str(session["fdl2"]), session["base2"],
            "disable_transcode"] + list(commands)


def stream_yes(ctx, cmd, timeout=600, cwd=None):
    """ctx.stream jaisa, lekin stdin par 'yes' tayyar rakhta hai.

    spd_dump har destructive command (erase/write) se pehle
    terminal par "yes" mangta hai — GUI me op chalana hi user ki
    tasdeeq hai, is liye stdin par yes bheja jata hai. STOP/timeout
    ka bartao ctx.stream jaisa hi rakha hai.
    Return: exit code (int), cancel/timeout par -1/-2 walay rawaj
    ke bajaye process ka code ya -1.
    """
    ctx.log(" ".join(str(c) for c in cmd), "CMD")
    ctx.log("Note: spd_dump ke 'yes' confirmations is op ke GUI "
            "action ki tasdeeq par khud diye jayenge.", "INFO")
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            cwd=str(cwd) if cwd else None, **kwargs)
    except FileNotFoundError:
        ctx.log(f"Engine nahi mila: {cmd[0]}", "ERROR")
        return -1
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Process shuru nahi ho saka: {e}", "ERROR")
        return -1
    ctx._proc = proc
    try:
        try:
            proc.stdin.write("yes\n" * 16)
            proc.stdin.flush()
        except Exception:  # noqa: BLE001
            pass
        timer = None
        if timeout:
            timer = threading.Timer(timeout, proc.kill)
            timer.daemon = True
            timer.start()
        assert proc.stdout is not None
        for line in proc.stdout:
            if ctx.is_cancelled():
                proc.terminate()
                ctx.log("User ne operation rok diya (STOP).", "WARN")
                break
            line = line.rstrip("\n")
            if line.strip():
                ctx.log(line, "DATA")
        proc.wait()
        if timer:
            timer.cancel()
        return proc.returncode if proc.returncode is not None else -1
    finally:
        ctx._proc = None


def parse_partition_xml(text):
    """spd_dump ke `partition_list` XML se {naam: size_bytes}.

    XML me size KiB units me ata hai (partition_list wala
    format, sh=10). Aakhri partition ka size marker (0xFFFFFFFF)
    skip hota hai. Kharab entry par wo entry skip — poora dict
    kabhi andaze se nahi banta.
    """
    parts = {}
    if not text:
        return parts
    for m in re.finditer(r'<\s*Partition\s+id="([^"]+)"\s+'
                         r'size="(0x[0-9a-fA-F]+|\d+)"', text):
        name = m.group(1).strip()
        raw = m.group(2)
        try:
            val = int(raw, 16) if raw.lower().startswith("0x") \
                else int(raw)
        except ValueError:
            continue
        if val >= 0xFFFFFFFF:
            continue
        parts[name] = val << 10
    return parts


def spd_guard(ctx) -> bool:
    """Device SPRD (DIAG/download) mode me hona chahiye."""
    dev = ctx.device
    if not dev or dev.mode != "SPD":
        boot = "Volume Down (kuch models par Up)"
        try:
            from core import spd_chips
            _chip = spd_chips.chip_for_device(dev)
            if _chip is not None and _chip.get("boot_key"):
                boot = str(_chip["boot_key"])
        except Exception:  # noqa: BLE001 — rehnumai hi hai, rukawat nahi
            pass
        ctx.log("Device SPRD mode me nahi mila. Phone band karke "
                f"boot key dabaye hue cable lagao — {boot}. "
                "Device Manager me SPRD port (1782:4D00) ana "
                "chahiye, aur spd_dump download gadget ka wait "
                "karega.",
                "ERROR")
        return False
    return True
