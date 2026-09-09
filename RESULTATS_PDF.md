# Les actes publies sont-ils exploitables ?

Genere le 2026-09-09T20:06:59+00:00 (UTC). Source : `data/pdf_sonde.csv`, une ligne par PDF, avec son URL exacte.


## Methode et seuils

On mesure les caracteres de texte reellement extractibles par page (`pdftotext`). Une page de deliberation dactylographiee en contient couramment plus de 1500 ; une page scannee sans couche texte en rend zero.


- `scan_sans_texte` : 0 caractere par page — inexploitable sans OCR
- `texte_marginal` : moins de 100 — sans doute un scan avec un en-tete texte
- `texte_partiel` : de 100 a 400
- `texte_exploitable` : plus de 400


## Denominateur

72 documents ont ete tentes, **61 ont pu etre reellement mesures**. Tous les taux ci-dessous portent sur ces 61-la.


Les autres n'ont pas ete mesures, et les compter comme depourvus de texte fausserait le resultat :


| Motif d'ecart | Nombre |
|---|---:|
| `robots_interdit` | 6 |
| `telechargement_echoue` | 4 |
| `fichier_trop_petit` | 1 |


## Resultat


### Tous documents trouves sur les pages d'actes — 61 documents

| Classe | Nombre | Part |
|---|---:|---:|
| `scan_sans_texte` | 26 | 43 % |
| `texte_marginal` | 1 | 2 % |
| `texte_partiel` | 14 | 23 % |
| `texte_exploitable` | 20 | 33 % |

- Couche texte franche (plus de 400 car./page) : **20 sur 61, soit 33 %**
- Texte au moins partiel (plus de 100 car./page) : **34 sur 61, soit 56 %**
- A passer en OCR : **27 sur 61, soit 44 %**


### Documents dont le nom indique une deliberation ou un PV — 21 documents

| Classe | Nombre | Part |
|---|---:|---:|
| `scan_sans_texte` | 13 | 62 % |
| `texte_marginal` | 1 | 5 % |
| `texte_partiel` | 3 | 14 % |
| `texte_exploitable` | 4 | 19 % |

- Couche texte franche (plus de 400 car./page) : **4 sur 21, soit 19 %**
- Texte au moins partiel (plus de 100 car./page) : **7 sur 21, soit 33 %**
- A passer en OCR : **14 sur 21, soit 67 %**


### Autres pieces (affiches, avis, bulletins) — 40 documents

| Classe | Nombre | Part |
|---|---:|---:|
| `scan_sans_texte` | 13 | 32 % |
| `texte_partiel` | 11 | 28 % |
| `texte_exploitable` | 16 | 40 % |

- Couche texte franche (plus de 400 car./page) : **16 sur 40, soit 40 %**
- Texte au moins partiel (plus de 100 car./page) : **27 sur 40, soit 68 %**
- A passer en OCR : **13 sur 40, soit 32 %**

Le chiffre qui compte est celui du deuxieme tableau. Le premier melange des deliberations et des affiches communales, qui n'ont aucune raison d'avoir le meme taux de numerisation.


## Charge de calcul si OCR

Pages par document : mediane 6, de 1 a 76. Poids median 835 Ko.


Dans cet echantillon, les 26 documents a OCRiser totalisent 232 pages, avec une mediane de 2 pages par document. Des documents courts : l'OCR y est une depense modeste, pas un mur.


## Lecture

Ce chiffre decide de la suite. Au-dessus des deux tiers de texte, le corpus est de la donnee et s'indexe directement. En dessous d'un tiers, c'est un corpus d'images et il faut une chaine OCR, ce qui change la nature comme le cout du projet. Entre les deux, il faut trancher document par document — et le dire, plutot que d'arrondir vers le resultat qui arrange.

