"""
util_install_drivers.py — Install Drivers (VCOM + Filter + Vendor Pack).

engines/drivers/ ke andar jo driver packages bundle hain un ki
pehle poori inventory log hoti hai, phir Windows par har package
tarteeb se install hota hai:

    Tarteeb: (1) MediaTek VCOM (.inf → pnputil /add-driver),
    (2) libusb-win32 filter installer (.exe, wizard hidayat
    log me pehle se), (3) Zadig (.exe — dusra WinUSB rasta,
    sirf zarurat par), (4) vendor packs (.msi → msiexec,
    .exe → vendor installer interactive).

    .msi → msiexec /i <file> /qb /norestart
    .exe → seedha chalaya jata hai (vendor installers interactive
           hote hain — screen par un ke apne sawal ayenge)
    .inf → pnputil /add-driver <file> /install

UsbDk ab bundle NAHI hai: Windows ke naye builds (24H2 /
26200) par wo MTKClient ko crash kar deta hai — is ki jagah
MediaTek VCOM + libusb filter wala rasta hai (tafseel
engines/drivers/README-DRIVERS.md me).

Imaandari:
  - Koi package na mile to guided FAIL — saath me official
    download guidance (engines/drivers/README-DRIVERS.md).
  - Ye op sirf Windows par install karta hai; doosre OS par
    inventory dikha kar guided FAIL.
  - SUCCESS sirf tab jab kam az kam 1 package mila ho AUR har
    koshish ka exit code 0 aya ho — aik bhi nakami par FAIL aur
    har package ka alag natija log me.
  - Driver install ke liye aam tor par ADMIN rights chahiye
    hote hain; kuch installers aakhir me reboot bhi mang sakte
    hain (msiexec wale raste par /norestart laga hai, vendor
    .exe apni marzi ke malik hain).
"""

import sys

from core.runner import ENGINES_DIR

OP = {
    "id": "util_install_drivers",
    "category": "Utility",
    "name": "Install Drivers (VCOM + Filter + Vendor Pack)",
    "engine": "drivers",
    "modes": (),
    "server_required": False,
}

_INSTALLABLE = (".msi", ".exe", ".inf")


def _human_size(n) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _group(pkg):
    """Install tarteeb ka group — VCOM pehle, filter dusra,
    Zadig teesra, baqi vendor packs aakhir me."""
    parent = pkg.parent.name.lower()
    name = pkg.name.lower()
    if parent == "mediatek-vcom" or name == "cdc-acm.inf":
        return 0
    if parent == "libusb-filter" or ("libusb" in name
                                     and "filter" in name):
        return 1
    if parent == "zadig" or name.startswith("zadig"):
        return 2
    return 3


def _scan_packages():
    """engines/drivers/** ke tamam .msi/.exe/.inf — install
    tarteeb me sorted (VCOM → filter → Zadig → vendor packs)."""
    base = ENGINES_DIR / "drivers"
    if not base.is_dir():
        return []
    found = [p for p in base.rglob("*")
             if p.is_file()
             and p.suffix.lower() in _INSTALLABLE]
    return sorted(found, key=lambda p: (_group(p),
                                        str(p).lower()))


def _install_cmd(path):
    """Package ki qisam ke mutabiq install command (list)."""
    suffix = path.suffix.lower()
    if suffix == ".msi":
        return ["msiexec", "/i", str(path), "/qb", "/norestart"]
    if suffix == ".inf":
        return ["pnputil", "/add-driver", str(path), "/install"]
    # .exe — vendor installer interactive hota hai, plain chalao
    return [str(path)]


def _pre_launch_lines(pkg):
    """Filter / Zadig se pehle ki khaas hidayat (log lines).

    Baqi packages ke liye khaali list — un par aam vendor wali
    line hi kaafi hai."""
    name = pkg.name.lower()
    parent = pkg.parent.name.lower()
    if parent == "libusb-filter" or ("libusb" in name
                                     and "filter" in name):
        return [
            "⚠ Filter installer — pehle ye hidayat parh lo: ye "
            "libusb-win32 ka setup hai. Setup mukammal ho jaye "
            "to is ke saath aya 'Filter Installation Wizard' "
            "chalao — wahan:",
            "  1) 'Install a device filter' select karo.",
            "  2) Phone BROM mode me lagao (band phone, Volume + "
            "aur − dono dabaye hue cable) — MediaTek VCOM "
            "driver is se pehle lag chuka hona chahiye (is op "
            "ki tarteeb me wo pehle ata hai).",
            "  3) List me 'MediaTek USB Port' select karke "
            "Install dabao. Yehi filter MTKClient ko us port ko "
            "kholne deta hai — MTK kaam ki asal kunji yehi hai.",
        ]
    if parent == "zadig" or name.startswith("zadig"):
        return [
            "⚠ Zadig SIRF zarurat par chalao — ye dusra rasta "
            "hai (WinUSB), pehla rasta filter wala hi rakho. "
            "Zadig aik device par WinUSB driver lagata hai; har "
            "PID alag device hai (BROM 0003, PreLoader 2000 "
            "waghera) — har aik par alag lagana parta hai. Aur "
            "jis PID par WinUSB lag gaya wo COM (serial) port "
            "NAHI rehta — SP Flash Tool jaise tools usay nahi "
            "dekh sakenge. Filter theek chal raha ho to Zadig "
            "mat chalao.",
        ]
    return []


