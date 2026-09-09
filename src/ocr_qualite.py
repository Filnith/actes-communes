#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_qualite.py — l'OCR est-il assez bon pour qu'on ait le droit de s'en servir ?

La question n'est plus "peut-on lire un scan" — on peut. Elle est : ce qu'on
lit est-il fiable. Une archive de deliberations ou les montants sont faux
serait pire que pas d'archive du tout, parce qu'elle aurait l'air serieuse.

Trois mesures independantes, plus une lecture humaine :

  1. La confiance que Tesseract s'accorde a lui-meme, mot par mot.
  2. La validite lexicale : quelle part des mots produits existe vraiment dans
     un dictionnaire francais. Un OCR qui derape fabrique des mots inexistants.
  3. Les marqueurs de structure : une deliberation contient forcement
     "conseil municipal", "seance", "presents", "ordre du jour". S'ils
     n'apparaissent pas, la reconnaissance a echoue meme si les chiffres de
     confiance sont flatteurs.

Et un temoin de comparaison : les memes mesures appliquees aux documents qui
ont deja une couche texte native. Sans ce temoin, un score de validite
lexicale ne veut rien dire — on ne sait pas a quoi le comparer.

Les seuils de verdict sont fixes AVANT de connaitre les resultats, et ecrits
dans le fichier de sortie. C'est ce qui empeche d'arrondir dans le sens qui
arrange.
"""

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
import urllib.request
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from echantillon import robots_autorise, sans_accents, UA, DATA, RACINE, DELAI

MAX_DOCS = int(os.environ.get("CONSTAT_OCR_DOCS", "25"))
MAX_TEMOINS = int(os.environ.get("CONSTAT_OCR_TEMOINS", "10"))
PAGES_MAX = int(os.environ.get("CONSTAT_OCR_PAGES", "4"))
DPI = 300
MAX_OCTETS = 25 * 1024 * 1024

# Seuils de verdict, fixes d'avance.
S_BONNE = {"confiance": 80.0, "lexique": 0.85, "marqueurs": 4}
S_MOYENNE = {"confiance": 65.0, "lexique": 0.70, "marqueurs": 2}

MARQUEURS = ("conseil municipal", "deliberation", "seance", "presents",
             "convocation", "ordre du jour", "le maire", "abstention",
             "unanimite", "commune de", "l'an deux mille", "excuses",
             "secretaire de seance", "pouvoir", "vote", "adopte")

DIAG = {"demarre_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seuils": {"bonne": S_BONNE, "moyenne": S_MOYENNE, "dpi": DPI,
                   "pages_par_document": PAGES_MAX},
        "etapes": [], "echec": None}


def note(e, **d):
    DIAG["etapes"].append(dict(etape=e, **d))
    print("  . " + e + " : " + ", ".join(f"{k}={v}" for k, v in d.items()),
          flush=True)


def charger_lexique():
    for p in ("/usr/share/dict/french", "/usr/share/dict/fr",
              "/usr/share/hunspell/fr_FR.dic"):
        if os.path.exists(p):
            mots = set()
            with open(p, encoding="utf-8", errors="replace") as f:
                for l in f:
                    m = l.split("/")[0].strip().lower()
                    if m:
                        mots.add(m)
                        mots.add(sans_accents(m))
            note("lexique", source=p, mots=len(mots))
            return mots
    note("lexique", source="absent")
    return set()


LEXIQUE = set()
MOT = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def validite_lexicale(texte):
    if not LEXIQUE:
        return None, 0
    mots = MOT.findall(texte)
    if not mots:
        return 0.0, 0
    bons = sum(1 for m in mots
               if m.lower() in LEXIQUE or sans_accents(m) in LEXIQUE)
    return round(bons / len(mots), 3), len(mots)


def marqueurs_presents(texte):
    b = sans_accents(texte)
    return [m for m in MARQUEURS if m in b]


def telecharger_pdf(url, chemin):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    time.sleep(DELAI)
    with urllib.request.urlopen(req, timeout=90) as r, open(chemin, "wb") as f:
        lu = 0
        while lu < MAX_OCTETS:
            b = r.read(1 << 18)
            if not b:
                break
            f.write(b)
            lu += len(b)
    return lu


def pages_du_pdf(chemin):
    try:
        out = subprocess.run(["pdfinfo", chemin], capture_output=True,
                             timeout=40, text=True).stdout
        for l in out.splitlines():
            if l.startswith("Pages:"):
                return int(l.split(":", 1)[1].strip())
    except Exception:
        pass
    return None


def texte_natif(chemin):
    try:
        r = subprocess.run(["pdftotext", "-q", chemin, "-"],
                           capture_output=True, timeout=90)
        return r.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def ocriser(chemin, dossier, pages):
    """Rend les pages en images puis les passe a Tesseract.
    Renvoie (texte, confiance_moyenne, nombre_de_mots)."""
    base = os.path.join(dossier, "p")
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", "-f", "1",
                    "-l", str(pages), chemin, base],
                   capture_output=True, timeout=300)
    images = sorted(f for f in os.listdir(dossier) if f.endswith(".png"))
    textes, confs = [], []
    for img in images[:pages]:
        r = subprocess.run(["tesseract", os.path.join(dossier, img), "stdout",
                            "-l", "fra", "--psm", "1", "tsv"],
                           capture_output=True, timeout=180)
        lignes = r.stdout.decode("utf-8", "replace").splitlines()
        if not lignes:
            continue
        entetes = lignes[0].split("\t")
        try:
            i_conf, i_txt = entetes.index("conf"), entetes.index("text")
        except ValueError:
            continue
        for l in lignes[1:]:
            ch = l.split("\t")
            if len(ch) <= i_txt:
                continue
            mot = ch[i_txt].strip()
            try:
                c = float(ch[i_conf])
            except ValueError:
                continue
            if mot and c >= 0:
                textes.append(mot)
                confs.append(c)
    texte = " ".join(textes)
    conf = round(sum(confs) / len(confs), 1) if confs else 0.0
    return texte, conf, len(confs)


def verdict(conf, lex, nb_marq):
    lex = 0.0 if lex is None else lex
    if conf >= S_BONNE["confiance"] and lex >= S_BONNE["lexique"] \
            and nb_marq >= S_BONNE["marqueurs"]:
        return "bonne"
    if conf >= S_MOYENNE["confiance"] and lex >= S_MOYENNE["lexique"] \
            and nb_marq >= S_MOYENNE["marqueurs"]:
        return "moyenne"
    return "mauvaise"


def traiter(url, meta, extraits):
    f = dict(meta)
    f.update(url=url, octets=0, pages=None, source_texte=None, confiance=None,
             validite_lexicale=None, mots=0, marqueurs=0, verdict="non_teste",
             erreur=None)
    if not robots_autorise(url):
        f["verdict"] = "robots_interdit"
        return f
    dossier = tempfile.mkdtemp()
    chemin = os.path.join(dossier, "doc.pdf")
    try:
        f["octets"] = telecharger_pdf(url, chemin)
        if f["octets"] < 1000:
            f["verdict"] = "fichier_trop_petit"
            return f
        f["pages"] = pages_du_pdf(chemin)
        if not f["pages"]:
            f["verdict"] = "pdf_illisible"
            return f
        natif = texte_natif(chemin)
        car_page = len("".join(natif.split())) / f["pages"]

        if car_page >= 100:
            f["source_texte"] = "natif"
            texte = natif
            f["confiance"] = None
        else:
            f["source_texte"] = "ocr"
            texte, conf, nb = ocriser(chemin, dossier, min(PAGES_MAX, f["pages"]))
            f["confiance"] = conf

        lex, nmots = validite_lexicale(texte)
        f["validite_lexicale"], f["mots"] = lex, nmots
        marq = marqueurs_presents(texte)
        f["marqueurs"] = len(marq)

        if f["source_texte"] == "natif":
            f["verdict"] = "temoin_texte_natif"
        else:
            f["verdict"] = verdict(f["confiance"], lex, len(marq))

        if len(extraits) < 6 and f["source_texte"] == "ocr" and texte.strip():
            extraits.append(
                f"\n{'='*78}\n{meta.get('commune')} ({meta.get('population')} hab.)"
                f"  —  verdict : {f['verdict']}\n{url}\n"
                f"confiance {f['confiance']} | lexique {lex} | "
                f"marqueurs {len(marq)} : {', '.join(marq[:8])}\n{'-'*78}\n"
                + texte[:2500])
    except Exception as e:
        f["erreur"] = type(e).__name__ + ": " + str(e)[:120]
        f["verdict"] = "echec"
    finally:
        for n in os.listdir(dossier):
            try:
                os.unlink(os.path.join(dossier, n))
            except Exception:
                pass
        try:
            os.rmdir(dossier)
        except Exception:
            pass
    return f


def travail():
    global LEXIQUE
    for o in ("pdfinfo", "pdftotext", "pdftoppm", "tesseract"):
        if subprocess.run(["which", o], capture_output=True).returncode:
            raise RuntimeError(f"{o} absent")
    note("outils", tous="presents")
    LEXIQUE = charger_lexique()

    src = os.path.join(DATA, "deliberations.csv")
    if not os.path.exists(src):
        raise RuntimeError("data/deliberations.csv absent : lancer la moisson")
    docs = list(csv.DictReader(open(src, encoding="utf-8")))
    note("documents_disponibles", nombre=len(docs))

    # Un document par commune au maximum : on mesure la variete des pratiques
    # de numerisation, pas la qualite du scanner d'une seule mairie.
    vues, retenus = set(), []
    for d in docs:
        if d["code_insee"] in vues:
            continue
        vues.add(d["code_insee"])
        retenus.append(d)
        if len(retenus) >= MAX_DOCS + MAX_TEMOINS:
            break
    note("documents_retenus", nombre=len(retenus), communes=len(vues))

    fiches, extraits = [], []
    n_ocr = n_temoin = 0
    for i, d in enumerate(retenus, 1):
        meta = {k: d.get(k) for k in ("commune", "code_insee", "population",
                                      "departement", "indice_nom",
                                      "indice_texte_lien", "profondeur")}
        f = traiter(d["url"], meta, extraits)
        if f["source_texte"] == "ocr":
            n_ocr += 1
        elif f["source_texte"] == "natif":
            n_temoin += 1
        fiches.append(f)
        print(f"     [{i:>3}/{len(retenus)}] {str(d['commune'])[:22]:<22} "
              f"{str(f['source_texte'] or '-'):<6} conf={f['confiance']} "
              f"lex={f['validite_lexicale']} marq={f['marqueurs']:>2}  "
              f"{f['verdict']}", flush=True)
        if n_ocr >= MAX_DOCS and n_temoin >= MAX_TEMOINS:
            break

    with open(os.path.join(DATA, "ocr_qualite.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fiches[0].keys()))
        w.writeheader()
        w.writerows(fiches)
    with open(os.path.join(DATA, "ocr_extraits.txt"), "w", encoding="utf-8") as fh:
        fh.write("Extraits bruts de sortie OCR, pour lecture humaine.\n"
                 "Aucun chiffre ne remplace le fait de lire ce que la machine "
                 "a reellement produit.\n" + "\n".join(extraits))
    note("fiches", nombre=len(fiches), ocr=n_ocr, temoins=n_temoin)
    ecrire_resultats(fiches)


def ecrire_resultats(fiches):
    L = []
    L.append("# L'OCR est-il assez bon ?\n")
    L.append(f"Genere le {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
             f"(UTC). Source : `data/ocr_qualite.csv`. Sortie brute lisible dans "
             f"`data/ocr_extraits.txt`.\n")

    L.append("\n## Seuils, fixes avant de connaitre les resultats\n")
    L.append(f"- **bonne** : confiance Tesseract >= {S_BONNE['confiance']}, "
             f"validite lexicale >= {S_BONNE['lexique']}, "
             f"au moins {S_BONNE['marqueurs']} marqueurs de deliberation")
    L.append(f"- **moyenne** : >= {S_MOYENNE['confiance']}, "
             f">= {S_MOYENNE['lexique']}, >= {S_MOYENNE['marqueurs']} marqueurs")
    L.append("- **mauvaise** : tout le reste\n")
    L.append("Les trois criteres doivent tenir ensemble. Une confiance flatteuse "
             "avec zero marqueur signifie que la machine a lu quelque chose avec "
             "assurance, mais pas une deliberation.\n")

    ocr = [f for f in fiches if f["source_texte"] == "ocr"]
    tem = [f for f in fiches if f["source_texte"] == "natif"]

    if tem:
        lx = [f["validite_lexicale"] for f in tem if f["validite_lexicale"] is not None]
        mq = [f["marqueurs"] for f in tem]
        L.append("\n## Temoin : les documents deja en texte natif\n")
        L.append(f"{len(tem)} documents. Validite lexicale mediane "
                 f"**{sorted(lx)[len(lx)//2] if lx else '?'}**, "
                 f"marqueurs medians **{sorted(mq)[len(mq)//2] if mq else '?'}**.\n")
        L.append("C'est le plafond atteignable. Un OCR ne peut pas faire mieux "
                 "que le texte natif du meme corpus : sans ce point de "
                 "comparaison, les chiffres ci-dessous ne voudraient rien dire.\n")

    L.append("\n## Resultat sur les documents scannes\n")
    if not ocr:
        L.append("Aucun document scanne dans ce lot.\n")
    else:
        n = len(ocr)
        c = Counter(f["verdict"] for f in ocr)
        L.append(f"{n} documents passes a l'OCR.\n")
        L.append("\n| Verdict | Nombre | Part |")
        L.append("|---|---:|---:|")
        for k, v in c.most_common():
            L.append(f"| `{k}` | {v} | {100*v/n:.0f} % |")
        conf = sorted(f["confiance"] for f in ocr if f["confiance"] is not None)
        lx = sorted(f["validite_lexicale"] for f in ocr
                    if f["validite_lexicale"] is not None)
        mq = sorted(f["marqueurs"] for f in ocr)
        if conf:
            L.append(f"\n- Confiance Tesseract : mediane **{conf[len(conf)//2]}**, "
                     f"de {conf[0]} a {conf[-1]}")
        if lx:
            L.append(f"- Validite lexicale : mediane **{lx[len(lx)//2]}**, "
                     f"de {lx[0]} a {lx[-1]}")
        if mq:
            L.append(f"- Marqueurs de deliberation : mediane **{mq[len(mq)//2]}** "
                     f"sur {len(MARQUEURS)} cherches\n")
        bonnes = c["bonne"] + c["moyenne"]
        L.append(f"\n**{bonnes} sur {n} ({100*bonnes/n:.0f} %) sont au moins "
                 f"moyennes**, donc utilisables pour de la recherche plein "
                 f"texte.\n")

    L.append("\n## Ce que ces chiffres ne disent pas\n")
    L.append("La validite lexicale mesure si les mots existent, pas si ce sont "
             "les bons. Une date ou un montant mal lus restent invisibles a ce "
             "test : `12 000` devenu `72 000` est parfaitement lexical. Pour un "
             "corpus dont l'interet porte largement sur des sommes et des dates, "
             "c'est la limite serieuse de cette mesure, et elle appelle une "
             "verification humaine sur echantillon avant toute publication.\n")

    with open(os.path.join(RACINE, "RESULTATS_OCR.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    code = 0
    try:
        travail()
    except Exception as e:
        DIAG["echec"] = {"type": type(e).__name__, "message": str(e)[:500],
                         "trace": traceback.format_exc()[-2000:]}
        print("\nECHEC :", type(e).__name__, str(e)[:300], file=sys.stderr)
        code = 1
    finally:
        os.makedirs(DATA, exist_ok=True)
        DIAG["fini_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(os.path.join(DATA, "ocr_diagnostic.json"), "w",
                  encoding="utf-8") as f:
            json.dump(DIAG, f, ensure_ascii=False, indent=1)
        print("\ndata/ocr_diagnostic.json ecrit.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
