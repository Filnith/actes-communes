#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =========================================================================
#  NE PAS BRANCHER DANS LA CHAINE. MODULE INAPTE, ET PAS SEULEMENT BUGUE.
#
#  Revue adverse du 2026-09-10 : 17 defauts, tous verifies par execution.
#  Le pire, et il suffit a condamner l'approche : la regle qui exige une
#  personne physique se declenche sur "M. le Maire". Or toute deliberation
#  francaise commence par "Monsieur le Maire indique que...". Le module
#  occulte donc la parcelle, le permis de construire, le siege de
#  l'entreprise attributaire et jusqu'a l'adresse de la mairie — c'est-a-dire
#  tout le corpus. Les 40 epreuves passaient parce qu'elles etaient ecrites
#  sans sujet parlant ; un vrai proces-verbal en a toujours un.
#
#  Deux autres conclusions de fond :
#   - Premisse juridique fausse : "petitionnaire", "demandeur",
#     "beneficiaire" designent le plus souvent une personne MORALE (SCI,
#     SARL, association), et "domicilie" est le terme consacre du siege
#     social. Le raisonnement de depart etait errone, pas seulement
#     l'implementation.
#   - Les listes d'emargement au format "NOM Prenom + adresse", qui sont la
#     forme la plus courante des fuites reelles, ne declenchent aucune regle.
#
#  Ce n'est pas une liste de correctifs a appliquer : c'est une erreur de
#  categorie. "Cette adresse est-elle rattachee a une personne physique"
#  n'est pas une question d'expression reguliere. Elle demande de la
#  reconnaissance d'entites nommees.
#
#  Ce qui reste valable : les identifiants structures (IBAN, NIR,
#  telephone, courriel) SONT des problemes d'expression reguliere — mais
#  les quatre implementations ci-dessous ont chacune des defauts averes.
#
#  Conserve comme piece a conviction et comme base d'epreuves. Voir
#  claude/occultation-revue.md.
# =========================================================================
"""
occultation.py — retirer les identifiants personnels avant toute publication.

Pourquoi en amont et pas en aval : le depot est public sur GitHub, donc
indexable par les moteurs. Une architecture "archive complete, index expurge"
ne protegerait rien. Le texte non expurge ne doit jamais quitter le runner.

Base juridique (voir claude/rgpd.md) : article L.312-1-2 du CRPA ; liste CNIL
des mentions a occulter — etat civil, coordonnees, informations financieres.

---------------------------------------------------------------------------
LE PRINCIPE, tire du droit et non de la prudence : ce qui rend une adresse
personnelle, ce n'est pas la voie, c'est son RATTACHEMENT A UNE PERSONNE
PHYSIQUE.
---------------------------------------------------------------------------

Une premiere version occultait toute adresse postale complete. Le jeu
d'epreuves a montre qu'elle detruisait le corpus : elle masquait la parcelle
acquise par la commune, l'adresse d'un permis de construire, le terrain classe
en zone UA, le siege de l'entreprise attributaire d'un marche — et jusqu'a
l'adresse de la mairie elle-meme. Or ce sont exactement les informations pour
lesquelles on consulterait ce corpus. Une adresse d'entreprise n'est d'ailleurs
pas une donnee personnelle.

D'ou trois regles etroites :

  R1  marqueur strictement personnel ("domicilie", "demeurant", "residant")
      suivi d'une adresse. Ces mots ne s'appliquent qu'a des personnes.
  R2  marqueur ambigu ("sis", "sise") — qui s'applique aussi bien a une
      parcelle qu'a un habitant — occulte SEULEMENT si une personne physique
      est designee avant.
  R3  adresse postale complete sans marqueur, occultee SEULEMENT si une
      personne physique est designee avant.

"Personne physique designee" veut dire : une civilite (M., Mme), ou l'un des
mots par lesquels un acte administratif designe un particulier sans le nommer
— "le petitionnaire", "le demandeur", "le beneficiaire". Volontairement
exclus : "proprietaire" et "exploitant", qui qualifient aussi bien une commune
ou une societe, et dont l'ajout ferait occulter la parcelle dont la commune
est proprietaire.

Un nom de voie seul, une parcelle, un siege social, la mairie : conserves.

Rien n'est supprime en silence : chaque occultation laisse un marqueur visible,
pour que le lecteur sache qu'une mention a ete retiree et laquelle.

Cette occultation n'est PAS une garantie a elle seule. C'est la premiere de
quatre couches : occultation, non-indexation des noms de personnes, noindex
pour les moteurs generalistes, procedure de retrait operable. Aucune n'est
presentee comme suffisante.
"""

