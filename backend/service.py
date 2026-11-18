"""Interface du backend : le frontend n'appelle que ces fonctions."""
import json
from functools import lru_cache

import joblib
import pandas as pd

from backend.config import (
    ECART_MAX_CARTE_DEGRES, FICHIER_METRIQUES, FICHIER_MODELE, HORIZON_JOURS, LITRES_PAR_PLEIN, NB_SEGMENTS,
    REPORT_MAX_JOURS, ZOOM_CARTE,
)
from backend.data import age_dernier_prix, filtrer_perimetre, lire_stations, lire_table_enregistree
from backend.model import MODELES, VARIABLES_PROFIL, alternatives_station, profils_stations, segmenter

DECISION_PLEIN = "faire le plein"
DECISION_ATTENTE = f"attendre {HORIZON_JOURS} jours"
NOMS_MODELES = {"prix_seuls": "prix seuls", "prix_et_taux": "prix + taux BCE"}
LIBELLES_VARIABLES = {
    "prix": "Prix du jour",
    "var_prix_1j": "Variation du prix sur 1 jour",
    "var_prix_3j": "Variation du prix sur 3 jours",
    "var_prix_7j": "Variation du prix sur 7 jours",
    "ecart_mediane_dep": "Écart au prix médian du département",
    "var_mediane_dep_7j": "Variation du prix médian du département sur 7 jours",
    "jours_depuis_changement": "Jours depuis le dernier changement de prix",
    "age_prix_jours": "Âge du dernier prix connu (jours)",
    "jour_semaine": "Jour de la semaine",
    "var_taux_1j": "Variation de l'euro-dollar sur 1 jour",
    "var_taux_3j": "Variation de l'euro-dollar sur 3 jours",
    "var_taux_7j": "Variation de l'euro-dollar sur 7 jours",
}


@lru_cache(maxsize=1)
def _modele():
    if not FICHIER_MODELE.exists():
        raise FileNotFoundError("Modèle absent. Lancer d'abord : python -m backend.train")
    # joblib = pickle : ne charger que le modèle produit par notre propre backend.train.
    return joblib.load(FICHIER_MODELE)


def metriques() -> dict:
    if not FICHIER_METRIQUES.exists():
        raise FileNotFoundError("Métriques absentes. Lancer d'abord : python -m backend.train")
    return json.loads(FICHIER_METRIQUES.read_text(encoding="utf-8"))


def _variables() -> list[str]:
    return MODELES[metriques()["modele_retenu"]]


@lru_cache(maxsize=1)
def _table_test() -> pd.DataFrame:
    """Lignes de la table d'analyse enregistrée à partir du début de la période de test."""
    table = lire_table_enregistree()
    return table[table["jour"] >= metriques()["debut_test"]].reset_index(drop=True)


@lru_cache(maxsize=1)
def _reseau() -> pd.DataFrame:
    """Stations du périmètre dans le flux quotidien, avec leur état le jour du conseil."""
    perimetre = filtrer_perimetre(lire_stations()).copy()
    age = age_dernier_prix(perimetre, metriques()["qualite"]["jour_conseil"])
    perimetre["prix_frais"] = perimetre["prix_jour"].notna() & (age <= REPORT_MAX_JOURS)
    return perimetre.reset_index(drop=True)


def _verifier(station: str) -> None:
    if station not in set(lister_stations()["station"]):
        raise ValueError(f"Station inconnue : {station}")


def lister_stations() -> pd.DataFrame:
    """Stations du périmètre présentes dans le flux du jour et dans la période de test :
    station, ville, adresse, cp (triées par ville)."""
    reseau = _reseau()
    presentes = reseau[reseau["station"].isin(_table_test()["station"].unique())]
    colonnes = ["station", "ville", "adresse", "cp"]
    return presentes[colonnes].sort_values(["ville", "adresse"]).reset_index(drop=True)


def etat_station(station: str) -> dict:
    """État de la station dans le flux du jour : prix (€/L), date du prix, fermeture, rupture, automate."""
    _verifier(station)
    ligne = _reseau().set_index("station").loc[station]
    return {
        "jour_conseil": metriques()["qualite"]["jour_conseil"],
        "prix_jour": None if pd.isna(ligne["prix_jour"]) else float(ligne["prix_jour"]),
        "maj_prix_jour": None if pd.isna(ligne["maj_prix_jour"]) else str(ligne["maj_prix_jour"]),
        "prix_frais": bool(ligne["prix_frais"]),
        "fermee": bool(ligne["fermee"]),
        "rupture": bool(ligne["rupture"]),
        "automate_24_24": bool(ligne["automate_24_24"]),
    }


def _decision(lignes: pd.DataFrame, station: str, jour: str) -> dict:
    proba = float(_modele().predict_proba(lignes.iloc[[0]][_variables()])[0, 1])
    seuil = float(metriques()["seuil"])
    return {
        "station": str(station),
        "jour": str(jour),
        "prix": float(lignes["prix"].iloc[0]),
        "taux": float(lignes["taux"].iloc[0]),
        "proba_hausse": proba,
        "seuil": seuil,
        "decision": DECISION_PLEIN if proba > seuil else DECISION_ATTENTE,
        "modele": NOMS_MODELES[metriques()["modele_retenu"]],
    }


