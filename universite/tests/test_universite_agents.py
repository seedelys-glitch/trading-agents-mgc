# -*- coding: utf-8 -*-
"""Agents, compétences réelles (agent 6 vérifié par l'agent 9), moteur : reprises, délais, boucles."""

import json

import pytest
from aides_universite import DEBUT, executer_tout

from universite import agents, competences, donnees
from universite.competences import analyse_vwap_ema


def test_quatorze_agents_et_cinquante_six_roles():
    assert [a["n"] for a in agents.AGENTS] == list(range(1, 15))
    assert agents.agent(14)["cle"] == "directeur" and len(agents.roles()) == 56


def test_chaque_competence_appartient_a_un_agent_qui_la_declare():
    for c in competences.MODULES:
        assert c.TYPE in agents.agent(c.AGENT)["competences"], c.TYPE
    declarees = {t for a in agents.AGENTS for t in a["competences"]}
    assert declarees == set(competences.TYPES)


def test_agent_sans_competence_reste_en_construction():
    connues = set(competences.TYPES)
    assert agents.fiche(agents.agent(4), connues)["en_construction"]
    assert not agents.fiche(agents.agent(6), connues)["en_construction"]


def _analyse(moteur, jeu, instant):
    m = moteur.base.nouvelle_mission(6, "analyse_vwap_ema", "test", {"jeu": jeu, "instant": instant})
    faites = executer_tout(moteur)
    return moteur.base.mission(m), faites


def test_analyse_puis_verification_independante(moteur, jeu):
    instant = DEBUT + 3 * 86400 + 4 * 3600 + 30
    mission, faites = _analyse(moteur, jeu, instant)
    assert mission["statut"] == "terminee", mission["erreur"]
    assert [m["type"] for m in faites] == ["analyse_vwap_ema", "verification_analyse"]
    doc = moteur.base.un("SELECT * FROM documents WHERE id=?", (mission["resultat"]["document"],))
    assert doc["statut"] == "verifie" and doc["verifie_par"] == 9
    assert doc["donnees"]["ema"]["M5"]["disponible"] and doc["donnees"]["vwap"]["disponible"]
    assert not doc["donnees"]["ema"]["H1"]["disponible"]       # 76 heures < 221 bougies H1 : dit, pas inventé
    # les 4 fonctions de soutien ont réellement travaillé, dans l'ordre
    roles = [e["role"] for e in moteur.base.lire("SELECT role FROM etapes WHERE mission=? ORDER BY id", (mission["id"],))]
    assert roles == ["documentaliste", "chercheur", "professeur", "connaissances"]
    assert moteur.base.lire("SELECT de, a FROM messages WHERE genre='demande'") == [{"de": 6, "a": 9}]


def test_un_chiffre_faux_est_rejete(moteur, jeu):
    instant = DEBUT + 2 * 86400 + 3 * 3600 + 30
    m = moteur.base.nouvelle_mission(6, "analyse_vwap_ema", "test", {"jeu": jeu, "instant": instant})
    moteur.executer(moteur.base.prendre_mission(["analyse_vwap_ema"]))
    doc_id = moteur.base.mission(m)["resultat"]["document"]
    doc = moteur.base.un("SELECT donnees FROM documents WHERE id=?", (doc_id,))["donnees"]
    doc["vwap"]["valeur"] += 0.5
    moteur.base.ecrire("UPDATE documents SET donnees=? WHERE id=?", (json.dumps(doc), doc_id))
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (doc_id,))["statut"] == "rejete"
    assert moteur.base.lire("SELECT * FROM messages WHERE a=14 AND genre='alerte'")


def test_analyse_identique_avec_ou_sans_le_futur(moteur, base):
    from aides_universite import bougies_m1
    tout = bougies_m1(4 * 1440)
    instant = DEBUT + 2 * 86400 + 3600 * 3 + 7
    j1 = donnees.creer_jeu(base, "complet", "test", "MGC")
    donnees.ajouter_bougies(base, j1, "M1", tout)
    j2 = donnees.creer_jeu(base, "coupé", "test", "MGC")
    donnees.ajouter_bougies(base, j2, "M1", [b for b in tout if b[0] + 60 <= instant])
    r = []
    for j in (j1, j2):
        m = base.nouvelle_mission(6, "analyse_vwap_ema", "t", {"jeu": j, "instant": instant})
        moteur.executer(base.prendre_mission(["analyse_vwap_ema"]))
        r.append(base.mission(m)["resultat"])
    assert (r[0]["ema"], r[0]["vwap"], r[0]["prix"]) == (r[1]["ema"], r[1]["vwap"], r[1]["prix"])


