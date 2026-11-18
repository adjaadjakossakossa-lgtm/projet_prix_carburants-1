"""Tests de l'interface du backend (modèle et métriques produits par backend.train)."""
import pandas as pd
import pytest

from backend import service


def test_conseiller_refuse_une_station_inconnue(modele_entraine):
    with pytest.raises(ValueError, match="Station inconnue"):
        service.conseiller("0000000", "2026-06-01")


def test_conseiller_refuse_une_date_hors_test(modele_entraine):
    station = service.lister_stations()["station"].iloc[0]
    with pytest.raises(ValueError, match="période de test"):
        service.conseiller(station, "2025-03-01")


def test_conseiller_renvoie_une_decision(modele_entraine):
    station = service.lister_stations()["station"].iloc[0]
    jour = service.jours_disponibles(station)[0]
    r = service.conseiller(station, jour)
    assert 0 <= r["proba_hausse"] <= 1
    assert r["decision"] in {service.DECISION_PLEIN, service.DECISION_ATTENTE}
    assert r["decision"] == (service.DECISION_PLEIN if r["proba_hausse"] > r["seuil"] else service.DECISION_ATTENTE)
    assert r["seuil"] == pytest.approx(service.metriques()["seuil"])


def test_conseil_du_jour_utilise_le_modele_retenu(modele_entraine):
    m = service.metriques()
    for station in service.lister_stations()["station"].iloc[:30]:
        try:
            r = service.conseil_du_jour(station)
        except ValueError as erreur:
            assert "Pas de conseil" in str(erreur)
            continue
        assert r["jour"] == m["qualite"]["jour_conseil"]
        assert r["decision"] == (service.DECISION_PLEIN if r["proba_hausse"] > r["seuil"] else service.DECISION_ATTENTE)
        assert 0.5 < r["taux"] < 2
        return
    pytest.fail("aucun conseil du jour sur 30 stations : vérifier table_jour")


def test_etat_station_vient_du_flux(modele_entraine):
    station = service.lister_stations()["station"].iloc[0]
    etat = service.etat_station(station)
    assert {"prix_jour", "maj_prix_jour", "fermee", "rupture", "automate_24_24", "prix_frais"} <= set(etat)
    with pytest.raises(ValueError, match="Station inconnue"):
        service.etat_station("0000000")


def test_carte_et_croisement_des_sources(modele_entraine):
    carte = service.carte_reseau()
    assert carte["latitude"].between(49.5, 51.5).all() and carte["longitude"].between(1, 4.5).all()
    assert set(carte["etat"]) <= {"ouverte", "prix absent ou périmé", "rupture de gazole", "fermée"}
    serie = service.serie_marche()
    assert list(serie.columns) == ["jour", "gazole", "euro_dollar"]
    assert serie.iloc[0][["gazole", "euro_dollar"]].tolist() == [100, 100]


def test_profils_segments(modele_entraine):
    segments = service.profils_segments(3)
    assert len(segments) == 3
    assert segments["profil"].notna().all()
    assert segments["prix_relatif"].is_monotonic_decreasing  # du plus cher au moins cher
    assert "plus chères" in service.lecture_segments(segments)


def test_nommer_segments_selon_prix_et_rythme():
    resume = pd.DataFrame({"prix_relatif": [7.8, 0.8, -1.4], "changements_par_semaine": [2.8, 1.4, 3.1]})
    assert service.nommer_segments(resume).tolist() == [
        "Stations chères, prix qui bougent souvent",
        "Stations dans la moyenne, prix stables",
        "Stations pas chères, prix qui bougent souvent",
    ]


def test_nommer_segments_avec_deux_segments():
    resume = pd.DataFrame({"prix_relatif": [-2.0, 3.0], "changements_par_semaine": [1.0, 2.0]})
    noms = service.nommer_segments(resume).tolist()
    assert noms[0].startswith("Stations pas chères") and noms[1].startswith("Stations chères")


@pytest.mark.parametrize("bas, haut, attendu", [(-0.19, 0.11, False), (0.06, 0.60, True), (-0.5, -0.1, True)])
def test_ecart_significatif_si_l_intervalle_exclut_zero(bas, haut, attendu):
    assert service.ecart_significatif({"bas": bas, "haut": haut}) is attendu


def test_lecture_comparaison_modeles_reprend_les_vrais_chiffres(modele_entraine):
    m = service.metriques()
    texte = service.lecture_comparaison_modeles()
    assert service.NOMS_MODELES[m["modele_retenu"]] in texte
    assert f"{m['valeur_taux_bce']['bas']:.2f}" in texte
    significatif = service.ecart_significatif(m["valeur_taux_bce"])
    assert ("pas significatif" in texte) is (not significatif)


def test_alternatives_refuse_une_station_inconnue(modele_entraine):
    with pytest.raises(ValueError, match="Station inconnue"):
        service.alternatives("0000000")


def test_alternatives_proches_et_rentables(modele_entraine):
    from backend.config import NB_ALTERNATIVES, RAYON_KM

    stations = service.lister_stations()["station"]
    resultats = [service.alternatives(s) for s in stations.iloc[:40]]
    non_vides = [r for r in resultats if not r.empty]
    assert non_vides, "aucune alternative sur 40 stations : vérifier les coordonnées"
    for r in non_vides:
        assert {"station", "ville", "adresse", "prix_jour", "distance_km", "gain_c_l", "gain_plein_euros"} <= set(r.columns)
        assert not r["station"].isin(service.carte_reseau().query("etat != 'ouverte'")["station"]).any()
        assert len(r) <= NB_ALTERNATIVES
        assert (r["distance_km"] <= RAYON_KM).all() and (r["gain_plein_euros"] > 0).all()
        assert r["gain_plein_euros"].is_monotonic_decreasing


def test_importance_variables_en_clair_et_triees(modele_entraine):
    importances = service.importance_variables()
    assert len(importances) <= 8
    assert importances["importance"].is_monotonic_decreasing
    assert not importances["variable"].str.contains("_").any()  # aucun nom technique


def test_carte_sans_coordonnees_aberrantes(modele_entraine):
    carte = service.carte_reseau()
    assert (carte["latitude"] - carte["latitude"].median()).abs().max() <= 2
    assert (carte["longitude"] - carte["longitude"].median()).abs().max() <= 2
