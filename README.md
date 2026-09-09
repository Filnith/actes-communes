# Les actes des communes françaises

Rendre lisible et cherchable ce que décident réellement les conseils municipaux
français. Ces documents — délibérations, procès-verbaux, actes administratifs —
décident du sol, de l'eau, de l'argent, des écoles et du bâti. Ils sont publics
par obligation légale. Ils sont illisibles en pratique : déposés en PDF sur
36 000 sites que personne n'ouvre, sans aucune agrégation nationale.

Ce n'est pas de l'information cachée, ce qui serait un problème politique.
C'est de l'information disponible et inutilisable, ce qui est un problème
d'échelle.

## La règle de maison

Rien n'est affirmé sans reçu. Chaque ligne produite ici porte l'URL exacte et
la date qui l'ont produite. « Je ne sais pas » est un résultat publiable, et
un résultat négatif se publie aussi fort qu'un résultat positif.

## Fondation juridique

Réforme entrée en vigueur le 1er juillet 2022 — ordonnance n° 2021-1310 et
décret n° 2021-1311 du 7 octobre 2021, articles L. 2131-1 et R. 2131-1 du CGCT :

- La publication **sous forme électronique sur le site internet** de la
  collectivité est le régime de droit commun.
- **Plus de 3 500 habitants** : obligation. Publication « uniquement sous forme
  électronique, via une publication sur leur site internet ».
- **Moins de 3 500 habitants** : droit d'option entre affichage, papier et
  électronique — mais **l'électronique s'applique par défaut** en l'absence de
  délibération contraire.

Le corpus est donc légalement censé exister en ligne. Savoir s'il existe
réellement est une question empirique. C'est ce que mesure la première étape.

## Étape en cours : mesurer avant de construire

`src/echantillon.py` tire un échantillon stratifié de communes par tranche de
population, autour du seuil légal de 3 500 habitants, et mesure combien
publient effectivement leurs actes en ligne et sous quelle forme.

Si la matière n'est pas récupérable, le projet n'a pas lieu d'être, et ce dépôt
le dira.

Sources : liste officielle des communes (API Géo) et Annuaire de
l'administration (data.gouv.fr).

## Conduite de collecte

Non négociable pour un projet dont toute la valeur est la légitimité :

- User-Agent identifiable, avec une adresse de contact
- `robots.txt` consulté et respecté, hôte par hôte
- une requête à la fois, avec délai
- deux pages au maximum par commune

## Exécution

Le robot tourne sur GitHub Actions, pas sur une machine personnelle — pour
qu'il continue sans personne. Onglet *Actions* → *Échantillon* → *Run workflow*.
Les résultats sont réécrits dans `data/` et `RESULTATS.md` par le robot lui-même.
