#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_sonde.py — les actes publies sont-ils du texte, ou des images ?

C'est la contrainte bloquante suivante, et elle est plus severe que la
precedente. Un PDF scanne d'un registre manuscrit ne vaut rien sans OCR.
Un PDF avec couche texte vaut tout. Tant que cette proportion est inconnue,
on ne sait pas si ce corpus est de la donnee ou seulement des images.

Methode : repartir des communes ou l'echantillon precedent a trouve des PDF,
recuperer quelques PDF par commune, et mesurer la quantite de texte
reellement extractible par page. Le seuil retenu est explicite plus bas et
discutable — c'est pour ca qu'il est ecrit dans le fichier de sortie.

Meme conduite que l'echantillon : User-Agent identifiable, robots.txt
respecte, une requete a la fois, et un plafond de taille par fichier.
Meme regle aussi : ce script ecrit son diagnostic quoi qu'il arrive.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import traceback
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from echantillon import (get, ExtracteurLiens, robots_autorise,
                         UA, DATA, RACINE, DELAI)

MAX_PDF = int(os.environ.get("CONSTAT_MAX_PDF", "80"))
PAR_COMMUNE = int(os.environ.get("CONSTAT_PDF_PAR_COMMUNE", "3"))
MAX_OCTETS = 25 * 1024 * 1024

# Seuils de classement, en caracteres de texte extrait par page.
# Une page de deliberation dactylographiee en contient couramment plus de
# 1500. Une page scannee sans couche texte en rend zero. Entre les deux se
# trouvent les PDF ou seul un en-tete est du texte.
SEUIL_MARGINAL = 100
SEUIL_PARTIEL = 400

DIAG = {
    "demarre_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "seuils_caracteres_par_page": {"marginal": SEUIL_MARGINAL,
                                   "partiel": SEUIL_PARTIEL},
    "etapes": [], "echec": None,
}


def note(etape, **d):
    DIAG["etapes"].append(dict(etape=etape, **d))
    print("  . " + etape + " : " + ", ".join(f"{k}={v}" for k, v in d.items()),
          flush=True)


def outil(nom):
    return subprocess.run(["which", nom], capture_output=True).returncode == 0


def pdfs_de_la_page(url):
    if not robots_autorise(url):
        return [], "robots_interdit"
    st, final, html, err = get(url)
    if st != 200 or not html:
        return [], (err or f"HTTP {st}")
    p = ExtracteurLiens()
    try:
        p.feed(html)
    except Exception:
        pass
    out = []
    for href, _ in p.liens:
        if href and ".pdf" in href.lower():
            u = urllib.parse.urljoin(final, href)
            if u.startswith("http") and u not in out:
                out.append(u)
    return out, None


def analyser(url):
    """Telecharge un PDF et mesure le texte reellement extractible."""
    f = {"url": url, "octets": 0, "pages": None, "caracteres": 0,
         "car_par_page": 0.0, "classe": "non_teste", "erreur": None}
    if not robots_autorise(url):
        f["classe"] = "robots_interdit"
        return f
    chemin = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
            chemin = t.name
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        import time
        time.sleep(DELAI)
        with urllib.request.urlopen(req, timeout=90) as r, open(chemin, "wb") as fh:
            lu = 0
            while lu < MAX_OCTETS:
                buf = r.read(1 << 18)
                if not buf:
                    break
                fh.write(buf)
                lu += len(buf)
            f["octets"] = lu
        if f["octets"] < 1000:
            f["classe"] = "fichier_trop_petit"
            return f

        try:
            info = subprocess.run(["pdfinfo", chemin], capture_output=True,
                                  timeout=40, text=True).stdout
            for ligne in info.splitlines():
                if ligne.startswith("Pages:"):
                    f["pages"] = int(ligne.split(":", 1)[1].strip())
        except Exception as e:
            f["erreur"] = "pdfinfo: " + type(e).__name__

        try:
            res = subprocess.run(["pdftotext", "-q", chemin, "-"],
                                 capture_output=True, timeout=90)
            texte = res.stdout.decode("utf-8", "replace")
            f["caracteres"] = len("".join(texte.split()))
        except Exception as e:
            f["erreur"] = (f["erreur"] or "") + " pdftotext: " + type(e).__name__

        if not f["pages"]:
            f["classe"] = "pdf_illisible"
            return f
        f["car_par_page"] = round(f["caracteres"] / f["pages"], 1)
        c = f["car_par_page"]
        f["classe"] = ("scan_sans_texte" if c == 0 else
                       "texte_marginal" if c < SEUIL_MARGINAL else
                       "texte_partiel" if c < SEUIL_PARTIEL else
                       "texte_exploitable")
    except Exception as e:
        f["erreur"] = type(e).__name__ + ": " + str(e)[:120]
        f["classe"] = "telechargement_echoue"
    finally:
        if chemin and os.path.exists(chemin):
            os.unlink(chemin)
    return f


