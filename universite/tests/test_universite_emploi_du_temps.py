# -*- coding: utf-8 -*-
"""Emploi du temps des agents (31/10) : la tournée du directeur confie le travail en retard, rien d'inventé."""

import datetime as dt

import pytest
from aides_universite import DEBUT, bougies_m1, executer_tout

from universite import config, donnees
from universite.competences import synthese_directeur, tournee_directeur as td
from universite.serveur import Universite


@pytest.fixture
def univ(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DEFAUTS, "ia_commentaires", False)
    monkeypatch.setattr(td, "rafraichir_yahoo", lambda base: {"jeu": None, "ajoutees": 0})
    u = Universite(tmp_path, demarrer_moteur=False)
    yield u
    u.arreter()


def tournee(u):
    m = u.base.nouvelle_mission(14, td.TYPE, td.TITRE, {}, "test")
    mission = u.base.mission(m)
    u.base.ecrire("UPDATE missions SET statut='en_cours' WHERE id=?", (m,))
    u.moteur.executer(u.base.mission(m))
    return u.base.mission(m)


def types_en_file(u):
    return sorted(r["type"] for r in u.base.lire("SELECT type FROM missions WHERE statut='en_attente'"))


def test_boucle_creee_une_seule_fois(univ):
    assert univ.base.un("SELECT COUNT(*) AS n FROM boucles WHERE genre=?", (td.TYPE,))["n"] == 1
    assert td.assurer_boucle(univ.moteur) is None


def test_marche_ouvert_tout_est_confie(univ, monkeypatch):
    jeu = donnees.creer_jeu(univ.base, "test", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(univ.base, jeu, "M1", bougies_m1(2 * 1440))
    monkeypatch.setattr(td, "maintenant", lambda: DEBUT + 2 * 86400)       # mardi 20/10, 0 h à Paris
    monkeypatch.setattr(td, "seance", lambda t: "ouverte")
    m = tournee(univ)
    assert m["statut"] == "terminee"
    attendus = sorted(td.PLANNING)
    assert types_en_file(univ) == attendus
    jeux = {r["params"].get("jeu") for r in univ.base.lire("SELECT params FROM missions WHERE statut='en_attente'")
            if isinstance(r["params"], dict)}
    assert jeu in jeux
    # deuxième tournée tout de suite : rien de nouveau (déjà dans la file)
    tournee(univ)
    assert types_en_file(univ) == attendus


def test_marche_ferme_pas_d_analyse_technique(univ, monkeypatch):
    jeu = donnees.creer_jeu(univ.base, "test", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(univ.base, jeu, "M1", bougies_m1(1440))
    monkeypatch.setattr(td, "maintenant", lambda: DEBUT - 86400)
    monkeypatch.setattr(td, "seance", lambda t: "fermée")
    tournee(univ)
    file = types_en_file(univ)
    assert not set(td.ANALYSES) & set(file)
    assert "calendrier_macro" in file and "discours_fed" in file


def test_sans_bougies_rien_qui_en_demande(univ, monkeypatch):
    monkeypatch.setattr(td, "maintenant", lambda: DEBUT)
    monkeypatch.setattr(td, "seance", lambda t: "ouverte")
    m = tournee(univ)
    assert types_en_file(univ) == ["calendrier_macro", "cours_du_jour", "discours_fed", "retour_erreurs"]
    assert any("aucune bougie" in s for s in m["resultat"]["sautees"])


def test_synthese_du_jour_apres_15h(univ, monkeypatch):
    t = dt.datetime(2026, 10, 20, 15, 30, tzinfo=td.PARIS).timestamp()
    monkeypatch.setattr(td, "maintenant", lambda: t)
    monkeypatch.setattr(td, "seance", lambda t: "fermée")
    tournee(univ)
    assert "synthese_directeur" in types_en_file(univ)
    executer_tout(univ.moteur)
    assert univ.base.un("SELECT statut FROM missions WHERE type='synthese_directeur'")["statut"] == "terminee"


@pytest.mark.parametrize("valeur, attendu", [("12H", 12), ("12 h", 12), ("24 heures", 24), (48, 48), ("", 24),
                                             (None, 24), ("1,5", 1.5)])
def test_synthese_lit_les_heures(valeur, attendu):
    assert synthese_directeur.lire_heures(valeur) == attendu


def test_yahoo_garde_le_meme_jeu(univ):
    import pandas as pd
    import sys
    config.salle_importable()
    from mgc import sources

    def faux(contrat, chargeur):
        i = pd.DatetimeIndex([pd.Timestamp(DEBUT + 60 * k, unit="s", tz="UTC") for k in range(5)])
        df = pd.DataFrame({"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 3.0}, index=i)
        return {"M1": df}

    sauve = sources.charger_yahoo
    sources.charger_yahoo = faux
    try:
        a = donnees.importer_yahoo(univ.base, "MGCZ26")
        b = donnees.importer_yahoo(univ.base, "MGCZ26")
    finally:
        sources.charger_yahoo = sauve
    assert a["jeu"] == b["jeu"] and a["ajoutees"] == 5 and b["ajoutees"] == 0
