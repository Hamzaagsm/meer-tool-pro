RPMB WRITE — INPUT FOLDER
=========================

'RPMB Write (DA)' op yahan se file parhta hai.

Qawaid:
- Is folder me SIRF AIK .bin file rakho — jo device ki RPMB me
  likhni hai. 0 files = op ruk jayega; 2 ya zyada = op ruk
  jayega (galat file khud kabhi nahi chuni jati).
- File ka size 256 bytes ka multiple hona chahiye (RPMB sector
  = 256 bytes). Aakhri na-mukammal hissa write nahi hota.
- Range (Start Sector / Sectors) app ke neeche wale PARAMS bar
  se di jati hai; Sectors khali ho to poori file likhi jati hai.

⚠️ KHATARNAK: RPMB authenticated / anti-rollback area hai.
Galat file = secure data mustaqil kharab ho sakta hai. Op
danger-gate (tasdeeq checkbox) ke baghair nahi chalta, aur
write se pehle maujooda data ka backup khud banata hai
(backups/ folder me) — backup na bane to write nahi hota.
