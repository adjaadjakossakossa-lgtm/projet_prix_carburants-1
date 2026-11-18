"""Construit la base, entraîne les 2 modèles, choisit le modèle de la démo et sauvegarde.

Usage : python -m backend.train
"""
import json
import time

import joblib
import pandas as pd
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import cross_val_score

from backend.config import (
    ANNEES, DOSSIER_HISTORIQUE, FICHIER_FLUX, FICHIER_METRIQUES, FICHIER_MODELE, FICHIER_TAUX, LITRES_PAR_AN,
    PLEINS_PAR_AN, RAYON_KM, REPORT_MAX_JOURS,
)
from backend.data import (
    age_dernier_prix, ajouter_cible_et_variables, calculer_variables, charger_brut_dans_sqlite,
    enregistrer_table_analyse, executer_requete_analyse, filtrer_perimetre, lignes_du_jour, lire_stations,
)
from backend.download import chemin_archive, telecharger_tout
from backend.model import (
    CIBLE, MODELES, couts_moyens, couts_references, creer_pipeline, decouper_temporel, evaluer,
    evaluer_choix_station, intervalle_gain, plis_temporels, profils_stations, regret, regret_par_mois,
    regret_toujours_plein, regret_validation_croisee, seuil_optimal,
)


def fichiers_bruts_manquants() -> list:
    fichiers = [chemin_archive(annee, DOSSIER_HISTORIQUE) for annee in ANNEES] + [FICHIER_FLUX, FICHIER_TAUX]
    return [fichier for fichier in fichiers if not fichier.exists()]


def en_euros_par_an(gain_c_l: dict) -> dict:
    """Ajoute l'économie annuelle de la flotte fictive (€) à un gain moyen en c€/L."""
    return {**gain_c_l, "economie_annuelle_euros": gain_c_l["moyenne"] / 100 * LITRES_PAR_AN}


def qualite_reseau(stations: pd.DataFrame, grille: pd.DataFrame, jour_conseil: str) -> dict:
    """Diagnostic du périmètre : état du réseau le jour du conseil (flux) et trous de l'historique (grille)."""
    perimetre = filtrer_perimetre(stations)
    age = age_dernier_prix(perimetre, jour_conseil)
    historiques = grille["station"].drop_duplicates()
    return {
        "jour_conseil": jour_conseil,
        "stations_flux": int(len(perimetre)),
        "stations_fermees": int(perimetre["fermee"].sum()),
        "stations_en_rupture": int(perimetre["rupture"].sum()),
        "stations_sans_prix": int(perimetre["prix_jour"].isna().sum()),
        "stations_prix_perime": int((age > REPORT_MAX_JOURS).sum()),
        "stations_historique": int(len(historiques)),
        "stations_historique_absentes_du_flux": int((~historiques.isin(stations["station"])).sum()),
        "part_station_jour_sans_prix": float(grille["prix"].isna().mean()),
    }


