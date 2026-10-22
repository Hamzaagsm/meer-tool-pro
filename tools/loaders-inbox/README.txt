LOADERS INBOX — naye loaders yahan rakho, phir app me
"Utility → Loaders Library Import" op chalao.

Kya rakh sakte ho:
  - aik folder (andar .bin / .elf / .mbn loader files)
  - seedhi loose loader files (.bin / .elf / .mbn)
  - aik .zip (masalan kisi site se download kiya hua pack)

Import har file ko parakh-ta hai:
  - SHA-256 library index se mile to file verified jagah par jati hai
  - warna magic bytes se MTK DA / Qualcomm firehose pehchana jata hai
    aur file brand folder me ja kar local index me darj ho jati hai
  - pehchan na aye to file import NAHI hoti (log me wajah ayegi)

Import kabhi kuch delete nahi karta aur mojooda file overwrite
nahi karta.