def run(ctx) -> bool:
    drivers_dir = ENGINES_DIR / "drivers"
    packages = _scan_packages()

    ctx.log("Driver packages ki inventory (engines/drivers/):", "INFO")
    if packages:
        for p in packages:
            try:
                size = _human_size(p.stat().st_size)
            except Exception:  # noqa: BLE001
                size = "?"
            ctx.log(f"  {p.relative_to(drivers_dir)}  ({size})", "DATA")
        ctx.log(f"Kul {len(packages)} installable package(s) mile.",
                "INFO")
    else:
        ctx.log("  (koi .msi / .exe / .inf nahi mila)", "WARN")
        ctx.log("Driver package bundle nahi hai — guided FAIL. "
                "Lagta hai engines/drivers/ folder hi theek se "
                "nahi aya — MEER Tool Pro ka pack dobara download "
                "karke mukammal extract karo (drivers usi ke andar "
                "hain: MediaTek VCOM, libusb filter, Zadig, "
                "Samsung). Tafseel aur official sources is file "
                "me hain: engines/drivers/README-DRIVERS.md "
                "(app ke folder se engines\\drivers\\"
                "README-DRIVERS.md). Kisi ajnabi driver site se "
                "driver mat lena.", "ERROR")
        return False

    ctx.log("Install ki tarteeb: (1) MediaTek VCOM driver "
            "(.inf — phone ke BROM/PreLoader/DA ports), "
            "(2) libusb-win32 filter (MTKClient ko port kholne "
            "ki kunji), (3) Zadig sirf zarurat par (dusra WinUSB "
            "rasta), (4) vendor packs (Samsung waghera). "
            "UsbDk is pack me NAHI hai — naye Windows builds par "
            "wo MTKClient ko crash karta hai.", "INFO")

    if not sys.platform.startswith("win"):
        ctx.log(f"Ye system Windows nahi hai (sys.platform = "
                f"{sys.platform}) — driver install sirf Windows par "
                "hota hai. Upar wali inventory sirf maloomat ke "
                "liye hai; ye packages Windows PC par app ke saath "
                "rakh kar wahan ye op chalao.", "ERROR")
        return False

    ctx.log("Note: driver install ke liye ADMIN rights chahiye "
            "hote hain — app 'Run as administrator' se khuli ho to "
            "behtar hai. Kuch installers aakhir me PC reboot bhi "
            "mang sakte hain; kaam adhura na choro, installer ki "
            "screen mukammal hone do.", "WARN")

    results = []
    total = len(packages)
    for idx, pkg in enumerate(packages, start=1):
        if ctx.is_cancelled():
            return False
        pct = 10 + int(80 * (idx - 1) / total)
        ctx.progress(pct, f"Driver install ho raha hai: {pkg.name}")
        ctx.log(f"[{idx}/{total}] Install: {pkg.name} "
                f"({pkg.suffix.lower()})", "INFO")
        pre = _pre_launch_lines(pkg)
        for line in pre:
            ctx.log(line, "WARN")
        if pkg.suffix.lower() == ".exe" and not pre:
            ctx.log("Ye vendor .exe installer hai — interactive "
                    "chalega, us ki apni screen par Next/Install "
                    "wala flow mukammal karo.", "INFO")
        code = ctx.stream(_install_cmd(pkg), timeout=1200)
        if ctx.is_cancelled():
            return False
        ok = code == 0
        results.append((pkg, code, ok))
        if ok:
            ctx.log(f"  {pkg.name}: install exit code 0 — ho gaya.",
                    "OK")
        else:
            ctx.log(f"  {pkg.name}: exit code {code} — install "
                    "mukammal nahi hua.", "ERROR")

    ctx.log("Per-package natija:", "INFO")
    for pkg, code, ok in results:
        ctx.log(f"  {pkg.name}: exit {code} — "
                f"{'OK' if ok else 'FAIL'}",
                "OK" if ok else "ERROR")

    failed = [p for p, _c, ok in results if not ok]
    if failed:
        names = ", ".join(p.name for p in failed)
        ctx.log(f"{len(failed)}/{total} package(s) fail hue: "
                f"{names}. Aam wajahen: admin rights na hona, "
                "installer ki screen par user ka ruk jana, ya "
                "purana driver pehle se mojood hona. Upar har "
                "installer ki asal output mehfooz hai.", "ERROR")
        return False

    ctx.progress(95, "Tamam drivers install ho gaye")
    ctx.log(f"Tamam {total} driver package(s) exit code 0 ke "
            "saath install hue. Kisi installer ne reboot manga ho "
            "to phone lagane se pehle PC restart kar lo — driver "
            "reboot ke baad hi asal me load hota hai. MTK ke liye "
            "yaad rakho: VCOM ke baad libusb filter 'MediaTek "
            "USB Port' par lagana baqi ho to Filter Wizard wala "
            "step mukammal karo (upar hidayat di gayi hai).", "OK")
    return True
