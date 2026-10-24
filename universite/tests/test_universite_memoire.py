# -*- coding: utf-8 -*-
"""Mémoire : le Scribe (agent 15) note tout en blocs rangés par dossier, l'Archiviste (agent 16) les retrouve."""

import json
import time
import urllib.request

import pytest
from aides_universite import executer_tout

from universite import config, memoire
from universite.base import Base
from universite.serveur import Universite, lancer

SESSION = "abcd1234-0000-0000-0000-000000000000"


def ligne(**d):
    return json.dumps(d, ensure_ascii=False) + "\n"


def session_claude(dossier, cwd=r"C:\Users\admin\Documents\Jarvis"):
    f = dossier / "C--Users-admin-Documents-Jarvis" / f"{SESSION}.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text(
        ligne(type="queue-operation", operation="enqueue", sessionId=SESSION)
        + ligne(type="user", uuid="u1", sessionId=SESSION, cwd=cwd, timestamp="2026-10-24T08:00:00Z",
                message={"role": "user", "content": "<system-reminder>bruit interne</system-reminder>"
                                                    "Ajoute le bouton micro dans l'appli Jarvis"})
        + ligne(type="assistant", uuid="a1", sessionId=SESSION, timestamp="2026-10-24T08:00:05Z",
                message={"role": "assistant", "content": [{"type": "text", "text": "Je regarde voix.py."},
                                                          {"type": "tool_use", "name": "Read", "input": {"file_path": ".env"}}]})
        + ligne(type="user", uuid="u2", sessionId=SESSION, timestamp="2026-10-24T08:00:06Z",
                message={"role": "user", "content": [{"type": "tool_result", "content": "GEMINI_KEY=AIzaSyCLESECRETE123456789012345"}]})
        + ligne(type="assistant", uuid="a2", sessionId=SESSION, timestamp="2026-10-24T08:01:00Z",
                message={"role": "assistant", "content": [{"type": "text", "text": "Le bouton micro est ajouté. token=abc123secret"}]})
        + ligne(type="user", uuid="u3", sessionId=SESSION, isSidechain=True, timestamp="2026-10-24T08:02:00Z",
                message={"role": "user", "content": "travail d'un sous-agent"})
        + ligne(type="user", uuid="u4", sessionId=SESSION, timestamp="2026-10-24T08:05:00Z",
                message={"role": "user", "content": "Et le break-even de la stratégie ?"}),
        encoding="utf-8")
    return f


@pytest.fixture
def reglages_memoire(reglages, tmp_path):
    jarvis = tmp_path / "Jarvis"
    (jarvis / ".cache").mkdir(parents=True)
    return {**reglages, "memoire_jarvis": str(jarvis), "memoire_claude": str(tmp_path / "claude"),
            "memoire_etat_projet": False}


def test_secrets_masques():
    t = memoire.masquer("clé AIzaSyABCDEFGHIJKLMNOPQRSTUV123 et sk-proj-abcdefghijklmnop123\n"
                        "TELEGRAM_TOKEN=123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12\npassword: hunter2")
    assert "AIza" not in t and "sk-proj" not in t and "hunter2" not in t and "ABCDEFGHIJKLMNOP" not in t
    assert t.count("[masqué]") >= 4


def test_classement_par_dossier():
    assert memoire.classer("Le bouton micro de l'appli Jarvis sur Android") == "Jarvis"
    assert memoire.classer("Zone Fibonacci 0.618 avec FVG et BOS") == "Analyse technique"
    assert memoire.classer("Discours de Powell au FOMC") == "Macro et discours"
    assert memoire.classer("bonjour") == "Divers"
    assert memoire.classer("bonjour", indice="Jarvis") == "Jarvis"
    assert memoire.dossier_nomme("universite") == "Université" and memoire.dossier_nomme("inconnu") is None


