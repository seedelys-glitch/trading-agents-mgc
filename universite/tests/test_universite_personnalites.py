# -*- coding: utf-8 -*-
"""Personnalités, charte, mentor (cours et leçons tirées des erreurs) et réunion du soir (31/10)."""

import datetime as dt
import json
import urllib.error
import urllib.request

import pytest
from aides_universite import executer_tout

from universite import agents, charte, config, personnalites
from universite.competences import cours_du_jour, retour_erreurs, reunion_debrief, tournee_directeur as td
from universite.serveur import Universite, lancer


@pytest.fixture
def univ(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DEFAUTS, "ia_commentaires", False)
    monkeypatch.setitem(config.DEFAUTS, "memoire_jarvis", str(tmp_path / "Jarvis"))
    monkeypatch.setattr(retour_erreurs.config, "RACINE", tmp_path)
    monkeypatch.setattr(td, "rafraichir_yahoo", lambda base: {"jeu": None, "ajoutees": 0})
    u = Universite(tmp_path / "donnees", demarrer_moteur=False)
    yield u
    u.arreter()


def lancer_mission(u, agent, genre, params=None):
    m = u.base.nouvelle_mission(agent, genre, genre, params or {}, "test")
    u.base.ecrire("UPDATE missions SET statut='en_cours' WHERE id=?", (m,))
    u.moteur.executer(u.base.mission(m))
    return u.base.mission(m)


# ------------------------------------------------------------------ charte
@pytest.mark.parametrize("texte, raison", [
    ("Jabran est un idiot", "insulte ou grossièreté"),
    ("Achetez maintenant, le gold va monter", "conseil d'achat ou de vente"),
    ("Un gain garanti à coup sûr", "promesse de gain"),
    ("voici la clé gsk_abcdefghijklmnop123", "secret"),
    ("Je suis un humain, pas une IA", "se fait passer pour quelqu'un d'autre"),
    ("J'ai acheté 2 contrats", "ordre réel"),
])
def test_charte_refuse(texte, raison):
    assert raison in charte.verifier(texte)


def test_charte_accepte_un_texte_normal():
    assert charte.acceptable("Le prix est au-dessus du nuage Ichimoku ; on attend la confirmation. Merci Jabran.")
    assert "Jabran" in charte.consigne() and len(charte.CHARTE) >= 8


# ------------------------------------------------------------------ personnalités
def test_chaque_agent_a_une_personnalite():
    assert sorted(personnalites.BASE) == [a["n"] for a in agents.AGENTS]
    assert len({p["prenom"] for p in personnalites.BASE.values()}) == len(personnalites.BASE)
    for p in personnalites.BASE.values():
        assert p["devise"] and p["style"] and len(p["caractere"]) >= 2 and p["a_travailler"]


def test_la_personnalite_grandit_avec_le_travail_reel(univ):
    b = univ.base
    f = personnalites.fiche(b, 6)
    assert f["niveau"] == "débutant" and f["traits_gagnes"] == [] and f["humeur"] == "disponible"
    for _ in range(20):
        b.document(6, "analyse", "x", "x", statut="verifie")
    gagnes = personnalites.evoluer(b, 6)
    assert {g["trait"] for g in gagnes} == {"rigueur", "fiabilité"}
    f = personnalites.fiche(b, 6)
    assert f["humeur"].startswith("fierté") and f["niveau"] == "en progrès"
    assert personnalites.evoluer(b, 6) == []          # un trait ne se gagne qu'une fois
    assert b.lire("SELECT * FROM evenements WHERE genre='personnalite'")


# ------------------------------------------------------------------ leçons tirées des erreurs
def test_une_erreur_devient_une_lecon_relue_puis_appliquee(univ):
    b = univ.base
    m = b.nouvelle_mission(6, "analyse_vwap_ema", "VWAP", {}, "test")
    b.ecrire("UPDATE missions SET statut='erreur', erreur='ValueError : pas assez de bougies (12)', fin=? WHERE id=?",
             (b.mission(m)["cree"], m))
    r = lancer_mission(univ, 17, "retour_erreurs")
    assert r["statut"] == "terminee" and r["resultat"]["lecons"] == 1
    l = b.un("SELECT * FROM lecons")
    assert l["agent"] == 6 and l["type"] == "analyse_vwap_ema" and l["cause"] == "données manquantes ou trop courtes"
    assert b.un("SELECT * FROM messages WHERE a=6 AND genre='lecon'")
    # même erreur le lendemain : « répétée »
    retour_erreurs.noter(b, "universite", 6, "analyse_vwap_ema", "Mission « VWAP » en erreur",
                         "ValueError : pas assez de bougies (40)", maintenant=l["maj"] + 86400)
    assert b.un("SELECT statut, fois FROM lecons")["statut"] == "repetee"
    # la prochaine mission du même type relit la leçon ; elle réussit -> leçon appliquée
    import universite.competences as comps

    class Faux:
        TYPE, AGENT, TITRE, PARAMS = "analyse_vwap_ema", 6, "VWAP", {}

        @staticmethod
        def executer(ctx):
            ctx.etape("chercheur", "calcule")
            return {"ok": True}

    sauve = comps.TYPES["analyse_vwap_ema"]
    comps.TYPES["analyse_vwap_ema"] = Faux
    try:
        m2 = lancer_mission(univ, 6, "analyse_vwap_ema")
    finally:
        comps.TYPES["analyse_vwap_ema"] = sauve
    etapes = b.lire("SELECT libelle FROM etapes WHERE mission=? ORDER BY id", (m2["id"],))
    assert etapes[0]["libelle"].startswith("Relit 1 leçon")
    assert b.un("SELECT statut, relue FROM lecons") == {"statut": "appliquee", "relue": 1}
    assert personnalites.fiche(b, 6)["compteurs"]["lecons_appliquees"] == 1


