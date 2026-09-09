#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
echantillon.py — mesure de la publication en ligne des actes communaux.

Question posee, et une seule : sur un echantillon stratifie de communes
francaises, combien publient reellement leurs deliberations sur leur site,
et sous quelle forme ?

Le script mesure. Il ne suppose rien et n'ecrit aucune conclusion en dur.
Chaque ligne du rapport porte l'URL exacte qui l'a produite, pour que
n'importe qui puisse refaire le trajet et contredire le resultat.

Conduite de collecte :
  - User-Agent identifiable, avec une adresse de contact
  - robots.txt consulte et respecte, hote par hote
  - une requete a la fois, delai entre deux requetes
  - deux pages au maximum par commune
"""

import csv
import json
import os
import random
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser

CONTACT = os.environ.get("CONSTAT_CONTACT", "https://github.com/")
UA = f"ConstatBot/0.1 (+{CONTACT}) mesure-publication-actes-communaux"
TIMEOUT = 15
DELAI = 1.0
SEED = int(os.environ.get("CONSTAT_SEED", "20260909"))
PAR_TRANCHE = int(os.environ.get("CONSTAT_PAR_TRANCHE", "30"))

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RACINE, "data")

# Le seuil de 3 500 habitants est celui de l'article L. 2131-1 du CGCT :
# au-dessus, publication electronique obligatoire ; en dessous, droit d'option
# avec l'electronique par defaut. Les tranches sont construites autour de lui.
TRANCHES = [
    ("moins de 500", 0, 499),
    ("500 a 3499", 500, 3499),
    ("3500 a 9999", 3500, 9999),
    ("10000 a 49999", 10000, 49999),
    ("50000 et plus", 50000, 10**9),
]

MOTS_ACTES = [
    "deliberation", "deliberations",
    "conseil municipal", "conseil-municipal",
    "proces verbal", "proces-verbal", "proces verbaux", "proces-verbaux",
    "compte rendu", "compte-rendu", "comptes rendus", "comptes-rendus",
    "recueil des actes", "actes administratifs", "publicite des actes",
]


def sans_accents(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


class ExtracteurLiens(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.liens = []
        self._href = None
        self._txt = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._txt = []

    def handle_data(self, data):
        if self._href is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            texte = " ".join("".join(self._txt).split())
            self.liens.append((self._href, texte))
            self._href = None
            self._txt = []


_robots = {}


def robots_autorise(url):
    """Consulte le robots.txt de l'hote. En cas d'absence ou d'erreur de
    lecture, on considere l'acces autorise, ce qui est la convention."""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    if rp is None:
        return True
    try:
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def get(url, attendre=True):
    """Renvoie (statut, url_finale, corps_texte, erreur)."""
    if attendre:
        time.sleep(DELAI)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            brut = r.read(3_000_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return r.status, r.geturl(), brut.decode(enc, "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, url, "", f"HTTP {e.code}"
    except Exception as e:
        return 0, url, "", type(e).__name__ + ": " + str(e)[:120]


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def charger_communes():
    """Liste officielle des communes avec population (API Geo, Etat francais)."""
    url = ("https://geo.api.gouv.fr/communes"
           "?fields=nom,code,population,departement&format=json")
    st, _, corps, err = get(url, attendre=False)
    if st != 200:
        raise SystemExit(f"API Geo injoignable : {err or st}")
    communes = json.loads(corps)
    return [c for c in communes if c.get("population")]


def charger_annuaire():
    """Annuaire de l'administration : mairies et leur site internet.

    La ressource est resolue dynamiquement via l'API data.gouv.fr plutot
    qu'en URL codee en dur, pour survivre a un changement de lien.
    """
    meta = "https://www.data.gouv.fr/api/1/datasets/api-lannuaire-administration/"
    st, _, corps, err = get(meta, attendre=False)
    if st != 200:
        raise SystemExit(f"Metadonnees annuaire injoignables : {err or st}")
    d = json.loads(corps)
    candidates = []
    for r in d.get("resources", []):
        titre = sans_accents(r.get("title", ""))
        fmt = (r.get("format") or "").lower()
        if fmt in ("json", "csv") and r.get("url"):
            score = 0
            if "commune" in titre or "mairie" in titre:
                score += 2
            if fmt == "json":
                score += 1
            candidates.append((score, r.get("title"), r.get("url"), fmt))
    if not candidates:
        raise SystemExit("Aucune ressource exploitable dans l'annuaire.")
    candidates.sort(reverse=True)
    print(f"  ressource annuaire retenue : {candidates[0][1]} ({candidates[0][3]})")
    return candidates[0][2], candidates[0][3]


def sites_par_insee(url, fmt):
    """Renvoie {code_insee: site_internet} depuis la ressource annuaire."""
    st, _, corps, err = get(url, attendre=False)
    if st != 200:
        raise SystemExit(f"Ressource annuaire injoignable : {err or st}")
    sites = {}

    def enregistre(insee, site):
        if insee and site and insee not in sites:
            sites[str(insee).zfill(5)] = site

    if fmt == "json":
        data = json.loads(corps)
        if isinstance(data, dict):
            data = data.get("records") or data.get("results") or []
        for e in data:
            if not isinstance(e, dict):
                continue
            champs = e.get("fields", e)
            insee = (champs.get("code_insee_commune")
                     or champs.get("code_insee")
                     or champs.get("codeInsee"))
            if isinstance(insee, list):
                insee = insee[0] if insee else None
            site = champs.get("site_internet") or champs.get("siteInternet")
            if isinstance(site, str) and site.startswith("["):
                try:
                    j = json.loads(site)
                    site = j[0].get("valeur") if j else None
                except Exception:
                    pass
            if isinstance(site, list):
                site = (site[0].get("valeur") if site and isinstance(site[0], dict)
                        else (site[0] if site else None))
            enregistre(insee, site)
    else:
        lignes = corps.splitlines()
        lecteur = csv.DictReader(lignes, delimiter=";")
        if lecteur.fieldnames and len(lecteur.fieldnames) < 2:
            lecteur = csv.DictReader(lignes, delimiter=",")
        for row in lecteur:
            bas = {sans_accents(k): v for k, v in row.items() if k}
            insee = bas.get("code_insee_commune") or bas.get("code_insee")
            enregistre(insee, bas.get("site_internet"))
    return sites


# --------------------------------------------------------------------------
# Sondage d'une commune
# --------------------------------------------------------------------------

def liens_pertinents(html, base):
    p = ExtracteurLiens()
    try:
        p.feed(html)
    except Exception:
        pass
    trouves = []
    for href, texte in p.liens:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        cible = urllib.parse.urljoin(base, href)
        blob = sans_accents(texte + " " + cible)
        for mot in MOTS_ACTES:
            if mot in blob:
                trouves.append((cible, texte, mot))
                break
    vus, uniques = set(), []
    for c, t, m in trouves:
        if c not in vus:
            vus.add(c)
            uniques.append((c, t, m))
    return uniques


def sonder(commune, site):
    """Deux requetes au maximum : l'accueil, puis la meilleure page candidate."""
    fiche = {
        "code_insee": commune["code"],
        "nom": commune["nom"],
        "population": commune["population"],
        "departement": (commune.get("departement") or {}).get("code"),
        "site_annuaire": site,
        "site_repond": False,
        "statut_accueil": None,
        "robots_bloque": False,
        "erreur": None,
        "liens_actes_accueil": 0,
        "page_actes_url": None,
        "page_actes_statut": None,
        "pdf_sur_page_actes": 0,
        "liens_actes_sur_page": 0,
        "verdict": "non_teste",
        "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if not site:
        fiche["verdict"] = "pas_de_site_dans_annuaire"
        return fiche

    url = site if site.startswith("http") else "https://" + site
    if not robots_autorise(url):
        fiche["robots_bloque"] = True
        fiche["verdict"] = "robots_interdit"
        return fiche

    st, final, html, err = get(url)
    fiche["statut_accueil"] = st
    fiche["erreur"] = err
    if st != 200 or not html:
        fiche["verdict"] = "site_injoignable"
        return fiche
    fiche["site_repond"] = True

    cands = liens_pertinents(html, final)
    fiche["liens_actes_accueil"] = len(cands)
    if not cands:
        fiche["verdict"] = "aucun_lien_actes_en_page_accueil"
        return fiche

    def priorite(c):
        b = sans_accents(c[1] + " " + c[0])
        return (0 if "deliberation" in b else 1 if "proces" in b else 2, len(c[0]))

    cible = sorted(cands, key=priorite)[0][0]
    fiche["page_actes_url"] = cible
    if not robots_autorise(cible):
        fiche["verdict"] = "page_actes_robots_interdit"
        return fiche

    st2, final2, html2, err2 = get(cible)
    fiche["page_actes_statut"] = st2
    if st2 != 200 or not html2:
        fiche["verdict"] = "page_actes_injoignable"
        return fiche

    p = ExtracteurLiens()
    try:
        p.feed(html2)
    except Exception:
        pass
    pdfs = [h for h, _ in p.liens if h and ".pdf" in h.lower()]
    fiche["pdf_sur_page_actes"] = len(pdfs)
    fiche["liens_actes_sur_page"] = len(liens_pertinents(html2, final2))
    if pdfs:
        fiche["verdict"] = "actes_publies_en_pdf"
    elif fiche["liens_actes_sur_page"] > 0:
        fiche["verdict"] = "page_actes_sans_pdf_direct"
    else:
        fiche["verdict"] = "page_actes_vide"
    return fiche


# --------------------------------------------------------------------------

def main():
    os.makedirs(DATA, exist_ok=True)
    print("1/4  Liste officielle des communes...")
    communes = charger_communes()
    print(f"     {len(communes)} communes avec population")

    print("2/4  Annuaire de l'administration...")
    url, fmt = charger_annuaire()
    sites = sites_par_insee(url, fmt)
    print(f"     {len(sites)} communes avec un site declare")

    print(f"3/4  Echantillon stratifie (graine {SEED}, {PAR_TRANCHE} par tranche)...")
    rng = random.Random(SEED)
    echantillon = []
    for libelle, bas, haut in TRANCHES:
        pool = [c for c in communes if bas <= c["population"] <= haut]
        pris = rng.sample(pool, min(PAR_TRANCHE, len(pool)))
        for c in pris:
            echantillon.append((libelle, c))
        print(f"     {libelle:<16} {len(pris):>4} tirees sur {len(pool)}")

    print(f"4/4  Sondage de {len(echantillon)} communes...")
    fiches = []
    for i, (tranche, c) in enumerate(echantillon, 1):
        f = sonder(c, sites.get(c["code"]))
        f["tranche"] = tranche
        fiches.append(f)
        print(f"     [{i:>3}/{len(echantillon)}] {c['nom'][:28]:<28} "
              f"{c['population']:>7}  {f['verdict']}")

    with open(os.path.join(DATA, "echantillon.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "graine": SEED,
            "par_tranche": PAR_TRANCHE,
            "user_agent": UA,
            "fiches": fiches,
        }, fh, ensure_ascii=False, indent=1)

    if fiches:
        with open(os.path.join(DATA, "echantillon.csv"), "w",
                  encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(fiches[0].keys()))
            w.writeheader()
            w.writerows(fiches)

    ecrire_resultats(fiches)
    print("\nTermine. Voir RESULTATS.md")


def ecrire_resultats(fiches):
    from collections import Counter
    lignes = []
    a = lignes.append
    a("# Resultats de l'echantillon\n")
    a(f"Genere le {datetime.now(timezone.utc).isoformat(timespec='seconds')} (UTC). "
      f"Graine {SEED}. Rejouable a l'identique.\n")
    a("Chaque chiffre ci-dessous vient de `data/echantillon.csv`, "
      "ou chaque ligne porte l'URL exacte qui l'a produite.\n")

    a("\n## Par tranche de population\n")
    a("| Tranche | Testees | Site qui repond | Actes en PDF trouves |")
    a("|---|---:|---:|---:|")
    for libelle, _, _ in TRANCHES:
        g = [f for f in fiches if f.get("tranche") == libelle]
        if not g:
            continue
        rep = sum(1 for f in g if f["site_repond"])
        pdf = sum(1 for f in g if f["verdict"] == "actes_publies_en_pdf")
        a(f"| {libelle} | {len(g)} | {rep} | {pdf} |")

    a("\n## Detail des verdicts\n")
    a("| Verdict | Nombre |")
    a("|---|---:|")
    for v, n in Counter(f["verdict"] for f in fiches).most_common():
        a(f"| `{v}` | {n} |")

    a("\n## Lecture\n")
    a("Ces chiffres mesurent ce qu'un robot poli atteint en deux requetes par "
      "commune. Ils sous-estiment la publication reelle : un site peut publier "
      "ses actes plus profondement dans son arborescence, derriere un moteur de "
      "recherche interne, ou sur un portail intercommunal. A traiter comme un "
      "plancher, pas comme une mesure exacte.\n")

    with open(os.path.join(RACINE, "RESULTATS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lignes) + "\n")


if __name__ == "__main__":
    sys.exit(main())
