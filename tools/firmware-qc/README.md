# tools/firmware-qc/ — Qualcomm QFIL firmware yahan rakho

Qualcomm "EDL Flash (QFIL rawprogram)" operation yahan se firmware
parhti hai: firmware ke tamam files yahan rakho — rawprogram*.xml,
patch*.xml (aam tor par patch0.xml) aur tamam .img files.

Saath me us model ka firehose loader tools/loaders/qualcomm/<brand>/
me hona bhi lazmi hai. Ghalat firmware = hard brick ka khatra —
pehle "EDL Full Backup" se backup lo.
