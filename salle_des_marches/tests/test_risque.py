# -*- coding: utf-8 -*-
from mgc import risque


def test_achat_exemple_complet(config):
    r = risque.evaluer("achat", 4200.0, 4195.0, 4230.0, config)
    assert r["distance_ticks"] == 50
    assert r["risque_brut_par_contrat"] == 50.0
    assert r["couts_par_contrat"] == 3.5            # 1,50 $ de frais + 2 ticks de glissement
    assert r["risque_net_par_contrat"] == 53.5
    assert r["risque_autorise"] == 500.0            # 1 % de 50 000 $
    assert r["contrats"] == 9                       # 500 / 53,5 = 9,3 -> 9 (jamais au-dessus)
    assert r["risque_total_net"] == 481.5
    assert r["ratio_net_tp1"] == 5.54               # (300 - 3,5) / 53,5
    assert "bougie d'entrée clôture en gain" in r["gestion_stop"]   # règles du 23/10 (plus de break-even à 35 %)
    assert r["exploitable"] is True
    assert r["vetos"] == []


def test_vente_symetrique(config):
    r = risque.evaluer("vente", 4200.0, 4205.0, 4170.0, config)
    assert r["contrats"] == 9
    assert r["exploitable"] is True


def test_reste_de_la_limite_du_jour(config):
    r = risque.evaluer("achat", 4200.0, 4195.0, 4230.0, config, perte_du_jour_usd=900)
    assert r["reste_limite_jour"] == 100.0
    assert r["contrats"] == 1


def test_limite_du_jour_atteinte(config):
    r = risque.evaluer("achat", 4200.0, 4195.0, 4230.0, config, perte_du_jour_usd=1000)
    assert r["exploitable"] is False
    assert r["contrats"] == 0
    assert any("Limite de perte du jour" in v for v in r["vetos"])


def test_un_gain_ne_rajoute_pas_de_marge(config):
    r = risque.evaluer("achat", 4200.0, 4195.0, 4230.0, config, perte_du_jour_usd=-300)
    assert r["reste_limite_jour"] == 1000.0


def test_moins_d_un_contrat_bloque(config):
    r = risque.evaluer("achat", 4200.0, 4150.0, 4400.0, config)  # 50 points = 503,50 $ net > 500 $
    assert r["contrats"] == 0
    assert r["exploitable"] is False
    assert any("Moins d'un contrat" in v for v in r["vetos"])


def test_stop_incoherent(config):
    r = risque.evaluer("achat", 4200.0, 4205.0, 4230.0, config)
    assert r["exploitable"] is False
    assert any("Stop incohérent" in v for v in r["vetos"])
    r = risque.evaluer("vente", 4200.0, 4205.0, 4230.0, config)
    assert any("Stop incohérent" in v for v in r["vetos"])


def test_ratio_insuffisant(config):
    r = risque.evaluer("achat", 4200.0, 4195.0, 4205.0, config)  # (50 - 3,5) / 53,5 = 0,87
    assert r["ratio_net_tp1"] == 0.87
    assert r["exploitable"] is False
    assert any("Ratio" in v for v in r["vetos"])


def test_prix_hors_grille_et_sens_inconnu(config):
    assert risque.evaluer("achat", 4200.05, 4195.0, 4230.0, config)["exploitable"] is False
    assert risque.evaluer("achat", None, 4195.0, 4230.0, config)["exploitable"] is False
    r = risque.evaluer("long", 4200.0, 4195.0, 4230.0, config)
    assert r["exploitable"] is False and r["contrats"] == 0


def test_plafond_de_contrats(config):
    config["max_contrats"] = 3
    r = risque.evaluer("achat", 4200.0, 4199.0, 4230.0, config)  # 13,50 $ net -> 37 contrats calculés
    assert r["contrats"] == 3
    assert r["plafonne"] is True


def test_frais_et_glissement_configurables(config):
    config["frais_aller_retour_usd"] = 0.0
    config["glissement_ticks_par_cote"] = 0
    r = risque.evaluer("achat", 4200.0, 4195.0, 4230.0, config)
    assert r["risque_net_par_contrat"] == 50.0
    assert r["contrats"] == 10
