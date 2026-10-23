# -*- coding: utf-8 -*-
"""Laboratoire de replay : stratégie V1 rejouée, découpage, Monte-Carlo reproductible, vérification par l'agent 9."""

import json
import random

from conftest import DEBUT, executer_tout

from universite import donnees
from universite.competences import replay_strategie_v1 as replay

FIN = DEBUT + 3600 * 5000      # après la dernière bougie de test (l'horloge réelle n'intervient pas)


def bougies_h1(n, graine=7):
    """Bougies H1 ARTIFICIELLES pour les tests (marche aléatoire avec tendances)."""
    alea, c, lignes = random.Random(graine), 4000.0, []
    derive = 0.0
    for i in range(n):
        if i % 150 == 0:
            derive = alea.choice((-1.2, 1.2))
        o = c
        c = round(o + derive + alea.gauss(0, 4), 1)
        lignes.append((DEBUT + 3600 * i, o, round(max(o, c) + abs(alea.gauss(0, 2)), 1),
                       round(min(o, c) - abs(alea.gauss(0, 2)), 1), c, 100.0))
    return lignes


def _jeu(base, n=2500):
    j = donnees.creer_jeu(base, "h1", "test", "MGC")
    donnees.ajouter_bougies(base, j, "H1", bougies_h1(n))
    return j


def test_replay_puis_verification(moteur, base):
    j = _jeu(base)
    m = base.nouvelle_mission(13, "replay_strategie_v1", "replay", {"jeu": j, "instant": FIN})
    faites = executer_tout(moteur)
    mission = base.mission(m)
    assert mission["statut"] == "terminee", mission["erreur"]
    assert [x["type"] for x in faites] == ["replay_strategie_v1", "verification_replay"]
    doc = base.un("SELECT * FROM documents WHERE id=?", (mission["resultat"]["document"],))
    assert doc["statut"] == "verifie"
    d = doc["donnees"]
    assert set(d["parts"]) == {"entrainement", "validation", "test"}
    assert sum(p["net"]["nombre"] for p in d["parts"].values()) == len(d["trades"])
    assert "Conclusion statistique" in doc["contenu"]


def test_replay_falsifie_rejete(moteur, base):
    j = _jeu(base)
    m = base.nouvelle_mission(13, "replay_strategie_v1", "replay", {"jeu": j, "instant": FIN})
    moteur.executer(base.prendre_mission(["replay_strategie_v1"]))
    doc_id = base.mission(m)["resultat"]["document"]
    d = base.un("SELECT donnees FROM documents WHERE id=?", (doc_id,))["donnees"]
    d["tout"]["nombre"] = d["tout"]["nombre"] + 3
    base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(d), doc_id))
    executer_tout(moteur)
    assert base.un("SELECT statut FROM documents WHERE id=?", (doc_id,))["statut"] == "rejete"


def test_trop_peu_de_bougies_refuse(moteur, base):
    j = _jeu(base, 100)
    m = base.nouvelle_mission(13, "replay_strategie_v1", "replay", {"jeu": j, "instant": FIN})
    executer_tout(moteur)
    assert base.mission(m)["statut"] == "erreur" and "300" in base.mission(m)["erreur"]


def test_monte_carlo_reproductible():
    r = [1.5, -1, -1, 2, -1, 0.5, -1, 3]
    assert replay.monte_carlo(r) == replay.monte_carlo(r)
    mc = replay.monte_carlo(r)
    assert mc["total_R"][0] <= mc["total_R"][1] <= mc["total_R"][2]
    assert replay.monte_carlo([]) is None


def test_le_futur_ne_change_pas_le_passe(moteur, base):
    """Les trades fermés avant l'instant sont identiques, que la base contienne ou non la suite."""
    tout = bougies_h1(2500)
    coupe = DEBUT + 3600 * 1800
    j1 = donnees.creer_jeu(base, "complet", "test", "MGC")
    donnees.ajouter_bougies(base, j1, "H1", tout)
    j2 = donnees.creer_jeu(base, "coupé", "test", "MGC")
    donnees.ajouter_bougies(base, j2, "H1", [b for b in tout if b[0] + 3600 <= coupe])
    trades = []
    for j, inst in ((j1, FIN), (j2, FIN)):
        m = base.nouvelle_mission(13, "replay_strategie_v1", "r", {"jeu": j, "instant": inst})
        moteur.executer(base.prendre_mission(["replay_strategie_v1"]))
        doc = base.un("SELECT donnees FROM documents WHERE id=?", (base.mission(m)["resultat"]["document"],))
        trades.append(doc["donnees"]["trades"])
    import datetime as dt
    avant = [t for t in trades[0] if dt.datetime.fromisoformat(t["fermeture"]).timestamp() + 3600 < coupe - 3600]
    pareils = [{k: v for k, v in t.items() if k != "regime"} for t in avant]
    assert pareils == [{k: v for k, v in t.items() if k != "regime"} for t in trades[1][:len(avant)]]
    assert [t["regime"] for t in avant] == [t["regime"] for t in trades[1][:len(avant)]]
