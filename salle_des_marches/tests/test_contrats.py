# -*- coding: utf-8 -*-
import datetime as dt

from mgc import calendrier_cme as cal
from mgc.contrats import ContractManager

D = dt.date


def test_dates_du_contrat_decembre_2026(config):
    cm = ContractManager(config)
    assert cm.dernier_jour_negociation(2026, 12) == D(2026, 12, 29)
    assert cm.premier_jour_avis(2026, 12) == D(2026, 11, 30)
    assert cm.date_bascule(2026, 12) == D(2026, 11, 25)
    assert cm.premier_jour_avis(2027, 2) == D(2027, 1, 29)


def test_echeances_cotees(config):
    cm = ContractManager(config)
    assert cm.echeances(D(2026, 10, 17), nombre=4) == [(2026, 10), (2026, 12), (2027, 2), (2027, 4)]
    assert cm.echeances(D(2026, 10, 29), nombre=2) == [(2026, 12), (2027, 2)]  # octobre fini le 28


def test_contrat_actif_aujourd_hui(config):
    etat = ContractManager(config).etat(D(2026, 10, 17))
    assert etat["contrat"] == "MGCZ26"
    assert etat["suivant"] == "MGCG27"
    assert etat["bascule_estimee"] == "2026-11-25"
    assert etat["jours_ouvres_avant_bascule"] == 28
    assert etat["restriction_rollover"] is False
    assert etat["motif_restriction"] == ""


def test_restriction_5_jours_avant_la_bascule(config):
    cm = ContractManager(config)
    assert cm.etat(D(2026, 11, 17))["restriction_rollover"] is False  # 6 jours ouvrés
    etat = cm.etat(D(2026, 11, 18))                                  # 5 jours ouvrés
    assert etat["restriction_rollover"] is True
    assert "MGCG27" in etat["motif_restriction"]


def test_apres_la_bascule(config):
    etat = ContractManager(config).etat(D(2026, 11, 25))
    assert etat["contrat"] == "MGCG27"
    assert etat["restriction_rollover"] is False


def test_bascule_constatee_par_les_volumes(config):
    etat = ContractManager(config).etat(D(2026, 11, 10), volumes={"MGCZ26": 100, "MGCG27": 200})
    assert etat["contrat"] == "MGCG27"
    assert etat["suivant"] == "MGCJ27"
    assert "constatée" in etat["choix"]


def test_volumes_normaux_ne_changent_rien(config):
    etat = ContractManager(config).etat(D(2026, 11, 10), volumes={"MGCZ26": 2_000_000, "MGCG27": 40_000})
    assert etat["contrat"] == "MGCZ26"


def test_etat_depuis_une_heure_de_chicago(config):
    # dimanche 17h à Chicago : la séance compte pour le lundi
    etat = ContractManager(config).etat(dt.datetime(2026, 11, 22, 17, 0, tzinfo=cal.CHICAGO))
    assert etat["jours_ouvres_avant_bascule"] == 2  # du lundi 23 : 24 et 25
