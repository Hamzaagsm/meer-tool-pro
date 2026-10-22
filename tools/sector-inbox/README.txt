RAW SECTOR WRITE — INPUT FOLDER
===============================

'Raw Sector Write (EDL ws)' op yahan se file parhta hai.

Qawaid:
- Is folder me SIRF AIK .bin file rakho — jo sectors me
  likhni hai. 0 files = op ruk jayega; 2 ya zyada = op ruk
  jayega (galat file khud kabhi nahi chuni jati).
- Likhai ki jagah app ke neeche wale PARAMS bar se ati hai:
  LUN + Start Sector (+ Sector Size agar maloom ho: UFS par
  aksar 4096, eMMC par 512; khali = auto).
- File jitni bari hai, shuru wale sector se utne hi sectors
  aage tak likha jata hai.

⚠️ KHATARNAK: raw sector write galat jagah par ho to GPT /
boot / modem mustaqil kharab ho sakta hai. Op danger-gate
(tasdeeq checkbox) ke baghair nahi chalta, aur write se
pehle usi range ka backup khud banata hai (backups/ folder
me) — backup na bane to write nahi hota. Loader (firehose)
bhi lazmi hai.
