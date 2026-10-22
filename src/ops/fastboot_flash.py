"""
fastboot_flash.py — Fastboot Flash Pack (folder ke .img → partitions).

Folder: tools/flash-fastboot/ — har .img file ka naam hi us ki
partition ka naam hai (boot.img → boot, vendor_boot.img →
vendor_boot, vbmeta.img → vbmeta waghera). Sirf wohi partitions
flash hote hain jin ki .img file folder me mojood hai.

Usool: bootloader UNLOCKED pehle getvar se asal confirm hota hai
(fastboot_frp wala hi check). Koi aik flash fail ho jaye to
op wahin ruk jata hai (FAIL-fast) — adha flash hua pack aage
nahi chalaya jata. SUCCESS sirf tab jab har file exit 0 par
flash ho jaye.
"""

from core.runner import TOOLS_DIR
from ops.fastboot_frp import check_unlocked, resolve_fastboot

OP = {
    "id": "fastboot_flash",
    "category": "ADB / Fastboot",
    "name": "Flash Pack (folder ke .img → partitions)",
    "engine": "fastboot",
    "modes": ("FASTBOOT",),
    "server_required": False,
}

FLASH_DIR = TOOLS_DIR / "flash-fastboot"


def run(ctx) -> bool:
    fb = resolve_fastboot(ctx)
    if fb is None:
        return False
    serial = ctx.device.serial
    if not check_unlocked(ctx, fb, serial):
        return False

    ctx.log("⚠ KHABARDAR — BRICK KA KHATRA: ghalat ya doosre model "
            "ki image flash karne se phone BRICK ho sakta hai "
            "(boot hi nahi hoga). Sirf isi model ki, isi build ki "
            "images rakho. boot aur vbmeta khaas ehtiyat wale "
            "hain — vbmeta ghalat ho to verified boot fail ho "
            "jayega aur phone band par sakta hai. Pehle apna "
            "backup lazmi rakho.", "WARN")

    if not FLASH_DIR.is_dir():
        ctx.log(f"Flash folder nahi mila: {FLASH_DIR} — pehle ye "
                "folder banao aur is me .img files rakho.", "ERROR")
        ctx.log("Har image ka naam partition ke naam par rakho: "
                "boot.img, vendor_boot.img, vbmeta.img waghera. "
                "Sirf wohi partitions flash honge jin ki .img "
                "file mojood hai.", "WARN")
        return False

    images = sorted(FLASH_DIR.glob("*.img"),
                    key=lambda p: p.name.lower())
    if not images:
        ctx.log(f"Flash folder khali hai: {FLASH_DIR} — koi .img "
                "file nahi mili, flash karne ke liye kuch nahi.",
                "ERROR")
        ctx.log("Har image ka naam partition ke naam par rakho: "
                "boot.img, vendor_boot.img, vbmeta.img waghera. "
                "Sirf wohi partitions flash honge jin ki .img "
                "file mojood hai.", "WARN")
        return False

    names = [p.stem for p in images]
    ctx.log(f"{len(images)} image(s) mil gayi — ye partitions "
            f"flash honge: {', '.join(names)}", "INFO")

    flashed = []
    total = len(images)
    for idx, path in enumerate(images, start=1):
        if ctx.is_cancelled():
            ctx.log("User ne operation rok diya (STOP) — baqi "
                    "images flash nahi hui. Jo partitions pehle "
                    f"flash ho chuki hain: "
                    f"{', '.join(flashed) if flashed else 'koi nahi'}",
                    "WARN")
            return False
        stem = path.stem
        pct = 10 + int(80 * (idx - 1) / total)
        ctx.progress(pct, f"{stem} flash ho raha hai "
                          f"({idx}/{total})...")
        ctx.log(f"[{idx}/{total}] {stem} flash ho raha hai "
                f"({path.name})...", "INFO")
        code = ctx.stream([fb, "-s", serial, "flash", stem,
                           str(path)], timeout=900)
        if ctx.is_cancelled():
            return False
        if code != 0:
            ctx.log(f"{stem} flash FAIL hua (exit code {code}) — "
                    "op yahin ruk gaya hai, baqi images flash "
                    "nahi hongi. Wajah upar ke log me dekho "
                    "(ghalat image, partition naam ki ghalti, "
                    "ya cable/battery ka masla ho sakta hai). "
                    f"Pehle flash ho chuki partitions: "
                    f"{', '.join(flashed) if flashed else 'koi nahi'}.",
                    "ERROR")
            return False
        ctx.log(f"{stem} flash ho gaya.", "OK")
        flashed.append(stem)

    ctx.log(f"Flash Pack mukammal — ye partitions flash huin: "
            f"{', '.join(flashed)} ({len(flashed)}/{total}).",
            "OK")
    ctx.log("Phone abhi Fastboot mode me hi hai — reboot ke "
            "liye 'Reboot (Fastboot → Normal)' op chalao, ya "
            "phone ke Power button se on karo.", "INFO")
    ctx.progress(95, "Flash Pack mukammal")
    return True
