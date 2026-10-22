"""
samsung_firmware_info.py — Samsung device se firmware pehchan parhna.

ADB getprop se Model / CSC / PDA / Android / Security Patch parh kar
DATA lines me dikhata hai, taake user wahi Model + CSC kisi free
firmware utility (SamFirm / SamLoader / Frija) me dal kar Samsung ke
official servers se sahi firmware download kar sake.

Ye op khud firmware download ya flash NAHI karta — pehchan aur
guide hi is ka kaam hai (is build me Samsung flash shamil nahi).
"""

from core import device_watch, engines

OP = {
    "id": "samsung_firmware_info",
    "category": "Samsung",
    "name": "Firmware Download Helper (Samsung)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}


def run(ctx) -> bool:
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai. Phone on karke USB debugging ON "
                "karo, cable lagao aur phone par 'Allow USB debugging' ayega "
                "to use Allow karo — phir ye op dobara chalao.", "ERROR")
        return False

    ctx.progress(20, "getprop parha ja raha hai...")
    try:
        props = device_watch.adb_getprops(
            engines.find_platform_tool("adb"), dev.serial)
    except Exception:
        props = {}
    if not props:
        ctx.log("getprop se jawab nahi aya — authorization check karo: phone "
                "par 'Allow USB debugging' ka prompt Allow kiya tha? Cable "
                "badal kar dobara koshish karo.", "ERROR")
        return False

    brand = props.get("ro.product.brand", "")
    if "samsung" not in brand.lower():
        ctx.log(f"Ye device Samsung nahi lagta (brand: {brand or 'maloom nahi'}) "
                "— phir bhi jo values mili hain wo neeche dikha di hain.", "WARN")

    model = props.get("ro.product.model", "")
    csc = props.get("ro.csc.sales_code", "") or props.get("ro.csc.country_code", "")
    pda = props.get("ro.build.PDA", "")
    android = props.get("ro.build.version.release", "")
    patch = props.get("ro.build.version.security_patch", "")

    rows = [
        ("Model", model),
        ("CSC", csc),
        ("PDA / Build", pda),
        ("Android", android),
        ("Security Patch", patch),
    ]
    for key, val in rows:
        if val:
            ctx.log(f"{key}: {val}", "DATA")

    ctx.progress(70, "Firmware pehchan mil gayi")
    ctx.log("Firmware dhoondhne ke liye upar wale Model + CSC bilkul waisi hi "
            "kisi free firmware utility (SamFirm / SamLoader / Frija) me dalo — "
            "ye utilities Samsung ke official servers se hi firmware download "
            "karti hain. CSC galat dala to doosre region ki firmware ayegi "
            "(language/network ka farq par sakta hai). Download ke baad flash "
            "ke liye Download Mode + Odin/Heimdall alag qadam hai — is build me "
            "Samsung flash shamil nahi.", "INFO")

    if not model and not pda:
        ctx.log("Model aur PDA dono nahi mile — is pehchan se sahi firmware "
                "dhoondhna mumkin nahi.", "ERROR")
        return False
    ctx.progress(95, "Mukammal")
    return True
