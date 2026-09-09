#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
moisson.py — recolter de VRAIES deliberations, plus profond.

La mesure precedente s'arretait a deux pages par commune et n'a identifie que
21 deliberations : trop peu pour decider quoi que ce soit (intervalle de
confiance de 41 a 83 %). Elle disait aussi que le gisement etait juste en
dessous : les 43 fiches classees "page trouvee, pas de PDF direct" avaient
TOUTES des liens actes plus profonds.

Ce script descend donc jusqu'a trois niveaux, sur la cible retenue : les
communes de plus de 3 500 habitants, ou la publication en ligne est une
obligation legale et ou 100 % declarent un site.

Il corrige aussi un biais possible de la mesure precedente. Le tri reposait
sur le seul nom de fichier ; il se pouvait que les documents nommes
"PV-CM-*.pdf" soient justement les versions signees scannees. Ici on enregistre
SEPAREMENT les deux indices — nom de fichier et texte du lien — pour pouvoir
mesurer s'ils sont d'accord, au lieu de le supposer.

Conduite : robots.txt respecte, une requete a la fois, six pages au maximum
par commune, jamais hors du domaine de la commune.
"""

import csv
import json
import os
import random
import sys
import tempfile
import time
import traceback
import urllib.parse
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from echantillon import (get, ExtracteurLiens, robots_autorise, sans_accents,
                         charger_communes, url_archive_annuaire, telecharger,
                         sites_depuis_archive, DATA, RACINE)

POP_MIN = int(os.environ.get("CONSTAT_POP_MIN", "3500"))
NB_COMMUNES = int(os.environ.get("CONSTAT_NB_COMMUNES", "60"))
PROFONDEUR = int(os.environ.get("CONSTAT_PROFONDEUR", "3"))
PAGES_MAX = int(os.environ.get("CONSTAT_PAGES_MAX", "6"))
SEED = int(os.environ.get("CONSTAT_SEED", "20260909"))
CACHE_SITES = os.path.join(DATA, "sites_communes.json")

# Indices de deliberation, cherches separement dans le nom du fichier et dans
# le texte du lien. Les garder distincts est le seul moyen de savoir si l'un
# des deux ment.
MOTS_DELIB = ("deliberation", "delib", "proces-verbal", "proces verbal",
              "proces_verbal", "pv-", "pv_", "-pv", "pv ", "compte-rendu",
              "compte rendu", "compte_rendu", "conseil municipal",
              "conseil-municipal", "conseil_municipal", "cm-", "-cm",
              "seance du", "seance-du")

# Liens a suivre pour descendre vers les actes.
MOTS_NAVIGATION = MOTS_DELIB + ("actes", "conseil", "municipalite", "mairie",
                                "vie municipale", "publications", "documents",
                                "archives", "seances", "recueil")

DIAG = {"demarre_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parametres": {"pop_min": POP_MIN, "communes": NB_COMMUNES,
                       "profondeur": PROFONDEUR, "pages_max": PAGES_MAX,
                       "graine": SEED},
        "etapes": [], "echec": None}


def note(e, **d):
    DIAG["etapes"].append(dict(etape=e, **d))
    print("  . " + e + " : " + ", ".join(f"{k}={v}" for k, v in d.items()),
          flush=True)


def indices(texte):
    b = sans_accents(texte)
    return [m for m in MOTS_DELIB if m in b]


def charger_sites():
    """Carte code INSEE -> site. Mise en cache dans le depot : l'archive
    officielle pese 365 Mo, inutile de la retelecharger a chaque execution."""
    if os.path.exists(CACHE_SITES):
        try:
            with open(CACHE_SITES, encoding="utf-8") as f:
                d = json.load(f)
            note("sites_depuis_cache", nombre=len(d.get("sites", {})),
                 date=d.get("date"))
            return d["sites"]
        except Exception as e:
            note("cache_illisible", erreur=str(e)[:100])
    url = url_archive_annuaire()
    with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as t:
        chemin = t.name
    note("archive_telechargee", octets=telecharger(url, chemin))
    sites = sites_depuis_archive(chemin)
    os.unlink(chemin)
    os.makedirs(DATA, exist_ok=True)
    with open(CACHE_SITES, "w", encoding="utf-8") as f:
        json.dump({"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "source": url, "sites": sites}, f, ensure_ascii=False)
    return sites


def moissonner(commune, site):
    """Parcours en largeur, borne, du site d'une commune."""
    trouves = []
    if not site:
        return trouves, "pas_de_site"
    depart = site if site.startswith("http") else "https://" + site
    hote = urllib.parse.urlparse(depart).netloc
    if not hote:
        return trouves, "url_invalide"

    file_attente = [(depart, 0)]
    vues, pdfs_vus, motif = set(), set(), None

    while file_attente and len(vues) < PAGES_MAX:
        url, prof = file_attente.pop(0)
        if url in vues:
            continue
        vues.add(url)
        if not robots_autorise(url):
            motif = motif or "robots_interdit"
            continue
        st, final, html, err = get(url)
        if st != 200 or not html:
            motif = motif or (err or f"HTTP {st}")
            continue

        p = ExtracteurLiens()
        try:
            p.feed(html)
        except Exception:
            pass

        candidats = []
        for href, texte in p.liens:
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            cible = urllib.parse.urljoin(final, href)
            if urllib.parse.urlparse(cible).netloc != hote:
                continue
            nom = cible.rsplit("/", 1)[-1]

            if ".pdf" in cible.lower():
                if cible in pdfs_vus:
                    continue
                i_nom, i_txt = indices(nom), indices(texte)
                if i_nom or i_txt:
                    pdfs_vus.add(cible)
                    trouves.append({
                        "url": cible, "page_source": final, "profondeur": prof,
                        "texte_lien": texte[:120],
                        "indice_nom": ";".join(i_nom),
                        "indice_texte_lien": ";".join(i_txt),
                        "accord_des_indices": bool(i_nom) and bool(i_txt),
                    })
            elif prof < PROFONDEUR:
                blob = sans_accents(texte + " " + cible)
                if any(m in blob for m in MOTS_NAVIGATION):
                    score = 0 if indices(texte + " " + cible) else 1
                    candidats.append((score, len(cible), cible, prof + 1))

        candidats.sort()
        for _, _, cible, np in candidats:
            if cible not in vues and len(file_attente) < PAGES_MAX * 2:
                file_attente.append((cible, np))

    return trouves, (None if trouves else (motif or "rien_trouve"))


