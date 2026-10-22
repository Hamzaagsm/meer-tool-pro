"""
util_install_drivers.py — Install Drivers (UsbDk + Vendor Pack).

engines/drivers/ ke andar jo driver packages bundle hain (UsbDk
.msi, Samsung USB driver .exe, aur jo vendor pack aage rakha
jaye) un ki pehle poori inventory log hoti hai, phir Windows par
har package us ki qisam ke mutabiq install hota hai:

    .msi → msiexec /i <file> /qb /norestart
    .exe → seedha chalaya jata hai (vendor installers interactive
           hote hain — screen par un ke apne sawal ayenge)
    .inf → pnputil /add-driver <file> /install

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
    "name": "Install Drivers (UsbDk + Vendor Pack)",
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


def _scan_packages():
    """engines/drivers/** ke tamam .msi/.exe/.inf (Path list, sorted)."""
    base = ENGINES_DIR / "drivers"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*")
                  if p.is_file()
                  and p.suffix.lower() in _INSTALLABLE)


def _install_cmd(path):
    """Package ki qisam ke mutabiq install command (list)."""
    suffix = path.suffix.lower()
    if suffix == ".msi":
        return ["msiexec", "/i", str(path), "/qb", "/norestart"]
    if suffix == ".inf":
        return ["pnputil", "/add-driver", str(path), "/install"]
    # .exe — vendor installer interactive hota hai, plain chalao
    return [str(path)]


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
                "Official download links aur har vendor ki hidayat "
                "is file me hai: engines/drivers/README-DRIVERS.md "
                "(app ke folder se engines\\drivers\\"
                "README-DRIVERS.md). Wahan se sirf OFFICIAL sources "
                "se driver lo — MediaTek VCOM/Preloader, Qualcomm "
                "QDLoader 9008 aur SPRD/Unisoc drivers aksar vendor "
                "ke apne tools (SP Flash Tool / ResearchDownload) ke "
                "saath ate hain, kisi ajnabi driver site se mat lena.",
                "ERROR")
        return False

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
        if pkg.suffix.lower() == ".exe":
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
            "reboot ke baad hi asal me load hota hai.", "OK")
    return True