def test_erreurs_du_desk_et_de_jarvis(univ, tmp_path):
    salle = tmp_path / "rapports" / "salle"
    salle.mkdir(parents=True)
    maintenant = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (salle / "veille.log").write_text(f"{maintenant} INFO tout va bien\n{maintenant} ERROR URLError: injoignable\n",
                                      encoding="utf-8")
    (tmp_path / "Jarvis").mkdir()
    (tmp_path / "Jarvis" / "jarvis.log").write_text(
        f"2020-01-01 10:00:00 ERROR vieille erreur\n{maintenant} ERROR KeyError: 'x' dans voix.py\n", encoding="utf-8")
    touchees = retour_erreurs.analyser(univ.base)
    lecons = {l["equipe"]: l for l in univ.base.lire("SELECT * FROM lecons")}
    assert len(touchees) == 2 and set(lecons) == {"desk", "jarvis"}
    assert lecons["desk"]["cause"].startswith("une source en ligne")
    assert lecons["jarvis"]["cause"] == "erreur de programmation"


def test_les_secrets_sont_masques_dans_les_lecons(univ):
    retour_erreurs.noter(univ.base, "jarvis", None, "jarvis", "Erreur", "ERROR GROQ_API_KEY=gsk_secretsecretsecret123")
    assert "gsk_secret" not in univ.base.un("SELECT exemple FROM lecons")["exemple"]


# ------------------------------------------------------------------ cours du mentor
def test_cours_du_jour_avec_sources(univ, monkeypatch):
    monkeypatch.setattr(cours_du_jour, "wikipedia",
                        lambda page, delai=8: {"titre": page, "texte": f"Résumé public de {page}.", "lien": "https://fr.wikipedia.org/x"})
    r = lancer_mission(univ, 17, "cours_du_jour", {"agents": [3, 8]})
    assert r["statut"] == "terminee" and r["resultat"]["cours"] == [3, 8]
    c = univ.base.lire("SELECT * FROM cours ORDER BY id")
    assert [x["agent"] for x in c] == [3, 8] and c[0]["sujet"] == "Le prix et le nuage"
    doc = univ.base.un("SELECT * FROM documents WHERE id=?", (c[0]["document"],))
    assert "Kenji" in doc["titre"] and "wikipedia" in doc["contenu"] and doc["statut"] == "verifie"
    # le sujet suivant au prochain cours
    lancer_mission(univ, 17, "cours_du_jour", {"agents": [3]})
    assert univ.base.un("SELECT sujet FROM cours ORDER BY id DESC LIMIT 1")["sujet"] == "Tenkan et Kijun"


def test_pas_de_cours_sans_renseignement(univ, monkeypatch):
    from universite import entrainement

    monkeypatch.setattr(entrainement, "programme", lambda n: [])     # ni programme, ni bibliothèque, ni Wikipédia
    monkeypatch.setattr(cours_du_jour, "wikipedia", lambda page, delai=8: None)
    r = lancer_mission(univ, 17, "cours_du_jour", {"agents": [3]})
    assert r["resultat"] == {"cours": [], "reportes": [3]} and not univ.base.lire("SELECT * FROM cours")


def test_les_eleves_les_plus_en_retard_d_abord(univ):
    eleves = cours_du_jour.a_enseigner(univ.base, n=20)
    assert 17 not in eleves and len(eleves) == 16


# ------------------------------------------------------------------ réunion du soir
def test_reunion_du_soir(univ):
    b = univ.base
    for _ in range(3):
        b.document(1, "analyse", "x", "x", statut="verifie")
    r = lancer_mission(univ, 14, "reunion_debrief")
    assert r["statut"] == "terminee", r["erreur"]
    res = r["resultat"]
    assert res["participants"] >= 15 and res["ia"] is None
    reunion = b.un("SELECT * FROM reunions")
    assert reunion["fin"] - reunion["debut"] == 1800 and reunion["document"] == res["document"]
    assert reunion_debrief.en_cours(b, reunion["debut"] + 60) and not reunion_debrief.en_cours(b, reunion["fin"] + 1)
    doc = b.un("SELECT * FROM documents WHERE id=?", (res["document"],))
    assert "Arthur (directeur)" in doc["contenu"] and "Sacha (SMC" in doc["contenu"] and "3 document(s) vérifié(s)" in doc["contenu"]
    assert len(b.lire("SELECT * FROM messages WHERE genre='reunion'")) == 16
    # une seule réunion par jour
    assert lancer_mission(univ, 14, "reunion_debrief")["resultat"]["deja_faite"]


