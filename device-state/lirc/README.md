# Telecomando Meliconi Control TV+ / Grundig P 37-071

Il telecomando usa il codice apparecchio `1331`. Le funzioni nascoste seguenti non producono effetti sul televisore e sono dedicate a 240-MP:

| Tasto fisico | Funzione da assegnare con 0707 | Codice IR |
|---|---:|---:|
| GUIDE | 0110 | 0x117 |
| MENU | 0111 | 0x017 |
| BACK | 0112 | 0x1E7 |
| SU | 0113 | 0x0E7 |
| GIU | 0114 | 0x167 |
| SINISTRA | 0115 | 0x067 |
| DESTRA | 0116 | 0x1A7 |
| OK | 0000 | 0x1FF |

Volume, mute e accensione restano comandi del televisore e vengono scartati da `lircd-uinput`.
Il codice IR `0x000` e un separatore del protocollo, non un tasto, e deve rimanere non standard.
