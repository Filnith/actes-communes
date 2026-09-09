#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
echantillon.py — mesure de la publication en ligne des actes communaux.

Question posee, et une seule : sur un echantillon stratifie de communes
francaises, combien publient reellement leurs deliberations sur leur site,
et sous quelle forme ?

REGLE DE CONCEPTION : ce script ne doit JAMAIS echouer en silence. Il ecrit
data/diagnostic.json quoi qu'il arrive, y compris en cas de plantage, parce
que celui qui l'a ecrit ne peut pas lire les journaux d'execution de GitHub.
Le depot est le seul canal de retour. Un echec doit donc etre lisible dans
le depot, pas seulement dans une console que personne ne relira.

Conduite de collecte :
  - User-Agent identifiable, avec une adresse de contact
  - robots.txt consulte et respecte, hote par hote
  - une requete a la fois, delai entre deux requetes
  - deux pages au maximum par commune
  - la source annuaire est prise en telechargement de masse officiel,
    pas en martelant une API
"""

import csv
import json
import os
import random
import sys
import tarfile
import tempfile
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser

CONTACT = os.environ.get("CONSTAT_CONTACT", "https://github.com/")
UA = f"ConstatBot/0.2 (+{CONTACT}) mesure-publication-actes-communaux"
TIMEOUT = 20
DELAI = 1.0
SEED = int(os.environ.get("CONSTAT_SEED", "20260909"))
PAR_TRANCHE = int(os.environ.get("CONSTAT_PAR_TRANCHE", "30"))

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RACINE, "data")

DATASET = ("https://www.data.gouv.fr/api/1/datasets/"
           "service-public-gouv-fr-annuaire-de-ladministration-"
           "base-de-donnees-locales/")
ARCHIVE_REPLI = ("https://lecomarquage.service-public.gouv.fr/"
                 "donnees_locales_v4/all_latest.tar.bz2")

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

DIAG = {
    "demarre_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "user_agent": UA,
    "graine": SEED,
    "par_tranche": PAR_TRANCHE,
    "etapes": [],
    "echec": None,
}


def note(etape, **details):
    DIAG["etapes"].append(dict(etape=etape, **details))
    print(f"  . {etape} : " + ", ".join(f"{k}={v}" for k, v in details.items()),
          flush=True)


def ecrire_diagnostic():
    os.makedirs(DATA, exist_ok=True)
    DIAG["fini_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(os.path.join(DATA, "diagnostic.json"), "w", encoding="utf-8") as f:
        json.dump(DIAG, f, ensure_ascii=False, indent=1)


def sans_accents(s):
    s = unicodedata.normalize("NFD", str(s or ""))
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
            self.liens.append((self._href, " ".join("".join(self._txt).split())))
            self._href = None
            self._txt = []


_robots = {}


def robots_autorise(url):
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


def get(url, attendre=True, timeout=TIMEOUT):
    if attendre:
        time.sleep(DELAI)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            brut = r.read(4_000_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return r.status, r.geturl(), brut.decode(enc, "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, url, "", f"HTTP {e.code}"
    except Exception as e:
        return 0, url, "", type(e).__name__ + ": " + str(e)[:150]


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def charger_communes():
    url = ("https://geo.api.gouv.fr/communes"
           "?fields=nom,code,population,departement&format=json")
    st, _, corps, err = get(url, attendre=False, timeout=120)
    note("api_geo", statut=st, erreur=err, octets=len(corps))
    if st != 200:
        raise RuntimeError(f"API Geo : {err or st}")
    communes = [c for c in json.loads(corps) if c.get("population")]
    note("communes_chargees", nombre=len(communes))
    return communes


def url_archive_annuaire():
    """Resout l'archive officielle via l'API data.gouv.fr, avec repli."""
    st, _, corps, err = get(DATASET, attendre=False, timeout=60)
    note("dataset_annuaire", statut=st, erreur=err)
    if st == 200:
        try:
            d = json.loads(corps)
            ressources = [(r.get("title"), r.get("format"), r.get("url"))
                          for r in d.get("resources", []) if r.get("url")]
            note("ressources_annuaire", nombre=len(ressources),
                 titres=[t for t, _, _ in ressources][:8])
            for titre, fmt, u in ressources:
                if u.endswith((".tar.bz2", ".tar.gz", ".tgz")):
                    note("archive_retenue", titre=titre, url=u)
                    return u
        except Exception as e:
            note("dataset_illisible", erreur=str(e)[:150])
    note("archive_repli", url=ARCHIVE_REPLI)
    return ARCHIVE_REPLI


def telecharger(url, chemin):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    total = 0
    with urllib.request.urlopen(req, timeout=600) as r, open(chemin, "wb") as f:
        while True:
            buf = r.read(1 << 20)
            if not buf:
                break
            f.write(buf)
            total += len(buf)
    return total


def collecter(obj, cle):
    """Toutes les valeurs associees a `cle`, a n'importe quelle profondeur."""
    trouve, pile = [], [obj]
    while pile:
        o = pile.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if sans_accents(k) == cle:
                    trouve.append(v)
                if isinstance(v, (dict, list)):
                    pile.append(v)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)):
                    pile.append(v)
    return trouve


