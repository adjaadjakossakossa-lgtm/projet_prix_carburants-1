# Note de synthèse : chaque matin, un conseil de plein (≈ 365 € par an) et la liste des stations proches ouvertes et moins chères

**Pour :** gestionnaire de flotte, Livraisons Exemple · **De :** SEP Conseil (Hervé Adjakossa, Liam Arnault, Antoine Pholulamdeth, Samuel Sidoli) · **Date :** 18/11/2026 · **Document :** livrable de formation, client fictif · chiffres de l'entraînement du 18/11/2026

## La décision que nous vous demandons

Utiliser l'outil chaque matin pendant 3 mois sur vos pleins hebdomadaires, de deux façons :

1. suivre le conseil « faire le plein ou attendre 3 jours » ;
2. choisir, quand il y en a une **sur la tournée**, la station proche moins chère, ouverte et sans rupture.

Suivre chaque mois le regret moyen observé.

## Votre question

Vous faites le plein de 40 utilitaires diesel une fois par semaine, dans le Nord et le Pas-de-Calais. Vous pouvez avancer ou décaler un plein de 3 jours. Aujourd'hui, vous faites le plein tout de suite : sur nos données de test, cela coûte en moyenne 1,24 c€/L de plus que le meilleur des deux jours. Faut-il attendre, et où faire le plein ?

## Nos données

- **Le flux quotidien officiel (data.gouv.fr)** dit chaque matin quelles stations sont ouvertes, lesquelles sont en rupture, et leur dernier prix. Le 17/11/2026, sur 469 stations de votre zone :
  - 8 sont fermées ;
  - 20 sont en rupture de gazole ;
  - 100 n'ont pas de prix récent (34 sans prix, 66 avec un prix de plus de 7 jours).

- **Le taux euro/dollar de la BCE** est croisé avec les prix : le pétrole se paie en dollars.
- **L'historique des prix** (2025-2026, 475 stations) vient des archives du même producteur, car le flux ne garde que le dernier jour.

## Ce que nous avons trouvé

1. **Le conseil de plein fait gagner peu, mais il gagne.** Le regret moyen passe de 1,24 à 0,95 c€/L sur 55 282 lignes que le modèle n'a jamais vues (du 04/05 au 16/10/2026). Le gain est de 0,29 c€/L, avec un intervalle de confiance à 95 % de 0,06 à 0,60.
2. **Le taux euro/dollar n'ajoute rien de mesurable.** Le modèle qui ne voit que les prix fait aussi bien (0,91 c€/L). L'écart entre les deux, −0,04 c€/L, est nul aux erreurs près. Nous avions choisi le modèle avec le taux **avant** de voir le test, et nous ne changeons pas ce choix après coup.
3. **Le choix de la station pèse plus que le jour du plein.** Faire un détour ne rapporte presque rien, environ 70 € par an une fois le temps du chauffeur payé. Mais quand une station moins chère est déjà sur la tournée, le gain peut monter à environ 2 780 € par an.
4. **Trois profils de stations.** Les 67 stations « chères » sont à 7,8 c€/L au-dessus de la médiane de leur département.

## Notre recommandation, chiffrée

| Option | Ce que ça change | Regret moyen (c€/L) | Gain annuel estimé |
|---|---|---|---|
| Ne rien changer (toujours faire le plein tout de suite) | Rien | 1,24 | 0 € |
| Toujours attendre 3 jours | Pire que la situation actuelle | 1,60 | aucun (perte) |
| **Conseil de plein de l'outil (recommandé)** | Un conseil par station chaque matin | **0,95** | **environ 365 € par an** (124 800 L), entre 75 et 750 € (IC 95 %) |
| Station moins chère déjà sur la tournée | Changer de station sans détour | — | jusqu'à environ 2 780 € par an, à vérifier sur vos tournées |
| Connaître l'avenir (plafond du conseil de plein) | Impossible | 0,00 | environ 1 550 € par an au maximum |

**Comment le seuil est fixé :** attendre alors que le prix monte coûte 3,25 c€/L en moyenne, et faire le plein alors que le prix ne monte pas coûte 1,16 c€/L. On fait donc le plein dès que la probabilité de hausse dépasse 0,26.

## Ce que l'outil ne sait pas faire

- **Il conseille « faire le plein » dans 80 % des cas** : il ne vous fera attendre qu'occasionnellement.
- **Le gain dépend de la phase du marché.** Il vient surtout de mai et juin 2026, quand les prix redescendaient. En juillet, quand ils montaient, l'outil a fait un peu pire que « toujours faire le plein ».
- **Une seule période de test**, pendant une crise des prix : rien ne garantit le même gain en période calme.
- **Il ne connaît pas vos tournées.** Le détour est estimé à vol d'oiseau × 1,3.
- **Gazole seulement**, Nord et Pas-de-Calais, hors autoroute.
- **Il faut rafraîchir les données chaque matin** (deux commandes), sinon le conseil date de la veille.

## Ce que nous avons changé après le COMEX

| Retour du COMEX | Ce que nous avons fait |
|---|---|
| Le projet pourrait intéresser au-delà de votre entreprise ; l'élargir à d'autres régions que le Nord et le Pas-de-Calais | Pas encore fait, faute de temps et de puissance de calcul. L'outil est prêt pour ça : la zone étudiée est un simple réglage. Une région comme le Grand Est demande seulement un calcul plus long ; la France entière, une machine plus puissante. |

## Comment suivre les résultats

| Indicateur | Fréquence | Alerte si | Qui |
|---|---|---|---|
| Regret moyen des pleins du mois, en c€/L (prix payé moins le meilleur des deux prix) | Mensuelle | Il dépasse celui de « toujours faire le plein » sur les mêmes pleins deux mois de suite | Gestionnaire de flotte |
| Date du flux utilisé par l'outil | Quotidienne | Le flux date de plus d'un jour | Gestionnaire de flotte |

Pour mesurer le vrai gain, nous proposons un **A/B test** : la moitié des véhicules suit l'outil, l'autre moitié fait le plein comme avant, pendant 3 mois.
