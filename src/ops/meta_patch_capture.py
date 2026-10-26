"""
meta_patch_capture.py — Anti-Crack Patch-Data Capture (META, bench).

Bench program: Hamza ke phone par chala kar per-model META patch
bytes capture karta hai aur tools/meta-patch-data.json ki
"captures" section + tools/meta-patch-captures/ me save karta hai.

SIRF READ — is op me device par KUCH NAHI likha jata (na patch,
na removal, na IMEI). Anti-crack removal / patch apply is program
ka kaam NAHI hai — wo alag round me hoga, jab patch bytes capture
ho chuke hon aur bench par compare ho chuke hon.

SUCCESS sirf tab jab kam az kam aik partition (proinfo/prodnv)
verified capture ho kar record save ho. Device refuse kare to
saaf FAIL + wajah — "capture hua" ka jhoota daawa kabhi nahi.
"""

import dataclasses

from core import meta_patch_capture, meta_session

OP = {
    "id": "meta_patch_capture",
    "category": "MDM / Transsion",
    "name": "Anti-Crack Patch-Data Capture (META, bench)",
    "engine": "meta",
    "modes": (),
    "server_required": False,
}


def _device_model_label(ctx):
    dev = getattr(ctx, "device", None)
    if dev is None:
        return "", "", ""
    label = " ".join([str(getattr(dev, "brand", "") or ""),
                      str(getattr(dev, "model", "") or "")]).strip()
    return (meta_patch_capture.model_slug(label),
            str(getattr(dev, "chip", "") or ""), label)


def run(ctx) -> bool:
    ctx.log("Anti-crack patch-data CAPTURE shuru — READ-ONLY program: "
            "device par kuch nahi likha jayega, sirf proinfo/prodnv "
            "parhe jayenge aur local file me save honge.", "INFO")
    ctx.log("Yaad rahe: ye capture hai, removal NAHI — patch bytes "
            "milne ke baad hi alag round me removal banega. Koi "
            "server upload nahi hota.", "WARN")
    session = meta_session.open_session(ctx)
    if session is None:
        return False

    model_code, chipset, label = _device_model_label(ctx)
    if not model_code or model_code == "unknown-model":
        # Device info na ho to bhi capture chal sakta hai — lekin
        # record ke liye koi pehchan chahiye; pehle Read Info chalao.
        ctx.log("Device ka model/chip maloom nahi (panel khali hai) — "
                "pehle 'Read Info (META Mode)' chalao taake capture "
                "record kis model ka hai ye pata chale, phir ye op "
                "dobara chalao.", "ERROR")
        return False

    # FT version/info best-effort — model/chip panel taza karne ke
    # liye; na mile to capture phir bhi device ki pehchan se chalega.
    # NOTE: session pehle se khula hai (open_session) — yahan `with`
    # istemal NAHI karna, warna __exit__ port band kar dega aur
    # neeche wala capture chal hi nahi payega.
    try:
        status, payload = session.request(
            meta_session.FT_VERSION_INFO, timeout=15)
        if status == meta_session.FT_STATUS_OK and payload:
            text = payload.decode("utf-8", errors="replace")
            lines = [ln.strip() for ln in text.splitlines()
                     if ln.strip()]
            if lines:
                ctx.log("FT info: " + " | ".join(lines[:4]), "DATA")
    except meta_session.MetaError as e:
        ctx.log(f"FT info request nakam ({e}) — capture phir bhi "
                "device ki maujooda pehchan se chalega.", "WARN")

    ctx.progress(30, "proinfo / prodnv capture ho rahe hain...")
    try:
        summary = meta_patch_capture.run_capture(
            session, model_code, chipset=chipset, model_label=label,
            ctx=ctx)
    except meta_patch_capture.CaptureError as e:
        ctx.log(str(e), "ERROR")
        ctx.log("Guide: kuch firmwares par FT partition read supported "
                "nahi hota — aisi surat me capture imaandari se FAIL "
                "hi rahega. Cable/port check karke dobara try karo; "
                "agar device baar baar refuse kare to is model ka "
                "patch data bench se is rasty nahi milega (research "
                "me note karna).", "WARN")
        return False
    finally:
        session.close()
    if ctx.is_cancelled():
        return False

    ctx.progress(90, "Capture record save ho gaya")
    for part, entry in summary["results"].items():
        if entry["status"] == "captured":
            ctx.log(f"Captured: {part} — {entry['size_bytes']} bytes, "
                    f"sha256 {entry['sha256'][:16]}…, file "
                    f"{entry.get('file', '')}", "OK")
        else:
            ctx.log(f"{part}: {entry['status']} — "
                    f"{entry.get('reason', '')}", "WARN")
    ctx.log(f"Anti-crack capture mukammal: model '{model_code}' — "
            f"{summary['captured_count']}/{len(summary['results'])} "
            f"partitions captured. Record tools/meta-patch-data.json "
            f"ki 'captures' section me + raw bytes "
            f"tools/meta-patch-captures/{model_code}/ me save hain.",
            "OK")
    ctx.log("Agla qadam (bench): isi model ka doosra phone / patch "
            "ke baad wala snapshot compare karo taake asal anti-crack "
            "patch region pehchana ja sake — us ke baghair removal "
            "NAHI banega.", "INFO")
    # Panel par model/mode taza rakho (capture ne device ko nahi badla).
    try:
        dev = getattr(ctx, "device", None)
        if dev is not None and getattr(ctx, "update_device", None):
            ctx.update_device(dataclasses.replace(dev, mode="META"))
    except Exception:  # noqa: BLE001
        pass
    ctx.progress(95, "Capture mukammal")
    return True
