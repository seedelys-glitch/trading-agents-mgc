# -*- coding: utf-8 -*-
"""Vague 2 : calendrier des annonces (agent 5) et réactions du gold aux annonces (agent 12), contrôlés par l'agent 9."""

import json

import pytest
from aides_universite import DEBUT, bougies_m1, executer_tout

from universite import donnees
from universite.competences import calendrier_macro, reaction_annonces

MARDI_CPI = DEBUT + 2 * 86400 - 9.5 * 3600         # mardi 20/10 12:30 UTC
MERCREDI_POWELL = DEBUT + 2 * 86400 + 16 * 3600     # mercredi 21/10 14:00 UTC
MERCREDI_FOMC = DEBUT + 2 * 86400 + 20 * 3600       # mercredi 21/10 18:00 UTC
FIN = DEBUT + 4 * 86400 - 600


def _ff(ts, titre, impact="High", pays="USD"):
    import datetime as dt
    return {"title": titre, "country": pays, "impact": impact, "forecast": "0.3%", "previous": "0.2%",
            "date": dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=-4))).isoformat()}


SEMAINE = [_ff(MARDI_CPI, "CPI m/m"), _ff(MERCREDI_POWELL, "Fed Chair Powell Speaks"),
           _ff(MERCREDI_FOMC, "Federal Funds Rate"), _ff(MARDI_CPI, "German ZEW", pays="EUR"),
           _ff(MARDI_CPI + 3600, "Richmond Manufacturing Index", impact="Low")]


@pytest.fixture
def calendrier(monkeypatch):
    def regler(instant, evenements=SEMAINE):
        monkeypatch.setattr(calendrier_macro, "telecharger", lambda: evenements)
        monkeypatch.setattr(calendrier_macro, "maintenant", lambda: instant)
    return regler


def _calendrier(moteur):
    m = moteur.base.nouvelle_mission(5, "calendrier_macro", "test", {})
    faites = executer_tout(moteur)
    assert all(f["statut"] == "terminee" for f in faites), [f["erreur"] for f in faites]
    return moteur.base.mission(m)["resultat"]


def test_calendrier_garde_l_historique_et_bloque(moteur, calendrier):
    calendrier(MERCREDI_POWELL - 15 * 60)
    res = _calendrier(moteur)
    lignes = moteur.base.lire("SELECT titre, genre FROM annonces ORDER BY quand, titre")
    assert [x["genre"] for x in lignes] == ["forte", "autre", "discours_fed", "reunion_fomc"]     # EUR ignorée
    assert len(res["blocages"]) == 2              # jour de FOMC + discours dans 15 min
    doc = moteur.base.un("SELECT * FROM documents WHERE id=?", (res["document"],))
    assert doc["statut"] == "verifie" and doc["verifie_par"] == 9
    assert "Forex Factory" in doc["contenu"] and "prévision 0.3%" in doc["contenu"]
    assert {"de": 5, "a": 8} in moteur.base.lire("SELECT de, a FROM messages WHERE genre='alerte'")
    # deuxième passage : rien n'est dupliqué
    _calendrier(moteur)
    assert moteur.base.un("SELECT COUNT(*) n FROM annonces")["n"] == 4


def test_calendrier_sans_blocage(moteur, calendrier):
    calendrier(MARDI_CPI - 3 * 3600)
    res = _calendrier(moteur)
    assert res["blocages"] == [] and res["a_venir"] == 3


def test_calendrier_indisponible_ne_produit_rien(moteur, monkeypatch):
    def panne():
        raise OSError("hors ligne")
    monkeypatch.setattr(calendrier_macro, "telecharger", panne)
    m = moteur.base.nouvelle_mission(5, "calendrier_macro", "test", {})
    moteur.executer(moteur.base.prendre_mission(["calendrier_macro"]))
    assert moteur.base.mission(m)["statut"] != "terminee"
    assert not moteur.base.lire("SELECT id FROM documents")


def test_blocage_falsifie_rejete(moteur, calendrier):
    calendrier(MARDI_CPI)
    m = moteur.base.nouvelle_mission(5, "calendrier_macro", "test", {})
    moteur.executer(moteur.base.prendre_mission(["calendrier_macro"]))
    ident = moteur.base.mission(m)["resultat"]["document"]
    d = moteur.base.un("SELECT donnees FROM documents WHERE id=?", (ident,))["donnees"]
    assert len(d["blocages"]) == 1
    d["blocages"] = []
    moteur.base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(d), ident))
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (ident,))["statut"] == "rejete"


def _reactions(moteur, jeu, instant):
    m = moteur.base.nouvelle_mission(12, "reaction_annonces", "test", {"jeu": jeu, "instant": instant})
    faites = executer_tout(moteur)
    assert all(f["statut"] == "terminee" for f in faites), [f["erreur"] for f in faites]
    return moteur.base.un("SELECT * FROM documents WHERE id=?", (moteur.base.mission(m)["resultat"]["document"],))


def test_reactions_mesurees_et_recomptees(moteur, jeu, calendrier):
    calendrier(DEBUT)
    _calendrier(moteur)
    doc = _reactions(moteur, jeu, FIN)
    assert doc["statut"] == "verifie" and doc["verifie_par"] == 9
    cas = doc["donnees"]["cas"]
    assert [c["titre"] for c in cas] == ["CPI m/m", "Fed Chair Powell Speaks", "Federal Funds Rate"]
    # vérification à la main sur les bougies du test : référence = clôture de la bougie 12:29
    m1 = {b[0]: b for b in bougies_m1(4 * 1440)}
    ref = m1[MARDI_CPI - 60][4]
    assert cas[0]["reference"] == ref and cas[0]["mouvement_15"] == round(m1[MARDI_CPI + 14 * 60][4] - ref, 2)
    assert all(not r["suffisant"] for r in doc["donnees"]["resume"].values())
    assert "échantillon insuffisant" in doc["contenu"]


def test_reactions_sans_look_ahead(base, moteur, calendrier):
    calendrier(DEBUT)
    _calendrier(moteur)
    toutes = bougies_m1(6 * 1440)
    instant = MERCREDI_FOMC + 1800                 # l'heure après le FOMC n'est pas finie
    court = donnees.creer_jeu(base, "court", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(base, court, "M1", [b for b in toutes if b[0] + 60 <= instant])
    long = donnees.creer_jeu(base, "long", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(base, long, "M1", toutes)
    a, b = (_reactions(moteur, j, instant)["donnees"]["cas"] for j in (court, long))
    assert a == b and [c["titre"] for c in a] == ["CPI m/m", "Fed Chair Powell Speaks"]


def test_reaction_falsifiee_rejetee(moteur, jeu, calendrier):
    calendrier(DEBUT)
    _calendrier(moteur)
    m = moteur.base.nouvelle_mission(12, "reaction_annonces", "test", {"jeu": jeu, "instant": FIN})
    moteur.executer(moteur.base.prendre_mission(["reaction_annonces"]))
    ident = moteur.base.mission(m)["resultat"]["document"]
    d = moteur.base.un("SELECT donnees FROM documents WHERE id=?", (ident,))["donnees"]
    d["cas"][1]["mouvement_60"] += 1.0
    moteur.base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(d), ident))
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (ident,))["statut"] == "rejete"


def test_mesure_refuse_un_trou():
    bougies = [(t, 1, 2, 0, 1, 1) for t in range(0, 3600 * 3, 60) if not 3000 <= t < 4000]
    assert reaction_annonces.mesurer(bougies, 60, 4010) is None       # dernière bougie fermée 17 min avant
    assert reaction_annonces.mesurer(bougies, 60, 6000) is not None
