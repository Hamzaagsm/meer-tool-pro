"""
adb_info.py — ADB se asal device info parhna.

`adb shell getprop` chalakar brand/model/chip/android/serial nikaalta hai
aur device panel ko update karta hai. Ye purane launcher-style tool se
bunyadi farq hai: info asal me phone se ATI hai, hardcode nahi hoti.
"""

import shutil

from core import device_watch

OP = {
    "id": "adb_info",
    "category": "ADB / Fastboot",
    "name": "Read Device Info (ADB)",
    "engine": "adb",
    "modes": ("ADB",),
    "server_required": False,
}


def run(ctx) -> bool:
    adb = shutil.which("adb")
    if not adb:
        ctx.log("adb nahi mila — platform-tools app ke tools/ folder me ya "
                "PATH me chahiye.", "ERROR")
        return False
    dev = ctx.device
    if not dev or dev.mode != "ADB":
        ctx.log("Device ADB mode me nahi hai. Phone on karke USB debugging "
                "ON karo aur dobara lagao.", "ERROR")
        return False

    ctx.progress(15, "getprop parha ja raha hai...")
    props = device_watch.adb_getprops(adb, dev.serial)
    if not props:
        ctx.log("getprop se koi jawab nahi aya — cable/authorization check karo "
                "(phone par 'Allow USB debugging' ayega, use Allow karo).", "ERROR")
        return False

    device_watch.enrich_from_props(dev, props)
    ctx.progress(70, "Info mili — panel update ho raha hai")

    rows = [
        ("Brand", dev.brand), ("Model", dev.model), ("Chip / Platform", dev.chip),
        ("Android", dev.android), ("Serial", dev.serial),
        ("Build", props.get("ro.build.display.id", "")),
        ("Security Patch", props.get("ro.build.version.security_patch", "")),
        ("IMEI note", "IMEI sirf original-restore ke liye — ye op nahi parhta"),
    ]
    for key, val in rows:
        if val:
            ctx.log(f"{key}: {val}", "DATA")
    if ctx.update_device:
        ctx.update_device(dev)
    ctx.progress(95, "Mukammal")
    return True