def conseil_du_jour(station: str) -> dict:
    """Conseil pour le jour du conseil (lendemain du dernier flux), à partir des prix connus à midi."""
    _verifier(station)
    jour = metriques()["qualite"]["jour_conseil"]
    table = lire_table_enregistree(nom="table_jour")
    lignes = table[table["station"] == station]
    if lignes.empty:
        raise ValueError(
            f"Pas de conseil le {jour} pour cette station : historique de prix incomplet "
            f"(aucun prix depuis plus de {REPORT_MAX_JOURS} jours, ou série trop courte)."
        )
    return _decision(lignes, station, jour)


def conseiller(station: str, jour: str) -> dict:
    """Rejoue la décision d'un jour de la période de test (probabilité de hausse à HORIZON_JOURS jours et décision)."""
    table = _table_test()
    if station not in set(table["station"]):
        raise ValueError(f"Station inconnue : {station}")
    lignes = table[(table["station"] == station) & (table["jour"] == jour)]
    if lignes.empty:
        periode = metriques()
        raise ValueError(
            f"Pas de donnée pour {station} le {jour} "
            f"(période de test : {periode['debut_test']} à {periode['fin_test']})"
        )
    return _decision(lignes, station, jour)


def jours_disponibles(station: str) -> list[str]:
    """Jours de la période de test où la station a une ligne, du plus ancien au plus récent."""
    table = _table_test()
    return sorted(table.loc[table["station"] == station, "jour"])


def historique_prix(station: str) -> pd.DataFrame:
    """Prix (€/L) de la station sur la période de test : colonnes jour, prix."""
    table = _table_test()
    return table.loc[table["station"] == station, ["jour", "prix"]].sort_values("jour").reset_index(drop=True)


def alternatives(station: str) -> pd.DataFrame:
    """Top-N des stations proches moins chères aujourd'hui (prix du flux), au gain par plein positif une
    fois le détour payé. Seules les stations ouvertes, sans rupture et au prix frais sont proposées.
    Colonnes : station, ville, adresse, prix_jour, distance_km, gain_c_l, gain_plein_euros."""
    _verifier(station)
    reseau = _reseau()
    colonnes = ["station", "ville", "adresse", "prix_jour", "distance_km", "gain_c_l", "gain_plein_euros"]
    origine = reseau[reseau["station"] == station]
    if not origine["prix_frais"].iloc[0]:
        return pd.DataFrame(columns=colonnes)
    candidates = reseau[reseau["prix_frais"] & (reseau["fermee"] == 0) & (reseau["rupture"] == 0)]
    positions = pd.concat([origine, candidates[candidates["station"] != station]])
    # Écart en c€/L entre deux prix du jour : le prix lui-même, en centimes.
    prix_c = positions.set_index("station")["prix_jour"] * 100
    top = alternatives_station(positions, prix_c, station, float(origine["prix_jour"].iloc[0]))
    top = top.merge(reseau[["station", "ville", "adresse", "prix_jour"]], on="station", how="left")
    return top[colonnes].round({"distance_km": 1, "gain_c_l": 1, "gain_plein_euros": 2})


def carte_reseau() -> pd.DataFrame:
    """Stations du périmètre avec position, prix du jour et état : pour la carte de l'exploration.
    Les stations aux coordonnées aberrantes (loin de la position médiane du réseau) sont écartées."""
    reseau = _reseau().dropna(subset=["latitude", "longitude"])
    proches = ((reseau["latitude"] - reseau["latitude"].median()).abs() <= ECART_MAX_CARTE_DEGRES) & (
        (reseau["longitude"] - reseau["longitude"].median()).abs() <= ECART_MAX_CARTE_DEGRES)
    reseau = reseau[proches]
    etat = pd.Series("ouverte", index=reseau.index)
    etat[~reseau["prix_frais"]] = "prix absent ou périmé"
    etat[reseau["rupture"] == 1] = "rupture de gazole"
    etat[reseau["fermee"] == 1] = "fermée"
    colonnes = ["station", "ville", "adresse", "latitude", "longitude", "prix_jour"]
    return reseau[colonnes].assign(etat=etat.to_numpy()).reset_index(drop=True)


def importance_variables(nb: int = 8) -> pd.DataFrame:
    """Les `nb` variables les plus utiles au modèle de la démo (importance par permutation, baisse de
    ROC-AUC), avec un libellé en clair. Colonnes : variable, importance (triée décroissante)."""
    importances = metriques()["modeles"][metriques()["modele_retenu"]]["importance_permutation"]
    table = pd.DataFrame({"variable": list(importances), "importance": list(importances.values())})
    table["variable"] = table["variable"].map(lambda nom: LIBELLES_VARIABLES.get(nom, nom))
    return table.sort_values("importance", ascending=False).head(nb).reset_index(drop=True)


def qualite() -> dict:
    """Diagnostic du réseau et de l'historique calculé par backend.train."""
    return metriques()["qualite"]