def test_sessions_claude_en_blocs_sans_secret_ni_resultat_d_outil(base, reglages_memoire, tmp_path):
    f = session_claude(tmp_path / "claude")
    c = memoire.ecrire_tout(base, reglages_memoire)
    blocs = base.lire("SELECT * FROM memoire_blocs WHERE source='claude'")
    assert c["nouveaux"] == 1 and len(blocs) == 1           # le 2e tour n'a pas encore de réponse : il attend
    b = blocs[0]
    assert b["dossier"] == "Jarvis" and b["session"] == "Claude · Jarvis · abcd1234"
    assert "Ajoute le bouton micro" in b["texte"] and "Le bouton micro est ajouté" in b["texte"]
    assert "bruit interne" not in b["texte"] and "sous-agent" not in b["texte"]
    assert "AIza" not in b["texte"] and "GEMINI_KEY" not in b["texte"] and "abc123secret" not in b["texte"]
    # la réponse au 2e tour arrive : le passage suivant relit seulement ce tour et l'ajoute
    with open(f, "a", encoding="utf-8") as h:
        h.write(ligne(type="assistant", uuid="a4", sessionId=SESSION, timestamp="2026-10-24T08:06:00Z",
                      message={"role": "assistant", "content": [{"type": "text", "text": "Plus de break-even à 35 %."}]}))
    c = memoire.ecrire_tout(base, reglages_memoire)
    assert c["nouveaux"] == 1
    b2 = base.un("SELECT * FROM memoire_blocs WHERE ref=?", (f"claude:{SESSION}:u4",))
    assert b2["dossier"] == "Stratégie" and "35 %" in b2["texte"]
    assert memoire.ecrire_tout(base, reglages_memoire)["nouveaux"] == 0       # rien de neuf : rien d'écrit


def test_missions_conversations_et_index(moteur, jeu, reglages_memoire, tmp_path):
    base = moteur.base
    moteur.base.nouvelle_mission(6, "analyse_vwap_ema", "VWAP test", {"jeu": jeu, "instant": 1_792_360_800.0 + 3 * 86400})
    executer_tout(moteur)
    base.ecrire("INSERT INTO conversation(ts, de, texte, origine) VALUES (?,?,?,?)", (time.time(), "jabran", "Où en est le replay ?", "voix"))
    base.ecrire("INSERT INTO conversation(ts, de, texte, origine) VALUES (?,?,?,?)", (time.time(), "directeur", "Le replay est fini.", "voix"))
    base.ecrire("INSERT INTO conversation(ts, de, texte, origine) VALUES (?,?,?,?)", (time.time(), "jabran", "Et ensuite ?", "voix"))
    desk = [{"id": 1, "de": "jabran", "nom": "Jabran", "texte": "Chef de desk, pourquoi pas de trade ?", "heure": time.time()},
            {"id": 2, "de": "chef", "nom": "Chef de desk", "texte": "Pas de zone Fibo valide.", "heure": time.time()},
            {"id": 3, "de": "jabran", "nom": "Jabran", "texte": "ok", "heure": time.time()},
            {"id": 4, "de": "fibo", "nom": "Fibonacci", "texte": "", "heure": time.time(), "attente": True}]
    (tmp_path / "Jarvis" / ".cache" / "desk-chat.json").write_text(json.dumps(desk), encoding="utf-8")
    (tmp_path / "Jarvis" / "memoire-jarvis.txt").write_text("# Ce que Jarvis retient\r\n- 23/10/2026 : Je trade surtout la session de New York\r\n",
                                                            encoding="utf-8")
    c = memoire.ecrire_tout(base, reglages_memoire)
    refs = {r["ref"]: r for r in base.lire("SELECT * FROM memoire_blocs")}
    missions = [r for k, r in refs.items() if k.startswith("mission:")]
    assert missions and all(r["dossier"] == "Analyse technique" for r in missions)
    assert "VWAP" in next(r for r in missions if r["agents"].startswith("[6"))["texte"]
    assert "directeur:1" in refs and "directeur:3" not in refs          # « Et ensuite ? » attend sa réponse
    assert "desk:1" in refs and "desk:3" not in refs and refs["desk:1"]["dossier"] == "Salle des marchés"
    souvenir = next(r for k, r in refs.items() if k.startswith("jarvis:memoire-jarvis.txt"))
    assert souvenir["texte"] == "Je trade surtout la session de New York" and memoire.date_paris(souvenir["debut"], "%d/%m") == "23/10"
    # recherche rapide, accents ignorés
    trouves = memoire.chercher(base, "reponse du directeur sur le REPLAY")
    assert trouves and trouves[0]["ref"] == "directeur:1"
    assert memoire.chercher(base, "zone fibo", dossier="Salle des marchés")[0]["ref"] == "desk:1"
    # dossiers sur le disque + index
    racine = memoire.dossier_memoire(base)
    assert (racine / "INDEX.md").is_file() and "Analyse technique" in (racine / "INDEX.md").read_text(encoding="utf-8")
    assert list((racine / "Analyse technique").glob("*.md")) and list((racine / "Salle des marches").glob("*.md"))
    assert c["total"] == len(refs)