def travail():
    for o in ("pdfinfo", "pdftotext"):
        if not outil(o):
            raise RuntimeError(f"{o} absent : installer poppler-utils")
    note("outils", poppler="present")

    src = os.path.join(DATA, "echantillon.csv")
    if not os.path.exists(src):
        raise RuntimeError("data/echantillon.csv absent : lancer d'abord "
                           "le workflow Echantillon")
    lignes = list(csv.DictReader(open(src, encoding="utf-8")))
    cibles = [r for r in lignes
              if r.get("page_actes_url") and int(r.get("pdf_sur_page_actes") or 0) > 0]
    note("communes_avec_pdf", nombre=len(cibles), sur=len(lignes))

    fiches, vus = [], 0
    for r in cibles:
        if vus >= MAX_PDF:
            break
        urls, err = pdfs_de_la_page(r["page_actes_url"])
        if err:
            note("page_ignoree", commune=r["nom"], raison=err)
            continue
        for u in urls[:PAR_COMMUNE]:
            if vus >= MAX_PDF:
                break
            f = analyser(u)
            f.update(commune=r["nom"], code_insee=r["code_insee"],
                     population=r["population"], tranche=r.get("tranche"))
            fiches.append(f)
            vus += 1
            print(f"     [{vus:>3}/{MAX_PDF}] {r['nom'][:22]:<22} "
                  f"{f['pages'] or '?':>4}p {f['car_par_page']:>8} car/page  "
                  f"{f['classe']}", flush=True)

    if not fiches:
        raise RuntimeError("Aucun PDF analyse.")

    with open(os.path.join(DATA, "pdf_sonde.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fiches[0].keys()))
        w.writeheader()
        w.writerows(fiches)
    note("pdf_analyses", nombre=len(fiches))
    ecrire_resultats(fiches)


def ecrire_resultats(fiches):
    L, a = [], None
    L.append("# Les actes publies sont-ils exploitables ?\n")
    L.append(f"Genere le {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
             f"(UTC). Source : `data/pdf_sonde.csv`, une ligne par PDF, "
             f"avec son URL exacte.\n")
    L.append("\n## Methode et seuils\n")
    L.append("On mesure les caracteres de texte reellement extractibles par "
             "page (`pdftotext`). Une page de deliberation dactylographiee en "
             "contient couramment plus de 1500 ; une page scannee sans couche "
             "texte en rend zero.\n")
    L.append(f"\n- `scan_sans_texte` : 0 caractere par page — inexploitable sans OCR\n"
             f"- `texte_marginal` : moins de {SEUIL_MARGINAL} — sans doute un "
             f"scan avec un en-tete texte\n"
             f"- `texte_partiel` : de {SEUIL_MARGINAL} a {SEUIL_PARTIEL}\n"
             f"- `texte_exploitable` : plus de {SEUIL_PARTIEL}\n")
    n = len(fiches)
    c = Counter(f["classe"] for f in fiches)
    L.append("\n## Resultat\n")
    L.append("| Classe | Nombre | Part |")
    L.append("|---|---:|---:|")
    for k, v in c.most_common():
        L.append(f"| `{k}` | {v} | {100*v/n:.0f} % |")
    bons = c["texte_exploitable"] + c["texte_partiel"]
    L.append(f"\n**{bons} PDF sur {n} ({100*bons/n:.0f} %) portent une couche "
             f"texte utilisable sans OCR.**\n")
    lisibles = [f for f in fiches if f["pages"]]
    if lisibles:
        pages = sorted(f["pages"] for f in lisibles)
        L.append(f"\nPages par document : mediane {pages[len(pages)//2]}, "
                 f"de {pages[0]} a {pages[-1]}. "
                 f"Poids median : {sorted(f['octets'] for f in lisibles)[len(lisibles)//2]//1024} Ko.\n")
    L.append("\n## Lecture\n")
    L.append("Ce chiffre decide de la suite. Au-dessus des deux tiers, le corpus "
             "est de la donnee et peut etre indexe directement. En dessous d'un "
             "tiers, c'est un corpus d'images : il faudrait une chaine OCR, ce "
             "qui change la nature et le cout du projet, et cela devrait etre "
             "dit sans arrondir.\n")
    with open(os.path.join(RACINE, "RESULTATS_PDF.md"), "w", encoding="utf-8") as fh:
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
        with open(os.path.join(DATA, "pdf_diagnostic.json"), "w",
                  encoding="utf-8") as f:
            json.dump(DIAG, f, ensure_ascii=False, indent=1)
        print("\ndata/pdf_diagnostic.json ecrit.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
