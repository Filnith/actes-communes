#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_occultation.py — le jeu d'epreuves de l'occultation.

Trois listes, et la deuxieme compte autant que la premiere.

DOIT_OCCULTER   : les identifiants personnels. Un manque ici est un
                  manquement au RGPD.
DOIT_PRESERVER  : ce qu'une deliberation dit tout le temps et qui n'est pas
                  une donnee personnelle. Un faux positif ici detruit le
                  corpus : une archive qui occulte "refection de la rue des
                  Ecoles" ne sert plus a rien. Une occultation trop large
                  n'est pas prudente, c'est une autre facon d'echouer.
CAS_DIFFICILES  : les cas qui ont fait tomber la premiere version — adresse
                  coupee par l'OCR, "Grande Rue", parcelle communale, siege
                  d'entreprise, adresse de la mairie.

Lancer : python3 src/test_occultation.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from occultation import occulter

DOIT_OCCULTER = [
    ("domicile explicite",
     "Madame Céline DEL OLMO, domiciliée 8 allée des Troènes - 38670 "
     "CHASSE-SUR-RHÔNE, présidente de l'association"),
    ("demeurant",
     "M. Jean MARTIN, demeurant 12 rue Victor Hugo, 75011 Paris, a formulé"),
    ("sis avec civilité",
     "M. DUBOIS, propriétaire de l'immeuble sis 9 rue Pasteur 21000 DIJON"),
    ("civilité puis adresse nue",
     "M. Jean MARTIN, 15 avenue de la République, 69003 LYON, demande"),
    ("désigné par son rôle",
     "Le pétitionnaire, 15 avenue de la République, 69003 LYON, demande"),
    ("bénéficiaire d'une aide",
     "Le bénéficiaire, 3 rue Pasteur 21000 DIJON, percevra l'aide"),
    ("courriel", "Contact : jean.martin@wanadoo.fr pour toute question"),
    ("téléphone espacé", "Renseignements au 06 12 34 56 78 au secrétariat"),
    ("téléphone pointé", "Téléphone : 01.42.68.53.00"),
    ("téléphone international", "Joindre le +33 6 12 34 56 78"),
    ("téléphone collé", "Contact 0612345678 pour le dossier"),
    ("date de naissance numérique",
     "M. DUPONT Paul, né le 12/03/1970, sollicite une aide"),
    ("date de naissance en lettres", "Mme LEROY, née le 3 mars 1970, demande"),
    ("IBAN", "Virement sur le compte FR76 3000 6000 0112 3456 7890 189"),
    ("numéro de sécurité sociale",
     "Assuré n° 1 70 03 34 172 042 12 bénéficiaire de l'aide"),
]

DOIT_PRESERVER = [
    ("voie sujet de délibération",
     "Approbation des travaux de réfection de la rue des Écoles"),
    ("voie sans numéro",
     "Acquisition d'une parcelle chemin des Vignes pour le cimetière"),
    ("place publique",
     "La place du Marché sera fermée à la circulation le 14 juillet"),
    ("date de séance",
     "Procès-verbal de la séance du conseil municipal du 5 juin 2026"),
    ("date en toutes lettres",
     "L'an deux mille vingt-six, le premier juillet, à quatorze heures"),
    ("montant",
     "Attribution d'une subvention d'un montant de 12 000 euros au club"),
    ("numéro de délibération",
     "Délibération n° 2026-15 relative au budget primitif"),
    ("salle municipale avec code postal",
     "Réunion à la Salle Jean Marion, Chasse sur Rhône 38670"),
    ("élus présents",
     "Étaient présents : Mme DIAT, M PISSOCHET, Mme MARTINET SCHIRCH"),
    ("référence légale",
     "VU les articles L.2212-1 et L.2212-2 du Code général des collectivités"),
    ("horaires", "Le débit sera ouvert de 18h00 à 23h59"),
    ("effectif", "Nombre de membres en exercice : 13, présents : 8"),
]

CAS_DIFFICILES = [
    (True, "Grande Rue sans type de voie en tête",
     "M. MARTIN, domicilié 4 Grande Rue, 01000 BOURG-EN-BRESSE"),
    (True, "adresse coupée par l'OCR",
     "Mme LEROY, domiciliée 8 allée des\nTroènes 38670 CHASSE"),
    (True, "numéro suivi d'une virgule",
     "domiciliée 8, allée des Troènes 38670 Chasse-sur-Rhône"),
    (True, "mention n°", "domicilié au n° 8 rue des Lilas, 69100 VILLEURBANNE"),
    (True, "accents perdus par l'OCR",
     "Mme DUPONT, domiciliee 12 allee des Peupliers 31000 TOULOUSE"),
    (True, "lieu-dit sans type de voie",
     "M. PAGES, demeurant au lieu-dit Les Granges, 12000 RODEZ"),
    (False, "commune seule, sans rue — non identifiant, choix assumé",
     "Mme BERNARD, domiciliée à CHASSE-SUR-RHÔNE (38670)"),
    (False, "parcelle acquise par la commune",
     "Acquisition de la parcelle sise 4 chemin des Vignes 34000 MONTPELLIER"),
    (False, "commune propriétaire",
     "La commune, propriétaire de la parcelle sise 4 chemin des Vignes "
     "34000 MONTPELLIER"),
    (False, "permis de construire",
     "Permis de construire accordé pour le 12 avenue Foch 75008 PARIS"),
    (False, "classement en zone d'urbanisme",
     "Le terrain 15 route de Lyon 69003 LYON est classé en zone UA"),
    (False, "siège d'une entreprise — pas une donnée personnelle",
     "Marché attribué à SARL BATI-PRO, 7 rue de l'Industrie 42000 SAINT-ETIENNE"),
    (False, "adresse de la mairie elle-même",
     "Mairie de Chasse-sur-Rhône, 1 place de l'Hôtel de Ville 38670 CHASSE"),
]


def executer():
    echecs = []
    total = 0

    def verifier(titre, lot):
        nonlocal total
        print(f"\n=== {titre} ===")
        for entree in lot:
            if len(entree) == 3:
                attendu, nom, texte = entree
            else:
                nom, texte = entree
                attendu = titre.startswith("DOIT OCCULTER")
            net, compte, preuves = occulter(texte)
            occulte = sum(compte.values()) > 0
            ok = occulte == attendu
            total += 1
            print(f"  {'OK  ' if ok else 'RATÉ'}  "
                  f"{'occulter ' if attendu else 'préserver'}  {nom}")
            if not ok:
                echecs.append((nom, " ".join(net.split())[:120]))

    verifier("DOIT OCCULTER", DOIT_OCCULTER)
    verifier("DOIT PRÉSERVER", DOIT_PRESERVER)
    verifier("CAS DIFFICILES", CAS_DIFFICILES)

    print()
    if echecs:
        print(f"{len(echecs)} ÉCHEC(S) sur {total} :")
        for nom, detail in echecs:
            print(f"  {nom}\n      {detail}")
        return 1
    print(f"Les {total} cas passent.")
    return 0


if __name__ == "__main__":
    sys.exit(executer())