def test_ema_identique_a_celle_de_la_salle():
    from universite.competences.verification_analyse import ema_pure
    lignes = [(0, 0, 0, 0, 4000 + (i % 7) - 3, 1) for i in range(400)]
    valeur, _ = analyse_vwap_ema.calculer_ema(lignes)
    assert abs(ema_pure([r[4] for r in lignes], 200)[-1] - valeur) < 1e-9


def test_directeur_confie_la_demande_au_bon_agent(moteur, jeu):
    m = moteur.base.nouvelle_mission(14, "demande_directeur", "demande", {
        "type": "controle_donnees", "params": {"jeu": jeu}, "consigne": "vérifie mes données"})
    executer_tout(moteur)
    confiee = moteur.base.mission(m)["resultat"]["mission_confiee"]
    assert moteur.base.mission(confiee)["agent"] == 13 and moteur.base.mission(confiee)["statut"] == "terminee"


def test_directeur_refuse_ce_que_personne_ne_sait_faire(moteur):
    m = moteur.base.nouvelle_mission(14, "demande_directeur", "demande", {"type": "analyse_bookmap"})
    executer_tout(moteur)
    assert moteur.base.mission(m)["statut"] == "erreur"


def test_synthese_ne_cite_que_des_documents_existants(moteur, jeu):
    _analyse(moteur, jeu, DEBUT + 86400)
    m = moteur.base.nouvelle_mission(14, "synthese_directeur", "synthèse", {})
    executer_tout(moteur)
    r = moteur.base.mission(m)["resultat"]
    assert r["verifies"] == 1
    ids = {d["id"] for d in moteur.base.lire("SELECT id FROM documents")}
    doc = moteur.base.un("SELECT * FROM documents WHERE id=?", (r["document"],))
    assert {s["document"] for s in doc["sources"]} <= ids


def test_erreur_passagere_puis_nouvel_essai(moteur, monkeypatch):
    appels = []

    def panne(ctx):
        appels.append(1)
        raise OSError("fichier occupé")

    monkeypatch.setattr(analyse_vwap_ema, "executer", panne)
    m = moteur.base.nouvelle_mission(6, "analyse_vwap_ema", "t", {}, tentatives_max=2)
    moteur.executer(moteur.base.prendre_mission())
    assert moteur.base.mission(m)["statut"] == "en_attente" and moteur.base.mission(m)["pas_avant"] > 0
    for _ in range(2):
        moteur.base.ecrire("UPDATE missions SET pas_avant=0 WHERE id=?", (m,))
        moteur.executer(moteur.base.prendre_mission())
    assert len(appels) == 3 and moteur.base.mission(m)["statut"] == "erreur"


def test_delai_depasse(moteur, monkeypatch):
    moteur.reglages["delai_mission_s"] = -1
    m = moteur.base.nouvelle_mission(13, "controle_donnees", "t", {"jeu": 1})
    moteur.executer(moteur.base.prendre_mission())
    assert moteur.base.mission(m)["statut"] == "erreur" and "délai" in moteur.base.mission(m)["erreur"]


def test_boucle_respecte_son_budget(moteur, jeu):
    b = moteur.nouvelle_boucle("contrôle", 13, "controle_donnees", "surveiller", {"jeu": jeu}, 30, iterations_max=2)
    t = 1e10
    for i in range(4):
        moteur.tour_de_boucles(t + i * 100)
        executer_tout(moteur)
    assert moteur.base.un("SELECT * FROM boucles WHERE id=?", (b,))["statut"] == "terminee"
    assert moteur.base.un("SELECT COUNT(*) AS n FROM missions WHERE boucle=?", (b,))["n"] == 2


def test_boucle_en_pause_apres_trois_erreurs(moteur):
    b = moteur.nouvelle_boucle("cassée", 13, "controle_donnees", "x", {"jeu": 999}, 30)
    for i in range(3):
        moteur.tour_de_boucles(1e10 + i * 100)
        executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM boucles WHERE id=?", (b,))["statut"] == "pause"


@pytest.mark.parametrize("texte,ok", [("Le prix est au-dessus de sa moyenne.", True),
                                      ("Le prix va monter vers 4100.", False)])
def test_commentaire_ia_sans_chiffre_invente(base, reglages, monkeypatch, texte, ok):
    from universite.ia import IALocale
    ia = IALocale(base, reglages)
    monkeypatch.setattr(ia, "completer", lambda *a, **k: texte)
    assert (ia.commenter("EMA 200 M5 : 4000.12") is not None) == ok
