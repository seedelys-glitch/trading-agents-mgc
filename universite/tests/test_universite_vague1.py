# -*- coding: utf-8 -*-
"""Vague 1 : SMC (1), Fibonacci (2), Ichimoku (3) contrôlés par reproductibilité, risque (8) recompté par l'agent 9."""

import json

import pytest
from aides_universite import DEBUT, bougies_m1, executer_tout

from universite import donnees
from universite.competences import verification_risque

INSTANT = DEBUT + 4 * 86400 - 600       # fin du jeu de test (4 jours de M1)


@pytest.mark.parametrize("genre, agent", [("analyse_smc", 1), ("analyse_fibo", 2), ("analyse_ichimoku", 3)])
def test_analyse_puis_controle_reproductible(moteur, jeu, genre, agent):
    m = moteur.base.nouvelle_mission(agent, genre, "test", {"jeu": jeu, "instant": INSTANT})
    faites = executer_tout(moteur)
    assert [f["type"] for f in faites] == [genre, "verification_reproductibilite"]
    assert all(f["statut"] == "terminee" for f in faites), [f["erreur"] for f in faites]
    doc = moteur.base.un("SELECT * FROM documents WHERE id=?", (moteur.base.mission(m)["resultat"]["document"],))
    assert doc["statut"] == "verifie" and doc["verifie_par"] == 9
    assert doc["donnees"]["resultat"] and "Aucune bougie postérieure" in doc["contenu"]
    for s in doc["sources"]:                       # seulement des bougies fermées à l'instant
        assert s["fin"] + donnees.PERIODES[s["unite"]] <= INSTANT
    pv = moteur.base.un("SELECT contenu FROM documents WHERE genre='verification'")["contenu"]
    assert "pas un recalcul indépendant" in pv


def test_resultat_trafique_rejete(moteur, jeu):
    m = moteur.base.nouvelle_mission(3, "analyse_ichimoku", "test", {"jeu": jeu, "instant": INSTANT})
    moteur.executer(moteur.base.prendre_mission(["analyse_ichimoku"]))
    ident = moteur.base.mission(m)["resultat"]["document"]
    d = moteur.base.un("SELECT donnees FROM documents WHERE id=?", (ident,))["donnees"]
    d["resultat"]["H1"]["kijun"] += 1
    moteur.base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(d), ident))
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (ident,))["statut"] == "rejete"
    assert moteur.base.lire("SELECT a FROM messages WHERE genre='alerte'") == [{"a": 14}]


@pytest.mark.parametrize("genre", ["analyse_smc", "analyse_fibo", "analyse_ichimoku"])
def test_bougies_futures_sans_effet(base, moteur, genre):
    """Même analyse avec ou sans 2 jours de bougies après l'instant : résultat identique (pas de look-ahead)."""
    toutes = bougies_m1(6 * 1440)
    court = donnees.creer_jeu(base, "court", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(base, court, "M1", [b for b in toutes if b[0] + 60 <= INSTANT])
    long = donnees.creer_jeu(base, "long", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(base, long, "M1", toutes)
    resultats = []
    for j in (court, long):
        m = base.nouvelle_mission(1, genre, "test", {"jeu": j, "instant": INSTANT})
        executer_tout(moteur)
        doc = base.un("SELECT donnees FROM documents WHERE id=?", (base.mission(m)["resultat"]["document"],))
        resultats.append(doc["donnees"]["resultat"])
    assert resultats[0] == resultats[1]


def _risque(moteur, **p):
    m = moteur.base.nouvelle_mission(8, "evaluation_risque", "test", p)
    faites = executer_tout(moteur)
    assert all(f["statut"] == "terminee" for f in faites), [f["erreur"] for f in faites]
    res = moteur.base.mission(m)["resultat"]
    return res, moteur.base.un("SELECT * FROM documents WHERE id=?", (res["document"],))


def test_risque_exploitable_et_recompte(moteur):
    res, doc = _risque(moteur, sens="achat", entree=4000.0, stop=3995.0, tp1=4010.0)
    assert res["exploitable"] and res["contrats"] >= 1
    assert doc["statut"] == "verifie" and doc["verifie_par"] == 9
    assert "Calcul seulement : aucun ordre" in doc["contenu"]
    assert not moteur.base.lire("SELECT * FROM messages WHERE genre='alerte'")


def test_risque_veto_previent_le_directeur(moteur):
    res, doc = _risque(moteur, sens="achat", entree=4000.0, stop=3990.0, tp1=4005.0)     # ratio < 1,5
    assert not res["exploitable"] and res["contrats"] == 0 and any("Ratio" in v for v in res["vetos"])
    assert doc["statut"] == "verifie"                  # le veto lui-même est recompté
    assert moteur.base.lire("SELECT a FROM messages WHERE genre='alerte'") == [{"a": 14}]


def test_risque_limite_du_jour(moteur):
    res, _ = _risque(moteur, sens="vente", entree=4000.0, stop=4005.0, tp1=3980.0, perte_du_jour=5000)
    assert not res["exploitable"] and any("Limite" in v for v in res["vetos"])


def test_risque_chiffre_faux_rejete(moteur):
    m = moteur.base.nouvelle_mission(8, "evaluation_risque", "test",
                                     {"sens": "achat", "entree": 4000.0, "stop": 3995.0, "tp1": 4010.0})
    moteur.executer(moteur.base.prendre_mission(["evaluation_risque"]))
    ident = moteur.base.mission(m)["resultat"]["document"]
    d = moteur.base.un("SELECT donnees FROM documents WHERE id=?", (ident,))["donnees"]
    d["evaluation"]["contrats_calcules"] += 1
    moteur.base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(d), ident))
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (ident,))["statut"] == "rejete"


def test_recalcul_independant_concorde_avec_la_salle():
    from universite import config
    config.salle_importable()
    from mgc import config as cfg
    from mgc import risque

    reg = dict(cfg.DEFAUTS, limite_perte_jour_usd=1000.0)
    for sens, e, s, t, perte in (("achat", 4000.0, 3995.0, 4010.0, 0), ("vente", 4000.0, 4003.3, 3990.1, 200),
                                 ("achat", 4000.0, 3999.9, 4000.5, 0), ("achat", 4000.0, 3980.0, 4100.0, 990)):
        a = risque.evaluer(sens, e, s, t, reg, perte)
        b = verification_risque.recalculer(sens, e, s, t, reg, perte)
        assert a["contrats_calcules"] == b["contrats_calcules"] and a["exploitable"] == b["exploitable"]
        assert abs(a["ratio_net_tp1"] - b["ratio"]) < 0.011


def test_d1_par_seance_cme(base, jeu):
    """D1 reconstruite depuis M1 : une bougie par séance (17 h Chicago), seulement les séances finies."""
    d1 = donnees.fenetre(base, jeu, "D1", INSTANT)["bougies"]
    assert [b[0] for b in d1] == [DEBUT + k * 86400 for k in range(3)]     # la 4e séance n'est pas finie
    m1 = donnees.fenetre(base, jeu, "M1", DEBUT + 86400)["bougies"]
    assert d1[0][1:5] == (m1[0][1], max(b[2] for b in m1), min(b[3] for b in m1), m1[-1][4])
