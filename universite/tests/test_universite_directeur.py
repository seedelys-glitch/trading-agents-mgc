# -*- coding: utf-8 -*-
"""Conversation avec le directeur (Jarvis -> agent 14) : réponses tirées de la base, missions réelles, rien d'inventé."""

import json
import urllib.request

import pytest
from aides_universite import bougies_m1, executer_tout

from universite import config, donnees
from universite.serveur import Universite, lancer


@pytest.fixture
def univ(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DEFAUTS, "ia_commentaires", False)
    u = Universite(tmp_path, demarrer_moteur=False)
    s = lancer(u, port=0)
    u.url = f"http://127.0.0.1:{s.server_address[1]}"
    yield u
    s.shutdown()
    u.arreter()


def avec_bougies(u):
    jeu = donnees.creer_jeu(u.base, "test", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(u.base, jeu, "M1", bougies_m1(4 * 1440))
    return jeu


def dire(u, texte):
    return u.directeur.repondre(texte, "voix")


def test_etat_et_historique(univ):
    r = dire(univ, "Où en est l'université ?")
    assert r["intention"] == "etat" and "Personne ne travaille" in r["reponse"]
    assert [m["de"] for m in r["messages"]] == ["jabran", "directeur"]
    assert r["messages"][0]["origine"] == "voix"


def test_pas_de_mission_sans_bougies(univ):
    r = dire(univ, "lance une analyse Fibonacci")
    assert r["intention"] == "mission" and r["mission"] is None and "aucune bougie" in r["reponse"]
    assert univ.base.lire("SELECT * FROM missions") == []


def test_mission_confiee_puis_suivie(univ):
    jeu = avec_bougies(univ)
    r = dire(univ, "Demande une analyse Ichimoku")
    m = univ.base.mission(r["mission"])
    assert m["agent"] == 14 and m["type"] == "demande_directeur" and m["params"]["type"] == "analyse_ichimoku"
    assert m["params"]["params"] == {"jeu": jeu}
    assert "Ichimoku" in r["reponse"]
    executer_tout(univ.moteur)
    s = dire(univ, "où en est la mission ?")
    assert s["intention"] == "suivi" and "terminée" in s["reponse"] and "Document n°" in s["reponse"]


def test_je_veux_un_replay(univ):
    avec_bougies(univ)
    r = dire(univ, "je veux un replay de ma stratégie")
    assert r["intention"] == "mission" and univ.base.mission(r["mission"])["params"]["type"] == "replay_strategie_v1"


def test_analyse_complete_lance_les_cinq_techniciens(univ):
    avec_bougies(univ)
    dire(univ, "lance une analyse complète")
    types = sorted(m["params"]["type"] for m in univ.base.lire("SELECT params FROM missions"))
    assert types == sorted(["analyse_smc", "analyse_fibo", "analyse_ichimoku", "analyse_vwap_ema", "analyse_flux"])


def test_question_sur_un_agent(univ):
    r = dire(univ, "et Fibonacci ?")
    assert r["intention"] == "agent" and r["reponse"].startswith("Fibonacci est disponible")
    r = dire(univ, "le heatmap il en est où")
    assert "en construction" in r["reponse"]


def test_synthese_sans_moteur_puis_lue(univ):
    r = dire(univ, "fais-moi la synthèse")
    assert r["intention"] == "synthese" and univ.base.mission(r["mission"])["type"] == "synthese_directeur"
    executer_tout(univ.moteur)
    r = dire(univ, "lis-moi la dernière synthèse")
    assert r["reponse"].startswith("Synthèse n°")


def test_alertes_et_resultats_vides(univ):
    assert dire(univ, "des alertes ?")["reponse"].startswith("Aucune alerte")
    assert "aucun document" in dire(univ, "les derniers résultats")["reponse"]


def test_question_libre_sans_ia_renvoie_les_faits(univ):
    r = dire(univ, "Pourquoi le gold monte aujourd'hui ?")
    assert r["intention"] == "question" and r["reponse"].startswith("Je réponds seulement avec ce qui existe")


def test_question_libre_refuse_les_chiffres_inventes(univ, monkeypatch):
    monkeypatch.setattr(univ.ia, "completer", lambda *a, **k: "Le gold va monter de 37 dollars.")
    r = dire(univ, "Pourquoi le gold monte ?")
    assert "37" not in r["reponse"] and r["reponse"].startswith("Je réponds seulement")
    monkeypatch.setattr(univ.ia, "completer", lambda *a, **k: "Aucun document ne parle de ça, lance une analyse.")
    assert dire(univ, "Pourquoi le gold monte ?")["reponse"].startswith("Aucun document")


def test_api_directeur(univ):
    corps = json.dumps({"texte": "quoi de neuf ?", "origine": "appli"}).encode()
    req = urllib.request.Request(univ.url + "/api/directeur", data=corps, method="POST",
                                 headers={"X-Universite": "1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        rep = json.loads(r.read())
    assert rep["intention"] == "etat" and rep["messages"][-1]["de"] == "directeur"
    with urllib.request.urlopen(univ.url + "/api/directeur", timeout=10) as r:
        assert len(json.loads(r.read())["messages"]) == 2