def aplatir_texte(v):
    """Un champ de l'annuaire peut etre une chaine, une liste, ou une liste
    de dictionnaires {valeur: ...}. On accepte les trois formes."""
    out = []
    pile = [v]
    while pile:
        o = pile.pop()
        if isinstance(o, str):
            if o.strip():
                out.append(o.strip())
        elif isinstance(o, dict):
            for k in ("valeur", "value", "url"):
                if k in o:
                    pile.append(o[k])
        elif isinstance(o, list):
            pile.extend(o)
    return out


def enregistrements(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("service", "services", "results", "records", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        return [data]
    return []


def sites_depuis_archive(chemin):
    """Renvoie {code_insee: site_internet} pour les mairies."""
    sites = {}
    membres, cles = [], Counter()
    n_fichiers = n_json = n_records = n_mairies = 0
    with tarfile.open(chemin, "r:*") as tar:
        for m in tar:
            if not m.isfile():
                continue
            n_fichiers += 1
            if len(membres) < 8:
                membres.append(m.name)
            if not m.name.lower().endswith(".json"):
                continue
            n_json += 1
            fh = tar.extractfile(m)
            if fh is None:
                continue
            try:
                data = json.loads(fh.read().decode("utf-8", "replace"))
            except Exception:
                continue
            for rec in enregistrements(data):
                if not isinstance(rec, dict):
                    continue
                n_records += 1
                if n_records <= 400:
                    for k in rec.keys():
                        cles[k] += 1
                types = [sans_accents(t) for t
                         in aplatir_texte(collecter(rec, "type_service_local"))]
                types += [sans_accents(t) for t
                          in aplatir_texte(collecter(rec, "pivotlocal"))]
                if not any("mairie" in t for t in types):
                    continue
                n_mairies += 1
                insees = [c for c in aplatir_texte(
                    collecter(rec, "code_insee_commune")) if len(c) == 5]
                urls = aplatir_texte(collecter(rec, "site_internet"))
                urls = [u for u in urls if u.startswith("http")]
                if insees and urls:
                    for i in insees:
                        sites.setdefault(i, urls[0])
    note("archive_lue", fichiers=n_fichiers, json=n_json,
         enregistrements=n_records, mairies=n_mairies,
         communes_avec_site=len(sites), exemples_membres=membres,
         cles_frequentes=[k for k, _ in cles.most_common(12)])
    return sites


# --------------------------------------------------------------------------
# Sondage
# --------------------------------------------------------------------------

def liens_pertinents(html, base):
    p = ExtracteurLiens()
    try:
        p.feed(html)
    except Exception:
        pass
    trouves, vus = [], set()
    for href, texte in p.liens:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        cible = urllib.parse.urljoin(base, href)
        if cible in vus:
            continue
        blob = sans_accents(texte + " " + cible)
        if any(mot in blob for mot in MOTS_ACTES):
            vus.add(cible)
            trouves.append((cible, texte))
    return trouves


def sonder(commune, site):
    f = {
        "code_insee": commune["code"], "nom": commune["nom"],
        "population": commune["population"],
        "departement": (commune.get("departement") or {}).get("code"),
        "site_annuaire": site, "site_repond": False, "statut_accueil": None,
        "erreur": None, "liens_actes_accueil": 0, "page_actes_url": None,
        "page_actes_statut": None, "pdf_sur_page_actes": 0,
        "liens_actes_sur_page": 0, "verdict": "non_teste",
        "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if not site:
        f["verdict"] = "pas_de_site_dans_annuaire"
        return f
    url = site if site.startswith("http") else "https://" + site
    if not robots_autorise(url):
        f["verdict"] = "robots_interdit"
        return f
    st, final, html, err = get(url)
    f["statut_accueil"], f["erreur"] = st, err
    if st != 200 or not html:
        f["verdict"] = "site_injoignable"
        return f
    f["site_repond"] = True
    cands = liens_pertinents(html, final)
    f["liens_actes_accueil"] = len(cands)
    if not cands:
        f["verdict"] = "aucun_lien_actes_en_page_accueil"
        return f

    def prio(c):
        b = sans_accents(c[1] + " " + c[0])
        return (0 if "deliberation" in b else 1 if "proces" in b else 2, len(c[0]))

    cible = sorted(cands, key=prio)[0][0]
    f["page_actes_url"] = cible
    if not robots_autorise(cible):
        f["verdict"] = "page_actes_robots_interdit"
        return f
    st2, final2, html2, _ = get(cible)
    f["page_actes_statut"] = st2
    if st2 != 200 or not html2:
        f["verdict"] = "page_actes_injoignable"
        return f
    p = ExtracteurLiens()
    try:
        p.feed(html2)
    except Exception:
        pass
    pdfs = [h for h, _ in p.liens if h and ".pdf" in h.lower()]
    f["pdf_sur_page_actes"] = len(pdfs)
    f["liens_actes_sur_page"] = len(liens_pertinents(html2, final2))
    f["verdict"] = ("actes_publies_en_pdf" if pdfs else
                    "page_actes_sans_pdf_direct" if f["liens_actes_sur_page"]
                    else "page_actes_vide")
    return f


# --------------------------------------------------------------------------

def travail():
    os.makedirs(DATA, exist_ok=True)
    print("1/4  Liste officielle des communes", flush=True)
    communes = charger_communes()

    print("2/4  Annuaire de l'administration (telechargement de masse)", flush=True)
    url = url_archive_annuaire()
    with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
        chemin = tmp.name
    octets = telecharger(url, chemin)
    note("archive_telechargee", octets=octets)
    sites = sites_depuis_archive(chemin)
    os.unlink(chemin)
    if not sites:
        raise RuntimeError("Aucun site de mairie extrait de l'archive. "
                           "Voir cles_frequentes dans le diagnostic.")

    print(f"3/4  Echantillon stratifie", flush=True)
    rng = random.Random(SEED)
    echantillon = []
    for libelle, bas, haut in TRANCHES:
        pool = [c for c in communes if bas <= c["population"] <= haut]
        pris = rng.sample(pool, min(PAR_TRANCHE, len(pool)))
        echantillon += [(libelle, c) for c in pris]
        note("tranche", nom=libelle, tirees=len(pris), disponibles=len(pool))

    print(f"4/4  Sondage de {len(echantillon)} communes", flush=True)
    fiches = []
    for i, (tranche, c) in enumerate(echantillon, 1):
        f = sonder(c, sites.get(c["code"]))
        f["tranche"] = tranche
        fiches.append(f)
        print(f"     [{i:>3}/{len(echantillon)}] {c['nom'][:26]:<26} "
              f"{c['population']:>7}  {f['verdict']}", flush=True)

    with open(os.path.join(DATA, "echantillon.json"), "w", encoding="utf-8") as fh:
        json.dump({"graine": SEED, "user_agent": UA, "fiches": fiches},
                  fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "echantillon.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fiches[0].keys()))
        w.writeheader()
        w.writerows(fiches)
    note("fiches_ecrites", nombre=len(fiches))
    ecrire_resultats(fiches)


def ecrire_resultats(fiches):
    L = []
    a = L.append
    a("# Resultats de l'echantillon\n")
    a(f"Genere le {datetime.now(timezone.utc).isoformat(timespec='seconds')} (UTC). "
      f"Graine {SEED} : le tirage est rejouable a l'identique.\n")
    a("Chaque chiffre vient de `data/echantillon.csv`, ou chaque ligne porte "
      "l'URL exacte qui l'a produite.\n")
    a("\n## Par tranche de population\n")
    a("| Tranche | Testees | Site dans l'annuaire | Site qui repond | Actes en PDF |")
    a("|---|---:|---:|---:|---:|")
    for libelle, _, _ in TRANCHES:
        g = [f for f in fiches if f.get("tranche") == libelle]
        if not g:
            continue
        a(f"| {libelle} | {len(g)} "
          f"| {sum(1 for f in g if f['site_annuaire'])} "
          f"| {sum(1 for f in g if f['site_repond'])} "
          f"| {sum(1 for f in g if f['verdict'] == 'actes_publies_en_pdf')} |")
    a("\n## Detail des verdicts\n")
    a("| Verdict | Nombre |")
    a("|---|---:|")
    for v, n in Counter(f["verdict"] for f in fiches).most_common():
        a(f"| `{v}` | {n} |")
    a("\n## Lecture\n")
    a("Ces chiffres mesurent ce qu'un robot poli atteint en deux requetes par "
      "commune. Ils sous-estiment la publication reelle : un site peut publier "
      "plus profond dans son arborescence, derriere un moteur de recherche "
      "interne, ou sur un portail intercommunal. A lire comme un plancher, "
      "pas comme une mesure exacte.\n")
    with open(os.path.join(RACINE, "RESULTATS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    code = 0
    try:
        travail()
    except Exception as e:
        DIAG["echec"] = {
            "type": type(e).__name__,
            "message": str(e)[:500],
            "trace": traceback.format_exc()[-2000:],
        }
        print("\nECHEC :", type(e).__name__, str(e)[:300], file=sys.stderr)
        code = 1
    finally:
        ecrire_diagnostic()
        print("\ndata/diagnostic.json ecrit.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
