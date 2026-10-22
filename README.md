# MEER TOOL PRO

Professional mobile servicing tool — Fenix Tool Pro / UnlockTool style:
phone lagao → tool khud device pehchane → operation live log + progress
ke saath **asal me execute** ho. Launcher nahi, nakli success nahi.

- Design + imaandar capability matrix: [DESIGN.md](DESIGN.md)
- Chalana (Windows): `run.bat` do-click karo (Python check ke saath)
- Engines ke liye: [tools/README.md](tools/README.md)
- DEMO MODE: baghair phone ke poora nakli session (Detect → Info → FRP)
  UI ke andar button se — har log line par [DEMO] tag hota hai.

## Saakht
```
src/main.py            app (dark professional UI)
src/core/device_watch.py  ADB/Fastboot polling + COM scan (BROM/EDL/SPD)
src/core/runner.py     operation runner: live stream, progress, STOP, honest FAIL
src/ops/               operation plugins (naya op = aik nayi file)
src/demo.py            demo session simulation
tools/                 engines (platform-tools, MTKClient, user loaders)
```
