# -*- coding: utf-8 -*-
"""Bureau immersif, étape 1 : plan en données, espace de travail d'un agent, bougies sans look-ahead."""

import json
import urllib.error
import urllib.request

import pytest
from aides_universite import DEBUT, bougies_m1, executer_tout

from universite import agents, config, donnees, scene
from universite.serveur import Universite, lancer

INSTANT = DEBUT + 4 * 86400 - 600


@pytest.fixture
def univ(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DEFAUTS, "ia_commentaires", False)
    u = Universite(tmp_path, demarrer_moteur=False)
    s = lancer(u, port=0)
    u.url = f"http://127.0.0.1:{s.server_address[1]}"
    u.jeu = donnees.creer_jeu(u.base, "test", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(u.base, u.jeu, "M1", bougies_m1(4 * 1440))
    yield u
    s.shutdown()
    u.arreter()


def lire(univ, chemin):
    try:
        with urllib.request.urlopen(univ.url + chemin, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_plan_coherent():
    assert scene.verifier() == []
    s = scene.scene()
    assert sorted(p["agent"] for p in s["postes"]) == [a["n"] for a in agents.AGENTS]
    assert scene.poste(14)["zone"] == "directeur"
    assert {"directeur", "bibliotheque", "reunion", "labo", "donnees"} <= {z["cle"] for z in s["zones"]}
    assert all("montre" in z and "source" in z for z in s["zones"])


def test_plan_incoherent_detecte():
    s = scene.scene()
    s["postes"] = s["postes"][1:] + [{**s["postes"][1], "agent": 1}]
    problemes = scene.verifier(s)
    assert any("chevauchent" in p for p in problemes)


def test_api_scene(univ):
    code, s = lire(univ, "/api/scene")
    assert code == 200 and s["version"] == 1 and len(s["postes"]) == 14


def test_espace_vide_ne_montre_rien_d_invente(univ):
    code, e = lire(univ, "/api/agent/4/espace")
    assert code == 200 and e["statut"] == "construction" and e["agent"]["en_construction"]
    assert e["documents"] == [] and e["dernier_document"] is None and e["graphique"] is None
    assert e["missions"] == [] and e["sources"] == [] and e["taches"] == []
    assert lire(univ, "/api/agent/99/espace")[0] == 404


def test_espace_apres_une_vraie_analyse(univ):
    univ.base.nouvelle_mission(1, "analyse_smc", "test", {"jeu": univ.jeu, "instant": INSTANT})
    executer_tout(univ.moteur)
    code, e = lire(univ, "/api/agent/1/espace")
    assert code == 200 and e["statut"] == "disponible" and e["poste"]["zone"] == "analyse"
    assert e["dernier_document"]["statut"] == "verifie" and len(e["documents"]) == 1
    assert e["graphique"] == {"jeu": univ.jeu, "instant": INSTANT, "unite": "H1"}
    assert {s["unite"] for s in e["sources"]} == {"D1", "H1", "M15"}
    assert [t["type"] for t in e["taches"]] == ["analyse_smc"]
    assert any(m["genre"] == "demande" and m["de"] == 1 and m["a"] == 9 for m in e["echanges"])
    # l'agent 9 ne propose pas ses vérifications internes comme tâches à lancer
    _, e9 = lire(univ, "/api/agent/9/espace")
    assert not any(t["type"].startswith("verification_") for t in e9["taches"])


def test_bougies_sans_look_ahead(univ):
    code, r = lire(univ, f"/api/bougies?jeu={univ.jeu}&unite=H1&instant={DEBUT + 5 * 3600 + 1800}&n=50")
    assert code == 200 and r["fermees_seulement"] and r["reconstruite_depuis"] == "M1"
    assert [b[0] for b in r["bougies"]] == [DEBUT + i * 3600 for i in range(5)]   # la 6e heure n'est pas finie
    assert all(b[0] + 3600 <= r["instant"] for b in r["bougies"])
    _, m1 = lire(univ, f"/api/bougies?jeu={univ.jeu}&unite=M1&instant={DEBUT + 600}&n=5000")
    assert len(m1["bougies"]) == 10


def test_bougies_erreurs(univ):
    assert lire(univ, "/api/bougies?jeu=999")[0] == 400
    assert lire(univ, "/api/bougies")[0] == 400
    assert lire(univ, f"/api/bougies?jeu={univ.jeu}&unite=X9")[0] == 400
