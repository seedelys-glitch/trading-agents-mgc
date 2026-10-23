# -*- coding: utf-8 -*-
import datetime as dt

import pytest

from mgc import annonces, vetos
from mgc import calendrier_cme as cal
from mgc.contrats import ContractManager


def paris(*args):
    return dt.datetime(*args, tzinfo=cal.PARIS)


@pytest.mark.parametrize("titre, impact, genre", [
    ("Fed Chairman Warsh Speaks", "High", "discours_fed"),  # le faux « FOMC » du 16/10/2026
    ("Fed Chair Powell Speaks", "High", "discours_fed"),
    ("FOMC Statement", "High", "reunion_fomc"),
    ("Federal Funds Rate", "High", "reunion_fomc"),
    ("FOMC Press Conference", "High", "reunion_fomc"),
    ("FOMC Member Hammack Speaks", "Low", "autre"),
    ("FOMC Meeting Minutes", "High", "forte"),
    ("CPI m/m", "High", "forte"),
    ("Retail Sales m/m", "Medium", "autre"),
])
def test_classement(titre, impact, genre):
    assert annonces.classer(titre, impact) == genre


def test_jour_de_reunion_fomc_bloque_toute_la_journee(config):
    liste = [{"quand": paris(2026, 10, 28, 20, 0), "titre": "FOMC Statement", "impact": "High"}]
    assert annonces.blocages(paris(2026, 10, 28, 9, 0), liste, config)
    assert annonces.blocages(paris(2026, 10, 27, 16, 0), liste, config) == []


def test_discours_du_president_30_minutes(config):
    liste = [{"quand": paris(2026, 10, 16, 5, 30), "titre": "Fed Chairman Warsh Speaks", "impact": "High"}]
    assert annonces.blocages(paris(2026, 10, 16, 5, 0), liste, config)
    assert annonces.blocages(paris(2026, 10, 16, 6, 0), liste, config)
    assert annonces.blocages(paris(2026, 10, 16, 6, 1), liste, config) == []
    assert annonces.blocages(paris(2026, 10, 16, 16, 0), liste, config) == []  # l'après-midi reste libre


def test_annonce_forte_90_avant_30_apres(config):
    liste = [{"quand": paris(2026, 10, 20, 14, 30), "titre": "CPI m/m", "impact": "High"}]
    assert annonces.blocages(paris(2026, 10, 20, 12, 59), liste, config) == []
    assert annonces.blocages(paris(2026, 10, 20, 13, 0), liste, config)
    assert annonces.blocages(paris(2026, 10, 20, 15, 0), liste, config)
    assert annonces.blocages(paris(2026, 10, 20, 15, 1), liste, config) == []


def test_vetos_de_contexte(config):
    instant = paris(2026, 10, 20, 16, 0)  # mardi, séance ouverte, dans la fenêtre
    etat = ContractManager(config).etat(instant)
    assert vetos.contexte(instant, config, etat, donnees_temps_reel=True) == []
    motifs = vetos.contexte(instant, config, etat)
    assert len(motifs) == 1 and "différées" in motifs[0]
    assert any("Pause d'urgence" in m for m in vetos.contexte(instant, config, etat, pause=True, donnees_temps_reel=True))
    assert any("non identifié" in m for m in vetos.contexte(instant, config, None, donnees_temps_reel=True))


def test_vetos_hors_fenetre_et_marche_ferme(config):
    samedi = paris(2026, 10, 17, 16, 0)
    motifs = vetos.contexte(samedi, config, ContractManager(config).etat(samedi), donnees_temps_reel=True)
    assert any("fermé" in m for m in motifs)
    assert any("fenêtre" in m for m in motifs)


def test_veto_rollover(config):
    instant = paris(2026, 11, 18, 16, 0)
    motifs = vetos.contexte(instant, config, ContractManager(config).etat(instant), donnees_temps_reel=True)
    assert any("Rollover" in m for m in motifs)