def tournee_a(univ, monkeypatch, quand, etat="ouverte"):
    monkeypatch.setattr(td, "maintenant", lambda: quand.timestamp())
    monkeypatch.setattr(td, "seance", lambda t: etat)
    lancer_mission(univ, 14, td.TYPE)
    return [r["type"] for r in univ.base.lire("SELECT type FROM missions WHERE statut='en_attente'")]


def test_la_tournee_lance_la_reunion_a_21h30_les_jours_de_marche(univ, monkeypatch):
    assert "reunion_debrief" not in tournee_a(univ, monkeypatch, dt.datetime(2026, 10, 20, 21, 20, tzinfo=td.PARIS))
    assert "reunion_debrief" in tournee_a(univ, monkeypatch, dt.datetime(2026, 10, 20, 21, 31, tzinfo=td.PARIS))
    # déjà dans la file : pas de doublon
    assert tournee_a(univ, monkeypatch, dt.datetime(2026, 10, 20, 21, 46, tzinfo=td.PARIS)).count("reunion_debrief") == 1


def test_pas_de_reunion_le_samedi_ni_un_jour_ferme(univ, monkeypatch):
    assert "reunion_debrief" not in tournee_a(univ, monkeypatch, dt.datetime(2026, 10, 24, 21, 31, tzinfo=td.PARIS), "fermée")
    assert "reunion_debrief" not in tournee_a(univ, monkeypatch, dt.datetime(2026, 12, 25, 21, 31, tzinfo=td.PARIS), "fermée")


# ------------------------------------------------------------------ rédaction par l'IA (Groq via Jarvis)
def test_redaction_groq_puis_charte_et_chiffres(univ, monkeypatch):
    ia = univ.ia
    monkeypatch.setitem(ia.reglages, "ia_commentaires", True)
    reponses = iter(["Belle journée : 3 analyses vérifiées.", "Achetez maintenant !", "Il y a eu 7 erreurs."])
    monkeypatch.setattr(ia, "_par_jarvis", lambda c, t, m: (next(reponses), "Groq (via Jarvis)"))
    faits = "Analyses vérifiées : 3."
    assert ia.rediger("consigne", faits) == {"texte": "Belle journée : 3 analyses vérifiées.", "ia": "Groq (via Jarvis)"}
    assert ia.rediger("consigne", faits) is None        # charte
    assert ia.rediger("consigne", faits) is None        # chiffre inventé
    assert univ.base.un("SELECT COUNT(*) AS n FROM ia_appels WHERE modele='Groq (via Jarvis)'")["n"] == 3


def test_redaction_desactivee_sans_ia(univ):
    assert univ.ia.rediger("consigne", "faits") is None


# ------------------------------------------------------------------ API
def test_api(univ):
    s = lancer(univ, port=0)
    url = f"http://127.0.0.1:{s.server_address[1]}"

    def lire(chemin):
        try:
            with urllib.request.urlopen(url + chemin, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        code, p = lire("/api/personnalites")
        assert code == 200 and len(p["personnalites"]) == 17 and p["charte"]
        code, f = lire("/api/agent/17/personnalite")
        assert code == 200 and f["prenom"] == "Margaux"
        assert lire("/api/agent/99/personnalite")[0] == 404
        code, r = lire("/api/reunion")
        assert code == 200 and r["reunion"] is None and "21h30" in r["horaire"]
        assert lire("/api/lecons")[0] == 200
        code, e = lire("/api/etat")
        assert e["reunion"] is None and e["prenoms"]["14"] == "Arthur"
        code, a = lire("/api/agent/17")
        assert a["personnalite"]["devise"]
    finally:
        s.shutdown()


def test_redaction_par_le_vrai_chemin_http(univ, monkeypatch):
    """Faux Jarvis local : l'université envoie consigne + faits en JSON et reçoit le texte (jamais de clé)."""
    import http.server
    import threading

    recu = {}

    class FauxJarvis(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            recu.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            corps = json.dumps({"texte": "Arthur : merci à tous.", "ia": "Groq (via Jarvis)"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

    srv = http.server.HTTPServer(("127.0.0.1", 0), FauxJarvis)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setitem(univ.ia.reglages, "ia_commentaires", True)
        monkeypatch.setitem(univ.ia.reglages, "redaction_url", f"http://127.0.0.1:{srv.server_address[1]}/api/rediger")
        assert univ.ia.rediger("Écris la réunion.", "faits") == {"texte": "Arthur : merci à tous.", "ia": "Groq (via Jarvis)"}
        assert recu["texte"] == "faits" and "charte" in recu["consigne"] and recu["max_tokens"] == 900
    finally:
        srv.shutdown()
