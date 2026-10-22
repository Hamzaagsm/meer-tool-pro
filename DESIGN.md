# MEER TOOL PRO — Design Document

**Maqsad:** Fenix Tool Pro / UnlockTool / AMT / DFT Pro jaisa professional servicing tool —
phone lagao → tool khud device pehchane → operation select karo → **screen par live log +
progress ke saath kaam CHALTA NAZAR aye** → asal me execute ho → SUCCESS / FAIL saaf mile.

**Purane GSM Tool (v8.8) se farq:** purana tool dusre tools ka *launcher* + guide tha
(buttons dabane se dusre programs khulte thay ya sirf hidayat milti thi). Ye tool
**khud kaam karega** — har operation aik asal open-source engine ko chalayega, us ki
output live console me stream hogi, aur natija asal hoga. **Nakli success kabhi nahi.**

---

## 1. UI Layout (UnlockTool / Fenix style)

```
┌────────────────────────────────────────────────────────────────────┐
│  MEER TOOL PRO  v1.0            [⚙ Settings]  [▶ DEMO MODE]       │
├────────────────────────────────────────────────────────────────────┤
│  DEVICE PANEL (auto-detect, hamesha upar)                          │
│  Status: ● CONNECTED      Port: COM7 (MediaTek BROM)               │
│  Brand: Infinix   Model: X6887 (HOT 50 Pro+)   Chip: MT6789 Helio G99│
│  Serial: KX8...   Mode: BROM   Android: 14   Security Patch: 2025-01│
├──────────────┬─────────────────────────────────────────────────────┤
│ OPERATIONS   │  LIVE LOG CONSOLE (bara, darmiyan)                  │
│              │  [12:01:03] ▶ Operation started: MTK FRP Erase      │
│ ▸ MTK        │  [12:01:04] Waiting for device... COM7 found        │
│   • Read Info│  [12:01:05] DA sent... handshake OK                 │
│   • FRP Erase│  [12:01:09] Erasing FRP partition... done           │
│   • Reset    │  [12:01:10] ✔ SUCCESS — Operation completed         │
│   • Flash    │                                                     │
│ ▸ Qualcomm   │  (rang: safed=info, hara=OK, peela=warning,         │
│ ▸ Samsung    │   laal=error, neela=engine ki apni output)          │
│ ▸ ADB/Fastboot│                                                    │
│ ▸ SPD/Unisoc │                                                     │
├──────────────┴─────────────────────────────────────────────────────┤
│  Progress: [████████████░░░░░░] 62%   [ START ]  [ STOP ]  [Clear] │
└────────────────────────────────────────────────────────────────────┘
```

Usool:
- **Device panel hamesha upar** — phone lagte hi 2 second ke andar khud bhar jaye
  (ADB se, Fastboot se, ya COM port scan se BROM/EDL/SPD detect karke).
- **Operations tree bayein** — category ke hisaab se (MTK / Qualcomm / Samsung /
  ADB-Fastboot / SPD-Unisoc). Har operation par saaf tag: koi tag nahi = asal engine
  se chalega; **`SERVER REQUIRED`** tag = paid server ke baghair mumkin nahi (neeche
  matrix dekho) — aisi operation par **fake button nahi** hoga, sirf tag + wajah.
- **Live log console sab se bara hisa** — engine ki asal output line-by-line,
  timestamp ke saath, rang-biranga status. Yehi wo cheez hai jo "kaam nazar ata hai".
- **Progress bar + START / STOP** neeche — operation ke doran progress bharta hai,
  STOP asal me process ko rokta hai.
- **DEMO MODE** — baghair phone ke poora nakli session (detect → info → FRP)
  bilkul asal jaisa log + progress ke saath, taake UI aur flow har waqt test ho sake.

---

## 2. Engine Plan (asal execution kahan se ayega)

| Engine | Source | Integration tareeqa | Halat |
|---|---|---|---|
| **MTKClient** | Open source (bkerler/mtkclient, GPL) | `tools/mtkclient/` me vendored copy ya system `mtk` command; har MTK operation = `mtk <cmd>` subprocess, output live stream | v1 core |
| **Qualcomm EDL** | Open source `edl` client (bkerler) | subprocess; **firehose loader user-supplied** — `loaders/qualcomm/<brand>/` folder me Hamza apne loaders rakhega. Loader na ho to operation shuru hi nahi hoga, log me saaf wajah ayegi | v1 (loader-gated) |
| **ADB / Fastboot** | Google platform-tools (free) | `tools/platform-tools/` me bundled `adb.exe` / `fastboot.exe`; subprocess | v1 core |
| **Samsung** | ADB + open methods | ADB ops universal; Download-mode flashing = Heimdall (open source) — mahdood support; baaki Samsung khaas ops matrix me dekho | v1 partial |
| **SPD / Unisoc** | Open methods (`spd_dump` waghera, experimental) | subprocess; v1 me sirf detect + info; flashing experimental tag ke saath baad me | v1 detect/info only |
| **COM/USB detect** | Windows port enumeration + VID/PID table | pyserial mojood ho to us se, na ho to Windows registry/`wmic` fallback — degrade graceful, crash kabhi nahi | v1 core |