import re
from collections import Counter

MARQUE = "[{} OCCULTÉ]"

# Un qualificatif peut preceder le type de voie : "Grande Rue", "Petite Place".
QUALIFICATIF = r"(?:(?:grand[e']?|petit[e]?|vieille?|haut[e]?|bas[se]{0,2})\s*)?"

TYPES_VOIE = (r"(?:rue|avenue|av\.|boulevard|bd\.?|all[ée]e|chemin|impasse|"
              r"place|route|quai|cours|square|lotissement|r[ée]sidence|"
              r"hameau|lieu[-\s]dit|faubourg|sentier|passage|villa|"
              r"esplanade|promenade|mont[ée]e|traverse|voie|clos|domaine|"
              r"rond[-\s]point|zone|parc|cit[ée]|mas|quartier)")

VOIE = QUALIFICATIF + TYPES_VOIE
NUMERO = r"(?:n[°o]\s*)?\d{1,4}\s*(?:bis|ter|quater)?[,\s]*"
CODE_POSTAL = r"\d{5}"

# Le corps de l'adresse peut contenir un saut de ligne : l'OCR coupe souvent
# une adresse en deux. L'exclure produisait une occultation PARTIELLE, qui
# laisse la moitie de l'adresse en clair tout en ayant l'air traitee — pire
# que pas d'occultation du tout.
CORPS = r"[^,;.]{0,60}"
FIN_CP = r"(?:[\s,\-–]*" + CODE_POSTAL + r"[\s\-]*[A-ZÀ-Þ][^,;.\n]{0,40})?"
ADRESSE = r"(?:" + NUMERO + r")?" + VOIE + CORPS + FIN_CP

CIVILITE = (r"(?:M\.|MM\.|Mme|Mmes|Mlle|Monsieur|Madame|Mademoiselle|"
            r"Messieurs|Mesdames)")

# Un acte administratif designe souvent un particulier par son role plutot que
# par une civilite : "le petitionnaire", "le demandeur". Ces mots designent
# toujours une personne qui s'adresse a l'administration.
# "proprietaire" et "exploitant" sont volontairement absents : ils qualifient
# aussi bien une commune ou une societe, et les inclure ferait occulter la
# parcelle dont la commune est proprietaire.
ROLE_PERSONNE = (r"(?:p[ée]titionnaire|demandeur|demanderesse|requ[ée]rant[e]?|"
                 r"b[ée]n[ée]ficiaire|int[ée]ress[ée]{1,2}|administr[ée]{1,2})")

PERSONNE = r"(?:" + CIVILITE + r"|" + ROLE_PERSONNE + r")"

MARQUEURS_PERSONNELS = (r"(?:domicili[ée]{1,2}s?|demeurant|r[ée]sidant|"
                        r"dont\s+le\s+domicile|adresse\s+personnelle)")
MARQUEUR_AMBIGU = r"(?:sis|sise|sises)"
LIAISON = r"\s*(?:au?x?|à|:)?\s*"