def construire_tables() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Télécharge les fichiers manquants, charge SQLite, construit et enregistre la table d'analyse et
    les lignes du conseil du jour. Renvoie (table d'analyse, grille SQL brute, comptes du chargement)."""
    if fichiers_bruts_manquants():
        telecharger_tout()
    comptes = charger_brut_dans_sqlite()
    grille = executer_requete_analyse()
    table = ajouter_cible_et_variables(grille)
    enregistrer_table_analyse(table)
    enregistrer_table_analyse(lignes_du_jour(calculer_variables(grille), comptes["jour_conseil"]), nom="table_jour")
    return table, grille, comptes


def entrainer_modele(variables, entrainement, test, seuil: float) -> tuple:
    """AUC et regret en validation croisée temporelle sur l'entraînement, ajustement, évaluation sur le test.
    Renvoie le pipeline, ses métriques et le regret de chaque ligne de test (c€/L)."""
    pipeline = creer_pipeline()
    auc_cv = cross_val_score(
        pipeline, entrainement[variables], entrainement[CIBLE], cv=plis_temporels(entrainement["jour"]), scoring="roc_auc",
    )
    pipeline.fit(entrainement[variables], entrainement[CIBLE])
    resultat = evaluer(pipeline, test[variables], test[CIBLE], test["variation_future"], seuil)
    proba = pipeline.predict_proba(test[variables])[:, 1]
    regrets = regret(test["variation_future"], proba > seuil)
    resultat.update({
        "roc_auc_cv_moyenne": float(auc_cv.mean()),
        "roc_auc_cv_ecart_type": float(auc_cv.std()),
        "regret_cv": regret_validation_croisee(entrainement, variables),
        "part_plein_modele": float((proba > seuil).mean()),
        # Fiabilité des probabilités, dont dépend le seuil issu des coûts (diagnostic, non optimisé).
        "brier": float(brier_score_loss(test[CIBLE], proba)),
        "gain_vs_plein": en_euros_par_an(
            intervalle_gain(test["jour"], regret_toujours_plein(test["variation_future"]), regrets)
        ),
    })
    return pipeline, resultat, regrets


def entrainer_les_modeles(entrainement, test, seuil: float) -> tuple[dict, dict, dict, str]:
    """Entraîne chaque modèle de MODELES. Renvoie (pipelines, métriques, regrets du test, nom du retenu).
    Modèle retenu : le plus petit regret en validation croisée sur l'entraînement, jamais le test."""
    pipelines, modeles, regrets = {}, {}, {}
    for nom, variables in MODELES.items():
        pipelines[nom], modeles[nom], regrets[nom] = entrainer_modele(variables, entrainement, test, seuil)
    retenu = min(modeles, key=lambda nom: modeles[nom]["regret_cv"])
    return pipelines, modeles, regrets, retenu


def evaluer_choix_de_station(entrainement, test, stations: pd.DataFrame) -> dict:
    """Choix de la station : alternatives apprises sur l'entraînement, gain mesuré sur le test."""
    prix_litre = float(test["prix"].median())
    ecarts = profils_stations(entrainement)["prix_relatif"], profils_stations(test)["prix_relatif"]
    return {
        "rayon_km": RAYON_KM,
        "prix_litre": prix_litre,
        "avec_detour": evaluer_choix_station(stations, *ecarts, prix_litre, avec_detour=True),
        "sur_tournee": evaluer_choix_station(stations, *ecarts, prix_litre, avec_detour=False),
    }


def sauvegarder(pipeline, metriques: dict) -> None:
    FICHIER_MODELE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, FICHIER_MODELE)
    FICHIER_METRIQUES.write_text(json.dumps(metriques, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> dict:
    table, grille, comptes = construire_tables()
    entrainement, test = decouper_temporel(table)
    hausse_moyenne, baisse_moyenne = couts_moyens(entrainement["variation_future"], entrainement[CIBLE])
    seuil = seuil_optimal(hausse_moyenne, baisse_moyenne)
    pipelines, modeles, regrets, retenu = entrainer_les_modeles(entrainement, test, seuil)
    stations = lire_stations()
    metriques = {
        "nb_stations": int(table["station"].nunique()),
        "nb_lignes_entrainement": int(len(entrainement)),
        "nb_lignes_test": int(len(test)),
        "debut_test": str(test["jour"].min()),
        "fin_test": str(test["jour"].max()),
        "taux_hausse": float(entrainement[CIBLE].mean()),
        "hausse_moyenne_c": hausse_moyenne,
        "baisse_moyenne_c": baisse_moyenne,
        "seuil": float(seuil),
        "litres_par_an": int(LITRES_PAR_AN),
        "pleins_par_an": int(PLEINS_PAR_AN),
        "chargement": comptes,
        "qualite": qualite_reseau(stations, grille, comptes["jour_conseil"]),
        "choix_station": evaluer_choix_de_station(entrainement, test, stations),
        "couts": couts_references(test["variation_future"]),
        "modeles": modeles,
        "modele_retenu": retenu,
        "economie_annuelle_euros": modeles[retenu]["gain_vs_plein"]["economie_annuelle_euros"],
        "regret_par_mois": regret_par_mois(
            test["jour"], {"toujours_plein": regret_toujours_plein(test["variation_future"]), **regrets}
        ),
        # Ce qu'apporte le croisement avec le taux BCE au modèle qui ne voit que les prix.
        "valeur_taux_bce": en_euros_par_an(
            intervalle_gain(test["jour"], regrets["prix_seuls"], regrets["prix_et_taux"])
        ),
    }
    sauvegarder(pipelines[retenu], metriques)
    return metriques


def afficher_resume(resultats: dict) -> None:
    print(f"Test du {resultats['debut_test']} au {resultats['fin_test']} "
          f"({resultats['nb_lignes_test']} lignes), seuil {resultats['seuil']:.3f}")
    for nom, perf in resultats["modeles"].items():
        print(f"{nom} : ROC-AUC test {perf['roc_auc']:.3f} "
              f"(CV : {perf['roc_auc_cv_moyenne']:.3f} ± {perf['roc_auc_cv_ecart_type']:.3f}), "
              f"coût {perf['cout_moyen_modele']:.3f} c€/L (seuil 0,5 : {perf['cout_moyen_seuil_05']:.3f}), "
              f"regret CV {perf['regret_cv']:.3f}, plein conseillé {perf['part_plein_modele']:.1%} du temps")
    couts = resultats["couts"]
    print(f"Coût moyen c€/L. Toujours plein : {couts['toujours_plein']:.3f}, "
          f"toujours attendre : {couts['toujours_attendre']:.3f}, oracle : {couts['oracle']:.3f}")
    gain = resultats["modeles"][resultats["modele_retenu"]]["gain_vs_plein"]
    apport_bce = resultats["valeur_taux_bce"]
    print(f"Modèle retenu (validation croisée) : {resultats['modele_retenu']}, économie annuelle "
          f"{gain['economie_annuelle_euros']:.0f} € "
          f"(gain {gain['moyenne']:.2f} c€/L, IC 95 % {gain['bas']:.2f} à {gain['haut']:.2f})")
    print(f"Apport du taux BCE : {apport_bce['economie_annuelle_euros']:.0f} € "
          f"(gain {apport_bce['moyenne']:.2f} c€/L, IC 95 % {apport_bce['bas']:.2f} à {apport_bce['haut']:.2f})")
    print(f"Conseil du jour : {resultats['qualite']['jour_conseil']}")
    print(f"Modèle sauvegardé : {FICHIER_MODELE}")


if __name__ == "__main__":
    debut = time.time()
    afficher_resume(main())
    print(f"Durée : {time.time() - debut:.0f} s")
