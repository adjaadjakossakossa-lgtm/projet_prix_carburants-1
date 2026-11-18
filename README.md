# Aide au plein de la flotte : faire le plein aujourd'hui ou dans 3 jours ?

Projet de data mining · Équipe : Hervé Adjakossa, Liam Arnault, Antoine Pholulamdeth, Samuel Sidoli

## La question business

Une PME de livraison du Nord (client fictif : 40 utilitaires diesel, un plein par semaine) veut savoir, chaque matin et pour une station donnée, **s'il vaut mieux faire le plein aujourd'hui ou attendre 3 jours**, et s'il existe tout près une station ouverte et moins chère.

## Les données

- **Le flux quotidien des prix des carburants** ([data.gouv.fr](https://explore.data.gouv.fr/fr/datasets/6615d83d7d7c66d5ec00c511/#/resources/336c34b5-a527-4c35-b84d-18462daa7c51), Licence Ouverte), proposé par le professeur : l'état du réseau chaque jour (stations ouvertes, fermées, en rupture) et le dernier prix connu.
- **Les archives annuelles du même producteur**, pour l'historique des prix, que le flux ne garde pas.
- **Le taux euro-dollar de la BCE** ([API BCE](https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata&startPeriod=2024-12-01)), croisé avec les prix, car le pétrole se paie en dollars.

Périmètre : gazole, départements 59 et 62, stations hors autoroute. Le choix des sources est expliqué dans [`docs/adr/choix_des_sources.md`](docs/adr/choix_des_sources.md).

## Les résultats

> **Chiffres de l'entraînement du 18/11/2026.** La période étudiée est fixe (test du 04/05 au 16/10/2026), mais la source met à jour ses archives : un nouveau téléchargement peut faire varier légèrement les chiffres.

Le « regret » mesure le surcoût d'une décision : le prix payé moins le meilleur des deux prix (aujourd'hui ou dans 3 jours), en centimes par litre. Plus il est bas, mieux c'est. Mesuré sur 55 282 jours-stations que le modèle n'a jamais vus.

| Stratégie | Regret moyen (c€/L) | Gain par rapport à aujourd'hui |
|---|---|---|
| **Baseline** : toujours faire le plein tout de suite (situation actuelle) | 1,24 | — |
| Toujours attendre 3 jours | 1,60 | perte |
| Modèle prix seuls | 0,91 | ≈ 420 €/an |
| **Modèle prix + taux BCE : modèle de l'application** | **0,95** | **≈ 365 €/an** (0,29 c€/L, IC 95 % : 0,06 à 0,60) |
| Plafond : connaître l'avenir | 0,00 | ≈ 1 550 €/an |

- **Le modèle fait gagner environ 365 € par an** à la flotte : un gain réel mais modeste.
- **Le taux BCE n'apporte rien de mesurable.** Le modèle de l'application a été choisi sur l'entraînement, avant de regarder le test (validation croisée : 0,59 contre 0,62 c€/L). Sur le test, il fait un peu moins bien que le modèle prix seuls, mais l'écart n'est pas significatif (−0,04 c€/L, IC 95 % : −0,19 à 0,11).
- **Le seuil de décision vient des coûts** : attendre alors que le prix monte coûte 3,25 c€/L en moyenne, faire le plein alors qu'il ne monte pas coûte 1,16 c€/L. On fait donc le plein dès que la probabilité de hausse dépasse 0,26.
- **Choisir la bonne station pèse plus que choisir le bon jour** : jusqu'à ≈ 2 780 €/an si une station moins chère est déjà sur la tournée, mais seulement ≈ 70 €/an s'il faut faire un détour.
- **Trois profils de stations** (K-means) : les 67 stations « chères » sont en moyenne 7,8 c€/L au-dessus de la médiane de leur département.

Le détail est dans la [Model Card](docs/model_card.md) et la [note de synthèse](docs/note_synthese.md).

Les slides (`docs/soutenance.pdf`) sont celles présentées en soutenance, avec les chiffres de l'entraînement de l'époque (≈ 360 €/an). Les chiffres de ce README viennent d'un entraînement plus récent (≈ 365 €/an) : l'écart vient de la mise à jour des archives par la source.

## Lancer le projet

Dans un environnement virtuel (`python -m venv .venv`, puis `.venv\Scripts\Activate.ps1` sous Windows ou `source .venv/bin/activate` sous Linux et macOS) :

```bash
pip install -r requirements.txt
python -m backend.train
python -m pytest
python -m streamlit run frontend/app.py
```

`python -m backend.train` télécharge les données (environ 150 Mo, connexion Internet nécessaire), construit la base, entraîne les modèles et sauvegarde les résultats. Il prend quelques minutes la première fois. Projet testé avec Python 3.13.

## L'application

| Écran | Ce qu'il montre |
|---|---|
| **Décision** | Pour la station choisie : la probabilité de hausse, le conseil (faire le plein ou attendre), et les stations moins chères à moins de 5 km |
| **Exploration** | La carte du réseau du jour, le croisement gazole et euro-dollar, les profils de stations |
| **Le modèle** | Les performances face aux stratégies simples, le gain par mois, les variables les plus utiles, les limites |

## Architecture

```
backend/                 logique métier (aucun import de streamlit)
  config.py              chemins, sources, périmètre, hypothèses de flotte, réglages du modèle
  download.py            téléchargement des données
  sql/schema.sql         schéma de la base SQLite
  sql/table_analyse.sql  table d'analyse en SQL : une ligne par station et par jour, sans fuite
  data.py                fichiers bruts -> SQLite -> table d'analyse
  model.py               forêt aléatoire, seuil, regret, K-means, choix de la station
  train.py               entraînement, choix du modèle, sauvegarde
  service.py             SEULE interface appelée par le frontend
frontend/app.py          Streamlit : affichage uniquement
tests/                   tests des données, du modèle, du service et de l'application
docs/                    note de cadrage, Data Quality Card, Model Card, note de synthèse, journal IA
data/raw/                données brutes (téléchargées, non versionnées)
models/                  modèle et résultats de l'entraînement (non versionnés)
```

Le frontend n'appelle que `backend/service.py` : on pourrait remplacer Streamlit sans toucher au backend. Plus de détails dans [`docs/architecture.md`](docs/architecture.md).

## Limites

- **Le gain est modeste et dépend du marché.** Il vient surtout de mai et juin 2026, quand les prix redescendaient. En juillet, quand ils montaient, le modèle a fait un peu moins bien que « toujours faire le plein ».
- **Une seule période de test**, pendant une crise des prix : rien ne garantit le même gain en période calme.
- **Le modèle conseille de faire le plein dans 80 % des cas** : il ne fait attendre qu'occasionnellement.
- **Les chiffres bougent légèrement d'un téléchargement à l'autre**, car la source met à jour ses archives.
- **Les données ont des trous** : près de la moitié des couples station × jour n'ont pas de prix de moins de 7 jours.
- **La flotte et les coûts de détour sont fictifs**, et les euros par an en dépendent directement. Les tournées réelles sont inconnues : le détour est estimé à vol d'oiseau × 1,3.
- **Gazole seulement**, Nord et Pas-de-Calais, hors autoroute.
- **Piste non retenue** : le prix du pétrole (Brent) de la veille pourrait améliorer le conseil, mais il demande une source payante. La version gratuite arrive avec 8 jours de retard, ce qui la rend inutile.
- L'outil est une aide à la décision : le gestionnaire garde la décision finale.

## Retours du COMEX et ce que nous avons changé

| Retour | Ce que nous avons changé |
|---|---|
| Le projet pourrait intéresser au-delà du client ; l'élargir à d'autres régions que le Nord et le Pas-de-Calais | Non fait dans ce rendu, faute de temps et de puissance de calcul. Le code le permet déjà : le périmètre est un réglage (`DEPARTEMENTS` dans `backend/config.py`), sans rien changer d'autre. Passer à une région comme le Grand Est demande seulement plus de temps d'entraînement ; pour toute la France, il faudrait une machine plus puissante. |
