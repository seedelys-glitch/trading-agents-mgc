# -*- coding: utf-8 -*-
"""De bout en bout : serveur + moteur réels, comme sur le PC (port choisi au hasard, base temporaire)."""

import json
import time
import urllib.error
import urllib.request

import pytest
from conftest import DEBUT, bougies_m1

from universite import config
from universite.serveur import Universite, lancer


@pytest.fixture
def univ(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DEFAUTS, "ia_commentaires", False)
    u = Universite(tmp_path)
    s = lancer(u, port=0)
    u.url = f"http://127.0.0.1:{s.server_address[1]}"
    yield u
    s.shutdown()
    u.arreter()


def appel(univ, chemin, donnees=None, entete=True, brut=None, entetes=None):
    corps = brut if brut is not None else (json.dumps(donnees).encode() if donnees is not None else None)
    h = {"X-Universite": "1"} if entete else {}
    h.update(entetes or {})
    req = urllib.request.Request(univ.url + chemin, data=corps, headers=h, method="POST" if corps is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def attendre(univ, mission, statut="terminee", delai=20):
    fin = time.time() + delai
    while time.time() < fin:
        m = univ.base.mission(mission)
        if m["statut"] == statut:
            return m
        time.sleep(0.1)
    raise AssertionError(f"mission {mission} : {univ.base.mission(mission)}")


def test_page_et_etat_initial(univ):
    with urllib.request.urlopen(univ.url + "/", timeout=5) as r:
        assert b"Universit" in r.read()
    code, etat = appel(univ, "/api/etat")
    assert code == 200 and len(etat["agents"]) == 14
    statuts = {a["n"]: a["statut"] for a in etat["agents"]}
    assert statuts[6] == "disponible" and statuts[4] == "construction"
    assert etat["liens"] == [] and etat["compteurs"]["documents"] == 0


def test_post_sans_en_tete_refuse(univ):
    code, _ = appel(univ, "/api/missions", {"type": "synthese_directeur"}, entete=False)
    assert code == 403 and univ.base.lire("SELECT * FROM missions") == []


def test_fichier_hors_du_dossier_ui_refuse(univ):
    code, _ = appel(univ, "/../serveur.py")
    assert code == 404


def test_parcours_complet_import_demande_directeur_verification(univ):
    csv = "time,open,high,low,close,volume\n" + "\n".join(
        f"{int(t)},{o},{h},{l},{c},{v}" for t, o, h, l, c, v in bougies_m1(3 * 1440))
    code, r = appel(univ, "/api/jeux/import", brut=csv.encode(), entetes={"X-Nom-Jeu": "essai"})
    assert code == 200 and r["unite"] == "M1" and r["ajoutees"] == 3 * 1440
    code, r = appel(univ, "/api/missions", {"type": "analyse_vwap_ema", "par_directeur": True,
                                            "params": {"jeu": r["jeu"], "instant": DEBUT + 2 * 86400 + 5 * 3600}})
    assert code == 200
    dem = attendre(univ, r["mission"])
    assert dem["agent"] == 14
    analyse = attendre(univ, dem["resultat"]["mission_confiee"])
    verif = attendre(univ, analyse["resultat"]["verification"])
    assert verif["resultat"]["verdict"] == "verifie"
    code, etat = appel(univ, "/api/etat")
    assert {(l["de"], l["a"]) for l in etat["liens"]} >= {(14, 6), (6, 9), (9, 6)}
    code, fiche = appel(univ, "/api/agent/6")
    assert set(fiche["soutiens_etat"]) == {"documentaliste", "chercheur", "professeur", "connaissances"}


def test_vwap_annonce_indisponible_juste_apres_l_ouverture(univ):
    from universite import donnees
    j = donnees.creer_jeu(univ.base, "t", "test", "MGC")
    donnees.ajouter_bougies(univ.base, j, "M1", bougies_m1(1440))
    code, r = appel(univ, "/api/missions", {"type": "analyse_vwap_ema", "params": {"jeu": j, "instant": DEBUT + 86400 + 30}})
    m = attendre(univ, r["mission"])
    doc = univ.base.un("SELECT * FROM documents WHERE id=?", (m["resultat"]["document"],))
    assert not doc["donnees"]["vwap"]["disponible"] and "non calculé" in doc["contenu"]


def test_reglages_bornes_et_ia_reste_locale(univ):
    code, r = appel(univ, "/api/reglages", {"concurrence": 99, "ia_url": "https://exemple.com/v1"})
    assert r["concurrence"] == 8 and r["ia_url"].startswith("http://127.0.0.1")
