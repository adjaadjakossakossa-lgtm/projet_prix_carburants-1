# Choix des sources de données

**Date** : 2026-10-21
**Statut** : à confirmer avec le professeur

## Contexte

Le professeur a proposé le flux quotidien des prix des carburants sur data.gouv.fr (ressource `336c34b5-a527-4c35-b84d-18462daa7c51`). Le lien donné au départ ne fonctionnant plus, nous avons retrouvé la source exacte, puis cherché une base à croiser : le taux de change EUR/USD de la BCE.

Vérifié le 2026-10-21 : le flux est une **photo de la veille** (dernier prix connu par station, fermetures, ruptures), **sans aucun historique**. Or la question « faire le plein aujourd'hui ou dans 3 jours ? » exige un historique pour entraîner et valider un modèle dans le temps.

## Décision

- **Flux quotidien data.gouv.fr** : référentiel du réseau (stations, coordonnées, fermetures, ruptures) et prix du jour.
- **Taux EUR/USD de la BCE** : seule source de marché.
- **Historique des prix** : archives annuelles du même producteur (donnees.roulez-eco.fr), que la page data.gouv.fr cite comme source du flux.

## Alternatives écartées

| Option | Pourquoi pas |
|---|---|
| Flux seul + BCE | Un seul jour de prix : pas de modèle de prévision ni de validation temporelle, alors que le cahier des charges les exige. |
| Collecter le flux chaque jour à partir de maintenant | Aucun historique exploitable avant la soutenance. C'est en revanche l'évolution naturelle en production. |
| Ajouter le prix du pétrole (Brent) | La version gratuite est publiée avec environ 8 jours de retard, ce qui la rend inutile pour décider au jour le jour. |

## Conséquences

- **Le conseil porte sur aujourd'hui** (lendemain du dernier flux), et pas seulement sur des jours passés rejoués.
- **Une station fermée ou en rupture n'est jamais proposée**, et les stations proches sont comparées sur leurs prix du jour réels.
- **Les coordonnées viennent du flux**, qui est propre : les archives avaient des coordonnées inversées ou manquantes.
- **Risque** : l'historique dépend du domaine donnees.roulez-eco.fr, moins stable que data.gouv.fr.
- **Risque** : le flux change chaque jour. Les métriques sont donc figées par `DATE_FIN_DONNEES` (`backend/config.py`), et seul le conseil du jour évolue.
- **Piège réglé** : les horodatages du flux portent un faux suffixe « +00:00 » alors qu'ils sont en heure locale, comme les archives. Ce suffixe est retiré au chargement.