# Chaque regle expose un groupe nomme "cible" : c'est lui, et lui seul, qui est
# remplace. Le contexte ("domicilie a", la civilite) est conserve, sans quoi la
# phrase deviendrait incomprehensible.
REGLES = [
    ("COURRIEL", re.compile(
        r"(?P<cible>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")),

    ("IBAN", re.compile(
        r"(?P<cible>\bFR\d{2}(?:[ ]?[A-Z0-9]{4}){5}[ ]?[A-Z0-9]{3}\b)")),

    ("NUMÉRO DE SÉCURITÉ SOCIALE", re.compile(
        r"(?P<cible>\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2])\s?\d{2}\s?\d{3}"
        r"\s?\d{3}(?:\s?\d{2})?\b)")),

    ("TÉLÉPHONE", re.compile(
        r"(?<![\d.,])(?P<cible>(?:\+33\s?|0)[1-9](?:[\s.\-]?\d{2}){4})"
        r"(?![\d.,])")),

    ("DATE DE NAISSANCE", re.compile(
        r"\bn[ée]{1,2}\s*(?:\(e\))?\s*le\s+(?P<cible>"
        r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})",
        re.IGNORECASE)),

    # R1 — marqueur strictement personnel.
    ("ADRESSE", re.compile(
        MARQUEURS_PERSONNELS + LIAISON + r"(?P<cible>" + ADRESSE + r")",
        re.IGNORECASE)),

    # R2 — marqueur ambigu, seulement si une personne physique est designee.
    ("ADRESSE", re.compile(
        PERSONNE + r"[^.;\n]{0,70}?" + MARQUEUR_AMBIGU + LIAISON +
        r"(?P<cible>" + ADRESSE + r")",
        re.IGNORECASE)),

    # R3 — adresse postale complete, meme condition.
    ("ADRESSE", re.compile(
        PERSONNE + r"[^.;\n]{0,70}?[,\s]\s*(?P<cible>\d{1,4}\s*"
        r"(?:bis|ter)?[,\s]+" + VOIE + CORPS +
        r"[\s,\-–]+" + CODE_POSTAL + r"[\s\-]*[A-ZÀ-Þ][^,;.\n]{0,40})",
        re.IGNORECASE)),
]

RESIDU_CODE_POSTAL = re.compile(r"\b\d{5}\b")


def occulter(texte):
    """Renvoie (texte_expurgé, compte_par_catégorie, mentions_retirées)."""
    compte = Counter()
    preuves = []
    for categorie, motif in REGLES:
        def remplacer(m, cat=categorie):
            cible = m.group("cible")
            if not cible or not cible.strip():
                return m.group(0)
            compte[cat] += 1
            preuves.append((cat, " ".join(cible.split())))
            a, b = m.span("cible"), m.span(0)
            return (m.group(0)[:a[0] - b[0]] + MARQUE.format(cat)
                    + m.group(0)[a[1] - b[0]:])
        texte = motif.sub(remplacer, texte)
    return texte, compte, preuves


def residus(texte, marge=70):
    """Contextes où un code postal subsiste après occultation.

    Ce n'est pas une liste d'erreurs : la plupart sont légitimes — siège d'une
    entreprise, adresse de la mairie, parcelle, salle municipale. C'est un
    indicateur de risque résiduel, à lire à la main. Une conformité qui ne
    mesure pas ce qu'elle rate est une conformité de façade.
    """
    out = []
    for m in RESIDU_CODE_POSTAL.finditer(texte):
        a, b = max(0, m.start() - marge), min(len(texte), m.end() + marge)
        out.append(" ".join(texte[a:b].split()))
    return out


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "data/ocr_extraits.txt"
    brut = open(src, encoding="utf-8").read()
    net, compte, preuves = occulter(brut)
    print("=== OCCULTATIONS ===")
    for k, v in compte.most_common():
        print(f"  {v:>3}  {k}")
    print(f"  total : {sum(compte.values())}")
    print("\n=== MENTIONS RETIRÉES (à vérifier par lecture) ===")
    for cat, ex in preuves[:20]:
        print(f"  [{cat}] {ex[:110]}")
    r = residus(net)
    print(f"\n=== RÉSIDUS : {len(r)} codes postaux subsistants ===")
    for c in r[:8]:
        print(f"  … {c} …")