def test_notes_deposees_et_envoyees(base, reglages_memoire):
    depot = memoire.dossier_memoire(base) / "a_ranger"
    depot.mkdir(parents=True)
    (depot / "session-app.md").write_text("dossier: Jarvis\nsession: Claude (appli) · 24/10\n\n# Mémoire des agents\n\n"
                                          "## Demande\nJabran veut un scribe et un archiviste.\n\n## Décision\nAgents 15 et 16.",
                                          encoding="utf-8")
    memoire.ecrire_tout(base, reglages_memoire)
    blocs = base.lire("SELECT * FROM memoire_blocs WHERE genre='note' ORDER BY id")
    assert [b["titre"] for b in blocs] == ["Mémoire des agents — Demande", "Mémoire des agents — Décision"]
    assert all(b["dossier"] == "Jarvis" and b["session"] == "Claude (appli) · 24/10" for b in blocs)
    assert not (depot / "session-app.md").exists() and (depot / "ranges" / "session-app.md").exists()
    r = memoire.noter(base, "Jarvis a redémarré tout seul à 23h45.", source="jarvis", session="Jarvis")
    assert r["nouveau"] and r["dossier"] == "Jarvis"
    assert not memoire.noter(base, "Jarvis a redémarré tout seul à 23h45.", source="jarvis", session="Jarvis")["nouveau"]


def test_archiviste_cite_des_blocs_verifies_par_l_agent_9(moteur, reglages_memoire):
    memoire.noter(moteur.base, "Décision : le stop passe au point d'entrée si la bougie d'entrée clôture en gain.",
                  titre="Règle du stop", dossier="Stratégie")
    m = moteur.base.nouvelle_mission(16, "recherche_memoire", "test", {"question": "stop point d'entree"})
    executer_tout(moteur)
    doc = moteur.base.un("SELECT * FROM documents WHERE mission=?", (m,))
    assert doc["genre"] == "memoire" and "Règle du stop" in doc["contenu"]
    assert moteur.base.un("SELECT statut, verifie_par FROM documents WHERE id=?", (doc["id"],)) == {"statut": "verifie", "verifie_par": 9}
    # un bloc modifié après la réponse : le contrôle le voit
    m2 = moteur.base.nouvelle_mission(16, "recherche_memoire", "test", {"question": "stop"})
    moteur.executer(moteur.base.prendre_mission())
    doc2 = moteur.base.un("SELECT id FROM documents WHERE mission=?", (m2,))["id"]
    moteur.base.ecrire("UPDATE memoire_blocs SET texte='autre chose'")
    executer_tout(moteur)
    assert moteur.base.un("SELECT statut FROM documents WHERE id=?", (doc2,))["statut"] == "rejete"
    vide = moteur.base.nouvelle_mission(16, "recherche_memoire", "test", {"question": "xylophone"})
    executer_tout(moteur)
    assert "Rien trouvé" in moteur.base.un("SELECT contenu FROM documents WHERE mission=?", (vide,))["contenu"]


