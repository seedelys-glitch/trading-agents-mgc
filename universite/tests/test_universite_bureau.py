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


def test_page_charge_le_bureau(univ):
    with urllib.request.urlopen(univ.url + "/", timeout=5) as r:
        assert b"bureau.js" in r.read()
    with urllib.request.urlopen(univ.url + "/bureau.js", timeout=5) as r:
        assert r.status == 200 and b"/api/scene" in r.read()


def test_etat_donne_le_dernier_document_reel(univ):
    _, e = lire(univ, "/api/etat")
    assert all(a["dernier_document"] is None for a in e["agents"])
    univ.base.nouvelle_mission(3, "analyse_ichimoku", "test", {"jeu": univ.jeu, "instant": INSTANT})
    executer_tout(univ.moteur)
    _, e = lire(univ, "/api/etat")
    d = {a["n"]: a["dernier_document"] for a in e["agents"]}
    assert d[3]["genre"] == "analyse" and d[3]["statut"] == "verifie"
    assert d[9]["genre"] == "verification" and d[1] is None


def test_sources_gardent_leur_reference(univ):
    univ.base.nouvelle_mission(1, "analyse_smc", "test", {"jeu": univ.jeu, "instant": INSTANT})
    executer_tout(univ.moteur)
    _, e9 = lire(univ, "/api/agent/9/espace")
    doc_analyse = univ.base.un("SELECT id FROM documents WHERE genre='analyse'")["id"]
    assert [s["document"] for s in e9["sources"]] == [doc_analyse]          # le document vérifié
    assert e9["sources"][0]["cite_dans"] != doc_analyse                      # cité dans le procès-verbal
    _, e1 = lire(univ, "/api/agent/1/espace")
    assert e1["jeux"][str(univ.jeu)]["nom"] == "test"


@pytest.mark.parametrize("cle", [z["cle"] for z in scene.ZONES])
def test_chaque_zone_repond_sans_rien_inventer(univ, cle):
    code, z = lire(univ, f"/api/zone/{cle}")
    assert code == 200 and z["zone"]["cle"] == cle
    for k, v in z.items():                                 # base vide : listes vides, compteurs à zéro
        if isinstance(v, list) and k != "agents":
            assert v == [] or k == "jeux", (k, v)
    assert lire(univ, "/api/zone/cuisine")[0] == 404


def test_zones_avec_du_vrai_travail(univ):
    univ.base.nouvelle_mission(1, "analyse_smc", "test", {"jeu": univ.jeu, "instant": INSTANT})
    univ.base.nouvelle_mission(13, "controle_donnees", "test", {"jeu": univ.jeu})
    executer_tout(univ.moteur)
    _, r = lire(univ, "/api/zone/reunion")
    assert r["messages_24h"] == len(r["messages"]) >= 2
    _, a = lire(univ, "/api/zone/analyse")
    assert [d["agent"] for d in a["documents"]] == [1] and len(a["agents"]) == 6
    _, b = lire(univ, "/api/zone/bibliotheque")
    assert b["verifications"] and b["regles"] == {}
    _, d = lire(univ, "/api/zone/donnees")
    assert d["jeux"][0]["unites"]["M1"]["n"] == 4 * 1440
    _, l = lire(univ, "/api/zone/labo")
    assert l["documents"][0]["genre"] == "donnees"


def test_bureau_du_directeur_montre_sa_vraie_synthese(univ):
    univ.base.nouvelle_mission(6, "analyse_vwap_ema", "test", {"jeu": univ.jeu, "instant": INSTANT})
    executer_tout(univ.moteur)
    univ.base.nouvelle_mission(14, "synthese_directeur", "test", {})
    executer_tout(univ.moteur)
    _, d = lire(univ, "/api/zone/directeur")
    s = univ.base.un("SELECT id, contenu FROM documents WHERE genre='synthese'")
    assert d["derniere_synthese"]["id"] == s["id"] and d["derniere_synthese"]["contenu"] == s["contenu"]
    assert [x["type"] for x in d["demandes"]] == ["synthese_directeur"]


def test_une_seule_universite_par_port(univ):
    port = int(univ.url.rsplit(":", 1)[1])
    with pytest.raises(OSError):                 # la 2e copie ne peut pas écouter sur le même port
        lancer(univ, port=port)
