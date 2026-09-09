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

## Où en est la mesure

**La matière existe.** Premier échantillon, 150 communes, 30 par tranche de
population (exécution du 2026-09-09, graine 20260909, rejouable) :

- 34 957 communes recensées, **22 113 déclarent un site internet** (63 %).
- **Au-dessus du seuil légal de 3 500 habitants : 90 sur 90 déclarent un site.**
  Cent pour cent, ce qui correspond à l'obligation de l'article L. 2131-1.
- Parmi ceux qui répondent, **49 sur 68 mènent à une section « actes » en deux
  requêtes seulement — 72 %.**
- Les 43 fiches classées `page_actes_sans_pdf_direct` ont **toutes** des liens
  « actes » supplémentaires sur la page atteinte : les documents sont un clic
  plus loin que là où le robot s'est arrêté.

Les échecs restants sont surtout ceux du robot, pas des communes : `robots.txt`
respecté, menus rendus en JavaScript, URL périmées dans l'annuaire.

Détail dans [`RESULTATS.md`](RESULTATS.md) et `data/echantillon.csv`, où chaque
ligne porte l'URL exacte qui l'a produite.

**Conséquence : viser d'abord les ~3 290 communes de plus de 3 500 habitants.**
Elles ont toutes un site, elles sont toutes légalement tenues de publier en
ligne, et le taux d'atteinte y est déjà de 72 % avec un robot naïf.

## Prochaine mesure : ces PDF sont-ils du texte ou des images ?

C'est la contrainte bloquante suivante, et elle est plus sévère. Un PDF scanné
d'un registre manuscrit ne vaut rien sans OCR ; un PDF avec couche texte vaut
tout. `src/pdf_sonde.py` mesure les caractères réellement extractibles par page
sur un échantillon des documents trouvés.

Au-dessus des deux tiers, le corpus est de la donnée. En dessous d'un tiers,
c'est un corpus d'images, il faudrait une chaîne OCR, et cela changerait la
nature comme le coût du projet. Ce sera dit sans arrondir.

## Conduite de collecte

Non négociable pour un projet dont toute la valeur est la légitimité :

- User-Agent identifiable, avec une adresse de contact
- `robots.txt` consulté et respecté, hôte par hôte
- une requête à la fois, avec délai
- profondeur limitée par commune
- sources prises en téléchargement de masse officiel, pas en martelant une API

## Exécution

Le robot tourne sur GitHub Actions, pas sur une machine personnelle — pour
qu'il continue sans personne. L'échantillon se relance chaque lundi matin, non
pour récolter du neuf, mais pour détecter la pourriture silencieuse : une
source qui déménage, un format qui dérive. Un pipeline qui rouille sans
prévenir est la panne la plus coûteuse, parce qu'on la découvre trop tard.

Les deux workflows sont aussi lançables à la main depuis l'onglet *Actions*.
Chacun réécrit ses résultats dans le dépôt, **y compris en cas d'échec** : le
dépôt est le seul canal de retour de celui qui écrit ce code.