def test_migration_6_reversible(tmp_path):
    b = Base(tmp_path / "m.sqlite")
    memoire.preparer(b)
    memoire.noter(b, "un bloc")
    assert memoire.chercher(b, "bloc")
    b.migrer(5)
    assert not b.lire("SELECT name FROM sqlite_master WHERE name LIKE 'memoire%'")
    assert b.migrer() == 6
    b.fermer()


@pytest.fixture
def univ(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DEFAUTS, "ia_commentaires", False)
    monkeypatch.setitem(config.DEFAUTS, "memoire_claude", "")
    monkeypatch.setitem(config.DEFAUTS, "memoire_jarvis", "")
    u = Universite(tmp_path, demarrer_moteur=False)
    s = lancer(u, port=0)
    u.url = f"http://127.0.0.1:{s.server_address[1]}"
    yield u
    s.shutdown()
    u.arreter()


def http(u, chemin, corps=None):
    req = urllib.request.Request(u.url + chemin, data=json.dumps(corps).encode() if corps is not None else None,
                                 headers={"X-Universite": "1", "Content-Type": "application/json"},
                                 method="POST" if corps is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_boucle_du_scribe_creee_une_fois(univ, tmp_path):
    boucles = univ.base.lire("SELECT * FROM boucles WHERE genre='ecriture_memoire'")
    assert len(boucles) == 1 and boucles[0]["responsable"] == 15 and boucles[0]["prochaine"] > time.time()
    univ.moteur.changer_boucle(boucles[0]["id"], "pause")
    u2 = Universite(tmp_path, demarrer_moteur=False)
    assert [b["statut"] for b in u2.base.lire("SELECT statut FROM boucles WHERE genre='ecriture_memoire'")] == ["pause"]


def test_api_et_directeur(univ):
    r = http(univ, "/api/memoire/noter", {"texte": "On a décidé de garder le compte B en 50/0/25/25.",
                                         "titre": "Compte B", "source": "claude", "session": "Claude · test"})
    assert r["nouveau"] and r["dossier"] == "Stratégie"
    res = http(univ, "/api/memoire?q=compte%20b")["resultats"]
    assert res[0]["titre"] == "Compte B" and "«" in res[0]["extrait"]
    ctx = http(univ, "/api/memoire/contexte?q=compte%20b")
    assert "Compte B" in ctx["texte"] and "bloc n°" in ctx["texte"] and "Compte B" in ctx["reponse"]
    idx = http(univ, "/api/memoire/index")
    assert idx["total"] == 1 and idx["recherche_rapide"] and idx["dossiers"][0]["dossier"] == "Stratégie"
    assert http(univ, f"/api/memoire/bloc/{r['bloc']}")["session"] == "Claude · test"
    rep = univ.directeur.repondre("Rappelle-moi ce qu'on a décidé pour le compte B", "voix")
    assert rep["intention"] == "memoire" and "Compte B" in rep["reponse"]
    assert http(univ, "/api/zone/bibliotheque")["memoire"]["total"] == 1


def test_question_sans_autre_sujet_que_la_memoire(base):
    memoire.noter(base, "Agents 15 Scribe et 16 Archiviste ajoutés : la mémoire de l'université est créée.",
                  titre="Création de la mémoire des agents", quand=time.time() - 3600)
    memoire.noter(base, "Le replay du compte A est terminé.", titre="Replay compte A")       # plus récent, sans rapport
    assert memoire.mots_question("Qu'est-ce qu'on a décidé sur la mémoire ?") == ["decide", "memoire"]
    assert memoire.mots_question("Qu'est-ce qu'on a décidé sur le break-even ?") == ["break", "even"]
    assert memoire.chercher(base, "Qu'est-ce qu'on a décidé sur la mémoire ?")[0]["titre"] == "Création de la mémoire des agents"
