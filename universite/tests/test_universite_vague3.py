# -*- coding: utf-8 -*-
"""Vague 3 : discours de la Fed (agent 10, lexique fixé) et historien (agent 11), contrôlés par l'agent 9."""

import json

import pytest
from aides_universite import executer_tout

from universite.competences import discours_fed

# Textes ARTIFICIELS (tests seulement), écrits pour contenir des expressions connues du lexique.
TEXTE_FAUCON = ("Good morning. Inflation remains elevated and the labor market is strong.\n\n"
                "In my view further tightening may be needed, and policy should stay restrictive for longer. "
                "It would be premature to cut rates. Some say rate increases are over; I am not yet confident.\n\n"
                + "Additional remarks on the economy follow. " * 20)
TEXTE_COLOMBE = ("Thank you. Inflation has eased and the labor market has cooled.\n\n"
                 "We have made progress on inflation, so it may soon be appropriate to reduce the policy rate. "
                 "Rate cuts would make policy less restrictive.\n\n" + "Further remarks on banking follow. " * 20)
FLUX = [{"titre": "Governor A, Outlook", "lien": "https://www.federalreserve.gov/newsevents/speech/a.htm", "date": 1792000000.0},
        {"titre": "Governor B, Policy", "lien": "https://www.federalreserve.gov/newsevents/speech/b.htm", "date": 1792100000.0}]
TEXTES = {FLUX[0]["lien"]: TEXTE_FAUCON, FLUX[1]["lien"]: TEXTE_COLOMBE}


@pytest.fixture
def fed(monkeypatch):
    monkeypatch.setattr(discours_fed, "telecharger_flux", lambda: FLUX)
    monkeypatch.setattr(discours_fed, "telecharger_texte", lambda lien: TEXTES[lien])


def _discours(moteur):
    m = moteur.base.nouvelle_mission(10, "discours_fed", "test", {})
    faites = executer_tout(moteur)
    assert all(f["statut"] == "terminee" for f in faites), [f["erreur"] for f in faites]
    return moteur.base.mission(m)["resultat"]


def test_lexique_compte_les_expressions_entieres():
    c = discours_fed.compter(TEXTE_FAUCON)
    assert c["faucon"] == {"inflation remains elevated": 1, "further tightening": 1, "not yet confident": 1,
                           "restrictive for longer": 1, "premature to cut": 1}       # « rate increases » ne compte pas
    assert c["colombe"] == {"cut rates": 1}
    assert discours_fed.penchant(5, 1) == "faucon" and discours_fed.penchant(1, 2) == "neutre ou partagé"


def test_discours_lus_ranges_et_recomptes(moteur, fed):
    res = _discours(moteur)
    assert len(res["documents"]) == 2
    docs = [moteur.base.un("SELECT * FROM documents WHERE id=?", (i,)) for i in res["documents"]]
    assert [d["donnees"]["penchant"] for d in docs] == ["faucon", "colombe"]
    assert all(d["statut"] == "verifie" and d["verifie_par"] == 9 for d in docs)
    assert "federalreserve.gov" in docs[0]["contenu"] and "Citations exactes" in docs[0]["contenu"]
    assert moteur.base.un("SELECT COUNT(DISTINCT origine) n FROM extraits WHERE origine LIKE 'fed:%'")["n"] == 2
    assert _discours(moteur)["nouveaux"] == 0          # déjà lus : rien n'est refait


def test_fiche_falsifiee_rejetee(moteur, fed):
    m = moteur.base.nouvelle_mission(10, "discours_fed", "test", {"nombre": 1})
    moteur.executer(moteur.base.prendre_mission(["discours_fed"]))
    ident = moteur.base.mission(m)["resultat"]["documents"][0]
    d = moteur.base.un("SELECT donnees FROM documents WHERE id=?", (ident,))["donnees"]
    d["comptes"]["citations"][0] = "We will cut rates aggressively."          # citation inventée
    moteur.base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(d), ident))
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (ident,))["statut"] == "rejete"


def test_flux_indisponible(moteur, monkeypatch):
    def panne():
        raise OSError("hors ligne")
    monkeypatch.setattr(discours_fed, "telecharger_flux", panne)
    m = moteur.base.nouvelle_mission(10, "discours_fed", "test", {})
    moteur.executer(moteur.base.prendre_mission(["discours_fed"]))
    assert moteur.base.mission(m)["statut"] != "terminee" and not moteur.base.lire("SELECT id FROM documents")


def test_historien_cite_seulement_ce_qui_est_garde(moteur, fed):
    _discours(moteur)
    m = moteur.base.nouvelle_mission(11, "precedents", "test", {"question": "inflation elevated tightening"})
    executer_tout(moteur)
    doc = moteur.base.un("SELECT * FROM documents WHERE id=?", (moteur.base.mission(m)["resultat"]["document"],))
    assert doc["statut"] == "verifie" and doc["donnees"]["extraits"]
    assert "speech/a.htm" in doc["contenu"]
    m = moteur.base.nouvelle_mission(11, "precedents", "test", {"question": "zzzz introuvable"})
    executer_tout(moteur)
    vide = moteur.base.un("SELECT contenu FROM documents WHERE id=?", (moteur.base.mission(m)["resultat"]["document"],))
    assert "rien n'est cité de mémoire" in vide["contenu"]