def travail():
    print("1/3  Communes et sites", flush=True)
    communes = [c for c in charger_communes() if c["population"] >= POP_MIN]
    note("communes_cibles", nombre=len(communes), seuil=POP_MIN)
    sites = charger_sites()

    rng = random.Random(SEED + 1)
    tirees = rng.sample(communes, min(NB_COMMUNES, len(communes)))
    note("communes_tirees", nombre=len(tirees))

    print(f"2/3  Moisson sur {len(tirees)} communes, profondeur {PROFONDEUR}",
          flush=True)
    lignes, motifs = [], Counter()
    for i, c in enumerate(tirees, 1):
        docs, motif = moissonner(c, sites.get(c["code"]))
        if motif:
            motifs[motif] += 1
        for d in docs:
            d.update(commune=c["nom"], code_insee=c["code"],
                     population=c["population"],
                     departement=(c.get("departement") or {}).get("code"))
            lignes.append(d)
        print(f"     [{i:>3}/{len(tirees)}] {c['nom'][:24]:<24} "
              f"{c['population']:>7}  {len(docs):>3} doc  {motif or ''}",
              flush=True)

    note("documents_trouves", nombre=len(lignes),
         communes_pourvues=len({l['code_insee'] for l in lignes}),
         motifs_d_echec=dict(motifs))
    if not lignes:
        raise RuntimeError("Aucun document. Voir motifs_d_echec.")

    # Le test du biais : les deux indices sont-ils d'accord ?
    n = len(lignes)
    nom_seul = sum(1 for l in lignes if l["indice_nom"] and not l["indice_texte_lien"])
    txt_seul = sum(1 for l in lignes if l["indice_texte_lien"] and not l["indice_nom"])
    deux = sum(1 for l in lignes if l["accord_des_indices"])
    note("accord_des_indices", les_deux=deux, nom_seul=nom_seul,
         texte_seul=txt_seul, total=n)

    with open(os.path.join(DATA, "deliberations.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)

    print("3/3  Ecrit data/deliberations.csv", flush=True)
    prof = Counter(l["profondeur"] for l in lignes)
    note("profondeur_des_trouvailles", **{f"niveau_{k}": v
                                          for k, v in sorted(prof.items())})


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
        with open(os.path.join(DATA, "moisson_diagnostic.json"), "w",
                  encoding="utf-8") as f:
            json.dump(DIAG, f, ensure_ascii=False, indent=1)
        print("\ndata/moisson_diagnostic.json ecrit.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
