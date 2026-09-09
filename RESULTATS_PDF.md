# Les actes publies sont-ils exploitables ?

Genere le 2026-09-09T19:43:20+00:00 (UTC). Source : `data/pdf_sonde.csv`, une ligne par PDF, avec son URL exacte.


## Methode et seuils

On mesure les caracteres de texte reellement extractibles par page (`pdftotext`). Une page de deliberation dactylographiee en contient couramment plus de 1500 ; une page scannee sans couche texte en rend zero.


- `scan_sans_texte` : 0 caractere par page — inexploitable sans OCR
- `texte_marginal` : moins de 100 — sans doute un scan avec un en-tete texte
- `texte_partiel` : de 100 a 400
- `texte_exploitable` : plus de 400


## Resultat

| Classe | Nombre | Part |
|---|---:|---:|
| `scan_sans_texte` | 26 | 36 % |
| `texte_exploitable` | 20 | 28 % |
| `texte_partiel` | 14 | 19 % |
| `robots_interdit` | 6 | 8 % |
| `telechargement_echoue` | 4 | 6 % |
| `fichier_trop_petit` | 1 | 1 % |
| `texte_marginal` | 1 | 1 % |

**34 PDF sur 72 (47 %) portent une couche texte utilisable sans OCR.**


Pages par document : mediane 6, de 1 a 76. Poids median : 835 Ko.


## Lecture

Ce chiffre decide de la suite. Au-dessus des deux tiers, le corpus est de la donnee et peut etre indexe directement. En dessous d'un tiers, c'est un corpus d'images : il faudrait une chaine OCR, ce qui change la nature et le cout du projet, et cela devrait etre dit sans arrondir.