def serie_marche() -> pd.DataFrame:
    """Croisement des deux sources, jour par jour : prix médian du gazole du périmètre et taux EUR/USD de
    la BCE (celui connu à midi), en indice 100 au premier jour. Colonnes : jour, gazole, euro_dollar."""
    table = lire_table_enregistree()
    jours = table.groupby("jour").agg(gazole=("prix", "median"), euro_dollar=("taux", "first"))
    return (100 * jours / jours.iloc[0]).round(2).reset_index()


def nommer_segments(resume: pd.DataFrame) -> pd.Series:
    """Nom métier de chaque segment, tiré de ses moyennes (une ligne par segment) :
    - prix : le segment au prix relatif le plus haut est « chères », le plus bas « pas chères »,
      les autres « dans la moyenne » ;
    - rythme : « prix qui bougent souvent » si le segment change de prix au moins aussi souvent que la
      médiane des segments, sinon « prix stables »."""
    rang_prix = resume["prix_relatif"].rank(method="first")
    prix = pd.Series("Stations dans la moyenne", index=resume.index)
    prix[rang_prix == rang_prix.max()] = "Stations chères"
    prix[rang_prix == 1] = "Stations pas chères"
    souvent = resume["changements_par_semaine"] >= resume["changements_par_semaine"].median()
    rythme = souvent.map({True: "prix qui bougent souvent", False: "prix stables"})
    return prix + ", " + rythme


def ecart_significatif(intervalle: dict) -> bool:
    """Vrai si l'intervalle de confiance à 95 % ({"bas", "haut"}) ne contient pas 0."""
    return not intervalle["bas"] <= 0 <= intervalle["haut"]


def profils_segments(k: int = NB_SEGMENTS) -> pd.DataFrame:
    """Profil moyen de chaque segment K-means de stations (table d'analyse entière, descriptif), avec son
    nom métier (colonne `profil`). Trié du segment le plus cher au moins cher."""
    profils = segmenter(profils_stations(lire_table_enregistree()), k)
    resume = profils.groupby("segment")[VARIABLES_PROFIL].mean().round(2)
    resume.insert(0, "effectif", profils["segment"].value_counts().sort_index())
    resume.insert(0, "profil", nommer_segments(resume))
    return resume.sort_values("prix_relatif", ascending=False)


def lecture_segments(resume: pd.DataFrame) -> str:
    """Phrase métier sur l'écart de prix entre le segment le plus cher et le moins cher (sortie de
    `profils_segments`)."""
    cher, pas_cher = resume.iloc[0], resume.iloc[-1]
    ecart_plein = (cher["prix_relatif"] - pas_cher["prix_relatif"]) / 100 * LITRES_PAR_PLEIN
    return (
        f"Les « {cher['profil'].lower()} » ({int(cher['effectif'])} stations) sont en moyenne "
        f"{cher['prix_relatif'] - pas_cher['prix_relatif']:.1f} c€/L plus chères que les "
        f"« {pas_cher['profil'].lower()} » ({int(pas_cher['effectif'])} stations), soit environ "
        f"{ecart_plein:.2f} € par plein de {LITRES_PAR_PLEIN} L. Quand les deux sont sur la tournée, "
        "mieux vaut éviter les premières."
    )


def lecture_comparaison_modeles() -> str:
    """Explique en clair pourquoi le modèle de la démo est retenu et ce qu'apporte le taux BCE."""
    m = metriques()
    retenu = m["modele_retenu"]
    autre = next(nom for nom in NOMS_MODELES if nom != retenu)
    cout_retenu = m["modeles"][retenu]["cout_moyen_modele"]
    cout_autre = m["modeles"][autre]["cout_moyen_modele"]
    bce = m["valeur_taux_bce"]
    texte = (
        f"Le modèle de la démo ({NOMS_MODELES[retenu]}) a été choisi sur l'entraînement seulement, "
        "par validation croisée, avant de regarder le test : c'est la règle pour ne pas tricher. "
    )
    if cout_retenu > cout_autre:
        texte += (
            f"Sur le test, il fait un peu moins bien que le modèle {NOMS_MODELES[autre]} "
            f"({cout_retenu:.3f} contre {cout_autre:.3f} c€/L). "
        )
    else:
        texte += (
            f"Sur le test, il fait aussi bien ou mieux que le modèle {NOMS_MODELES[autre]} "
            f"({cout_retenu:.3f} contre {cout_autre:.3f} c€/L). "
        )
    intervalle = f"{bce['bas']:.2f} à {bce['haut']:.2f} c€/L"
    if not ecart_significatif(bce):
        return texte + (
            f"L'écart n'est pas significatif : l'intervalle à 95 % de l'apport du taux BCE ({intervalle}) "
            "contient 0. En clair, les deux modèles se valent et le taux BCE n'apporte rien de mesurable."
        )
    if bce["moyenne"] > 0:
        return texte + f"Le taux BCE apporte un gain mesurable (intervalle à 95 % : {intervalle})."
    return texte + (
        f"Le taux BCE dégrade le modèle de façon mesurable (intervalle à 95 % : {intervalle}) : "
        "le modèle prix seuls est à préférer."
    )