**VID/PID pehchan (auto-detect):**
- `0E8D:0003` → MediaTek BROM · `0E8D:2000/2001` → MTK Preloader
- `05C6:9008` → Qualcomm EDL (9008) · `05C6:900E` → Qualcomm Diag
- `1782:4D00` → Spreadtrum/Unisoc Diag
- ADB/Fastboot → `adb devices` / `fastboot devices` polling

Har engine call **runner** ke through jayegi: subprocess ki stdout/stderr
line-by-line log console me, progress parser (engine output ke patterns se %),
STOP = process terminate, timeout = saaf error. Operation = aik chhoti plugin file
(`src/ops/*.py`) — naya operation jorna = aik file jorna, main app nahi cherna.

---

## 3. Capability Matrix (IMAANDARI SE — pakki)

### ✅ Asal me chalega (free open-source engines se)
| Operation | Engine | Note |
|---|---|---|
| Device detect + info (ADB/Fastboot/BROM/EDL) | apna watcher | teeno modes |
| ADB: info, reboot, reboot bootloader/recovery | platform-tools | universal |
| Fastboot: info (getvar), reboot, stock image flash (unlocked bootloader par) | platform-tools | universal |
| MTK: Read info / GPT | MTKClient | BROM access wale chipsets |
| MTK: FRP erase | MTKClient | FRP partition erase — supported SoC par |
| MTK: Factory reset (userdata/cache erase) | MTKClient | supported SoC par |
| MTK: Stock firmware flash (read/write partitions) | MTKClient | scatter firmware ke saath |
| MTK: Bootloader unlock | MTKClient | sirf jin SoC par MTKClient support karta hai |
| Qualcomm: EDL read/write/FRP | edl client | **sirf tab jab us device ka firehose loader Hamza ke paas ho** |

### ⚠️ Partial / loader-gated
| Operation | Wajah |
|---|---|
| Qualcomm EDL tamam ops | Engine free hai, lekin har device ka **firehose programmer (.elf/.mbn)** chahiye — ye files brand-signed hoti hain, bundle nahi ki ja sakti; Hamza apne loaders dega to chalengi |
| Samsung stock flash (Download mode) | Heimdall mahdood models par; Odin proprietary hai |
| SPD/Unisoc flash | Open tools experimental hain — v1 me nahi, detect/info sirf |

### 🔒 SERVER REQUIRED (free me mumkin NAHI — UI me saaf tag, fake button nahi)
| Operation | Wajah |
|---|---|
| Naye MTK chipsets (Dimensity series, Helio G99+ ke locked BROM) ka SLA/DAA auth bypass | Server-signed DA/auth file lagti hai — Fenix/UnlockTool bhi is ke liye apne paid server se sign karwate hain |
| Vivo/Oppo/Realme/Xiaomi auth flashing (EDL/BROM) | Brand ke authorized server account ke baghair auth nahi milta |
| Samsung latest FRP (server/Knox methods) | Server verification par mabni |
| Carrier/network unlock (aksar models) | Server credits par chalta hai |
| Xiaomi Mi account / EDL authorized ops | Authorized account lazmi |

**IMEI usool (Hamza ka apna pakka rule):** sirf **original IMEI restore**
(box/sticker wala asal number wapas likhna) — IMEI change/clone kabhi nahi.

Ye matrix is liye doc me pakki hai taake kal ko koi ye na kahe ke tool ne wo wada
kiya jo free me mumkin hi nahi tha. Jo chalega, wo asal chalega; jo nahi chal sakta,
wo pehle din se saaf likha milega.

---

## 4. v1 Module List (pehla working release)

1. **App shell** — dark professional UI: device panel, ops tree, live log, progress, START/STOP.
2. **Device Watch** — ADB + Fastboot polling + COM scan (BROM/EDL/SPD), auto info-fill.
3. **Runner** — plugin operations, live streaming, progress, stop, timeout, honest FAIL.
4. **MTK basics (MTKClient)** — Read Info/GPT, FRP Erase, Factory Reset, (Flash agle step me).
5. **ADB/Fastboot universal ops** — Info, Reboot (normal/bootloader/recovery), Fastboot getvar info.
6. **Qualcomm EDL engine slot** — engine jura hua, loader folder ka intezaar; loader na ho to saaf log.
7. **DEMO MODE** — nakli device session, poora flow baghair phone ke.
8. **One-click run** — `run.bat` (Python check ke saath); aage PyInstaller EXE (one-folder, koi setup nahi).

## 5. Aage ki zaruraten (Hamza se — jab wo dega tab ye hisay khulenge)
- Us ke paas mojood **firehose loaders** (Qualcomm) aur **MTK DA files** jo us ne khud
  jama kiye hain — `loaders/` folder me dalne ke liye.
- **Test phones par reports** — kaunsa model, kaunsa operation, log ki screenshot:
  yehi asal verification hai (purana usool: phone par sabit hue baghair "fixed" nahi).
- Fenix Tool Pro ke **UI screenshots** (agar wo de) — layout ko aur qareeb karne ke liye.
