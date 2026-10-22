# MEER TOOL PRO

Professional mobile servicing tool — Fenix Tool Pro / UnlockTool style:
phone lagao → tool khud device pehchane → operation live log + progress
ke saath **asal me execute** ho. Launcher nahi, nakli success nahi.

- Design + imaandar capability matrix: [DESIGN.md](DESIGN.md)
- Chalana (Windows): `run.bat` do-click karo (Python check ke saath)
- Engines ki tafseel: [engines/README.md](engines/README.md) ·
  user ki cheezen (loaders/firmware/backups): [tools/README.md](tools/README.md)
- DEMO MODE: baghair phone ke poora nakli session (Detect → Info → FRP)
  UI ke andar button se — har log line par [DEMO] tag hota hai.

## Operations (v1)

- **MTK** — Read Info/GPT, FRP Erase + Factory Reset, Full Backup,
  Scatter Flash, Bootloader Unlock/Relock + vbmeta (MTKClient engine)
- **MDM / Transsion** — Proinfo Backup/Restore (backup library),
  META Mode Guide, MDM Check (ADB), Security Plugin Remove, PayJoy Remove
- **Qualcomm** — EDL Loader Library, EDL Info/GPT, FRP, Factory Reset,
  Full Backup, QFIL Flash (edl engine + tumhare apne firehose loaders)
- **Samsung** — FRP Method Router (chipset/patch dekh kar sahi rasta),
  Firmware Download Helper
- **ADB / Fastboot** — Device Info, Reboot (Normal/Bootloader/Recovery),
  Fastboot Info + Reboot
- **SPD / Unisoc** — Official Tools Launcher, FRP.pac Guide
- Jo free me mumkin nahi (naye chipsets ka SLA/auth, latest Samsung FRP
  waghera) wo 🔒 SERVER REQUIRED tag ke saath saaf nazar ata hai —
  nakli button nahi.

## Saakht
```
src/main.py            app (dark professional UI)
src/core/device_watch.py  ADB/Fastboot polling + COM scan (BROM/EDL/SPD)
src/core/runner.py     operation runner: live stream, progress, STOP, honest FAIL
src/core/engines.py    engine resolution (engines/ folder, Python dhoondhna)
src/ops/               operation plugins (naya op = aik nayi file)
src/demo.py            demo session simulation
engines/               MTKClient + edl + platform-tools (EXE ke saath rehte hain)
tools/                 user ki cheezen: loaders, firmware, spd tools, mdm-backups
backups/               MTK/QC backup operations ki output (runtime par banti hai)
```
