# L'OCR est-il assez bon ?

Genere le 2026-09-09T20:45:58+00:00 (UTC). Source : `data/ocr_qualite.csv`. Sortie brute lisible dans `data/ocr_extraits.txt`.


## Seuils, fixes avant de connaitre les resultats

- **bonne** : confiance Tesseract >= 80.0, validite lexicale >= 0.85, au moins 4 marqueurs de deliberation
- **moyenne** : >= 65.0, >= 0.7, >= 2 marqueurs
- **mauvaise** : tout le reste

Les trois criteres doivent tenir ensemble. Une confiance flatteuse avec zero marqueur signifie que la machine a lu quelque chose avec assurance, mais pas une deliberation.


## Temoin : les documents deja en texte natif

10 documents. Validite lexicale mediane **0.875**, marqueurs medians **4**.

C'est le plafond atteignable. Un OCR ne peut pas faire mieux que le texte natif du meme corpus : sans ce point de comparaison, les chiffres ci-dessous ne voudraient rien dire.


## Resultat sur les documents scannes

10 documents passes a l'OCR.


| Verdict | Nombre | Part |
|---|---:|---:|
| `moyenne` | 6 | 60 % |
| `bonne` | 4 | 40 % |

- Confiance Tesseract : mediane **91.3**, de 82.8 a 94.7
- Validite lexicale : mediane **0.887**, de 0.731 a 0.917
- Marqueurs de deliberation : mediane **7** sur 16 cherches


**10 sur 10 (100 %) sont au moins moyennes**, donc utilisables pour de la recherche plein texte.


## Ce que ces chiffres ne disent pas

La validite lexicale mesure si les mots existent, pas si ce sont les bons. Une date ou un montant mal lus restent invisibles a ce test : `12 000` devenu `72 000` est parfaitement lexical. Pour un corpus dont l'interet porte largement sur des sommes et des dates, c'est la limite serieuse de cette mesure, et elle appelle une verification humaine sur echantillon avant toute publication.

