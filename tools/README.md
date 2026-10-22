# tools/ — user ki cheezen (loaders, firmware, backups)

Asal engines ab `engines/` folder me hain (app ke barabar) — MTKClient,
edl client, platform-tools wahan dekho (`engines/README.md`).

`tools/` me wo cheezen rehti hain jo **tumhari apni** hain aur package me
pehle se bundle nahi ho sakti theen:

- `loaders/qualcomm/<brand>/` — tumhare apne firehose loaders (.elf/.mbn)
  EDL operations inhin par chalengi; koi loader bundle NAHI kiya gaya
  (brand-signed files hoti hain).
- `loaders/mtk/` — tumhara apna MTK DA file (.bin). **Sirf aik** rakho —
  tool use khud MTK operations me `--loader` ke tor par laga dega.
- `firmware/` — MTK scatter firmware (scatter .txt + tamam .img/.bin)
  "Flash Firmware (Scatter)" operation ke liye.
- `firmware-qc/` — Qualcomm QFIL firmware (rawprogram*.xml + patch*.xml
  + tamam .img) "EDL Flash (QFIL)" operation ke liye.
- `spd/` — Spreadtrum/Unisoc ke official Upgrade Download /
  Research Download tools ki .exe copies (launcher wahan se kholta hai),
  aur stock .pac files FRP.pac wale kaam ke liye.
- `mdm-backups/<model>/` — MDM backup library: Proinfo Backup operation
  yahan har model ke backups rakhta hai. Ye library tumhare apne counter
  tajurbe se bharti hai — kisi model ka patch pehle se andar NAHI hai.

Jo cheez na ho, us ki operation log me saaf "setup required" deti hai —
crash kabhi nahi, nakli success kabhi nahi.
