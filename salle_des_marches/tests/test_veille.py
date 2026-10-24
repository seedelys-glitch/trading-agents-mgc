# -*- coding: utf-8 -*-
"""Veille du desk (cascade déménagée de Jarvis le 24/10) : événements écrits, jamais d'ordre."""

import datetime as dt
import json
import threading
import urllib.request

import pytest

from veille import cascade as cas
from veille.__main__ import ServeurExclusif, fabrique
from veille.service import Veille


def _etage(nom, sens="baissier", L=0.705, prix=2650.0):
    return {"nom": nom, "setup": True, "sens": sens, "impulse_id": "i1", "touche": {"L": L, "prix": prix}}


def _etat(entree=None, n=3):
    noms = ["Weekly", "12H", "48 min"]
    return {"etages": [_etage(x) for x in noms[:n]], "etage": n, "maj": 1.0, "sens": "baissier", "entree": entree}


def _plan(t_bougie):
    p = cas.plan_trade("baissier", 2700.0, 2600.0, 0.705, (2668.0, 2672.0))
    p.update(t_bougie=t_bougie, cle=f"entree-i1-0.705-{int(t_bougie)}")
    return p


def _paris_ts(heure, minute):
    # un mardi ; bougies.paris() lit l'heure locale (le PC est à l'heure de Paris)
    return dt.datetime(2026, 10, 20, heure, minute).timestamp()


@pytest.fixture
def veille(tmp_path):
    return Veille(tmp_path)


def test_un_message_par_etage_une_seule_fois(veille, monkeypatch):
    monkeypatch.setattr(veille.cascade, "analyse", lambda now=None: _etat(n=2))
    veille.cascade.check(now=1000.0)
    veille.cascade.check(now=1060.0)
    ev = veille.depuis(0)
    assert [e["type"] for e in ev] == ["etage", "etage"]
    assert "Weekly" in ev[0]["texte"] and "12H" in ev[0]["texte"]
    assert [e["id"] for e in ev] == [1, 2]


def test_entree_dans_la_fenetre_donne_le_plan(veille, monkeypatch):
    t = _paris_ts(16, 0)
    monkeypatch.setattr(veille.cascade, "analyse", lambda now=None: _etat(_plan(t)))
    veille.cascade.check(now=t + 900)
    e = [x for x in veille.depuis(0) if x["type"] == "entree"]
    assert len(e) == 1
    assert e[0]["plan"]["sens"] == "baissier" and e[0]["plan"]["stop"] > e[0]["plan"]["entree"]
    assert "vente" in e[0]["texte"]


def test_entree_hors_fenetre_sans_plan(veille, monkeypatch):
    t = _paris_ts(21, 0)
    monkeypatch.setattr(veille.cascade, "analyse", lambda now=None: _etat(_plan(t)))
    veille.cascade.check(now=t + 900)
    e = veille.depuis(0)[-1]
    assert e["type"] == "hors_fenetre" and "plan" not in e


def test_coupee_rien_ne_sort(veille, monkeypatch):
    monkeypatch.setattr(veille.cascade, "analyse", lambda now=None: _etat(n=3))
    assert "coup" in veille.commande("coupe la cascade").lower()
    veille.cascade.check(now=1000.0)
    assert veille.depuis(0) == []
    assert "active" in veille.commande("remets la cascade").lower()
    veille.cascade.check(now=1000.0)
    assert len(veille.depuis(0)) == 3


def test_journal_relu_apres_redemarrage(tmp_path, monkeypatch):
    v = Veille(tmp_path)
    v.ajouter({"source": "test", "type": "etage", "texte": "a"})
    v.ajouter({"source": "test", "type": "etage", "texte": "b"})
    v2 = Veille(tmp_path)
    assert v2.dernier_id() == 2 and [e["texte"] for e in v2.depuis(1)] == ["b"]
    assert v2.ajouter({"texte": "c"})["id"] == 3


def test_commande_inconnue_et_premier_tour(veille):
    assert veille.commande("quel temps fait-il") is None
    assert "premier tour" in veille.commande("état de la cascade")


def test_serveur_local(veille, monkeypatch):
    monkeypatch.setattr(veille.cascade, "analyse", lambda now=None: _etat(n=1))
    veille.cascade.check(now=1000.0)
    srv = ServeurExclusif(("127.0.0.1", 0), fabrique(veille))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        etat = json.load(urllib.request.urlopen(base + "/api/veille"))
        assert etat["service"] == "veille" and etat["dernier_id"] == 1
        ev = json.load(urllib.request.urlopen(base + "/api/evenements?depuis=0"))
        assert len(ev["evenements"]) == 1
        assert json.load(urllib.request.urlopen(base + "/api/evenements?depuis=1"))["evenements"] == []
        req = urllib.request.Request(base + "/api/veille/commande", method="POST",
                                     data=json.dumps({"texte": "coupe la cascade"}).encode())
        assert json.load(urllib.request.urlopen(req))["connu"] is True
        assert not veille.cascade.enabled()
        req = urllib.request.Request(base + "/api/veille/commande", method="POST", data=b"{}",
                                     headers={"Origin": "http://exemple.com"})
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(req)
    finally:
        srv.shutdown()


def test_dans_fenetre():
    assert cas.dans_fenetre(_paris_ts(15, 30)) and cas.dans_fenetre(_paris_ts(19, 59))
    assert not cas.dans_fenetre(_paris_ts(15, 29)) and not cas.dans_fenetre(_paris_ts(20, 0))


# ---------------------------------------------------------------------------- stratégie 1H / 12H
from veille import strategie_1h as s1h  # noqa: E402


def test_strategie_commandes(veille):
    assert "premier calcul" in veille.commande("état de la stratégie")
    assert "coupées" in veille.commande("coupe les alertes de stratégie")
    assert not veille.strategie.enabled()
    assert "actives" in veille.commande("remets les alertes de stratégie")
    assert veille.etat()["agents"]["strategie"]["observation"] is True


def test_strategie_observation_n_emet_rien(veille):
    veille.strategie._send("k1", "zone", "Alerte stratégie : test", ["x"])
    assert veille.depuis(0) == []


def test_strategie_hors_observation_emet_et_note(veille, monkeypatch):
    monkeypatch.setattr(s1h, "OBSERVE_ONLY", False)
    veille.strategie._send("k1", "confirmation", "Alerte stratégie : test", ["a", "b"], {"stop": 1.0})
    veille.strategie._send("k1", "confirmation", "Alerte stratégie : test", ["a", "b"], {"stop": 1.0})
    ev = veille.depuis(0)
    assert len(ev) == 1 and ev[0]["source"] == "strategie" and ev[0]["plan"]["stop"] == 1.0
    assert veille.strategie.journal.read_text(encoding="utf-8").count("\n") == 2


# ---------------------------------------------------------------------------- journal des setups et actus
import base64  # noqa: E402

from veille import actus as act  # noqa: E402

LECTURE = json.dumps({"unite": "1H", "sens": "Short", "fibo_haut": "2700", "fibo_bas": "2600", "niveau": "0.705",
                      "prix_niveau": "2670,5", "fvg": "Oui", "entree": "2670", "stop": "2680", "tp1": "2600",
                      "tp2": "2538", "tp3": "?", "date_entree": "21/10/2026", "heure_entree": "16:05",
                      "biais_12h": "Baissier", "ema": "Sous", "rsi": "?", "volume": "?", "confluences": "BOS",
                      "notes": "rejet net"})
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


class FausseIA:
    def __init__(self, texte=None, image=None):
        self.texte, self.image, self.vision_error = texte, image, ""

    def complete(self, prompt, max_tokens=700):
        return self.texte

    def see(self, image, prompt, mime="image/png", max_tokens=700):
        return self.image


def test_setup_note_dans_le_journal(veille, tmp_path):
    bot = tmp_path / "bot trad"
    bot.mkdir()
    veille.setups.base, veille.setups.brain = bot, FausseIA(image=LECTURE)
    rep = veille.noter_setup(PNG, "", "TP1", "", "Telegram")
    assert rep.startswith("Setup n°1 ajouté au journal") and "Conforme" in rep
    lignes = (bot / "journal_setups.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(lignes) == 2 and ";Short;" in lignes[1] and "noté par le desk, Telegram" in lignes[1]
    assert (bot / "captures" / "001_2026-10-21_short.png").is_file()
    assert "1 setup dans ton journal" in veille.stats_setups()


def test_setup_sans_image_ni_dossier(veille, tmp_path):
    assert "pas reçu" in veille.noter_setup(b"")
    veille.setups.base = None
    veille.setups.folder = lambda: None
    assert "bot trad" in veille.noter_setup(PNG)


def test_actu_analysee_par_l_ia_et_secours():
    ia = FausseIA(texte='Voilà : {"impact": "Fort", "sens": "haussier", "resume": "Droits de douane", '
                        '"traduction": "Nous taxons la Chine"}')
    r = act.analyse(ia, "We tariff China", "Truth Social")
    assert r["impact"] == "fort" and r["sens"] == "haussier" and "secours" not in r
    r = act.analyse(FausseIA(), "Fed rate inflation dollar", "Gmail")
    assert r["impact"] == "fort" and r["secours"] is True


def test_serveur_setups_et_actus(veille, tmp_path):
    bot = tmp_path / "bot trad"
    bot.mkdir()
    veille.setups.base, veille.setups.brain = bot, FausseIA(image=LECTURE)
    veille.ia = FausseIA(texte='{"impact": "faible", "sens": "neutre", "resume": "r", "traduction": "t"}')
    srv = ServeurExclusif(("127.0.0.1", 0), fabrique(veille))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(chemin, data):
        req = urllib.request.Request(base + chemin, method="POST", data=json.dumps(data).encode())
        return json.load(urllib.request.urlopen(req))

    try:
        r = post("/api/setups/noter", {"image": base64.b64encode(PNG).decode(), "resultat": "stop", "source": "voix"})
        assert r["reponse"].startswith("Setup n°1")
        assert "1 setup" in json.load(urllib.request.urlopen(base + "/api/setups/stats"))["reponse"]
        assert post("/api/actus/analyser", {"texte": "hello", "source": "Gmail"})["impact"] == "faible"
        with pytest.raises(urllib.error.HTTPError):
            post("/api/setups/noter", {"image": "pas du base64 !"})
    finally:
        srv.shutdown()


def test_ia_locale_prend_le_modele_charge():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from veille.ia import IALocale

    vu = {}

    class LM(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _env(self, d):
            b = json.dumps(d).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._env({"data": [{"id": "qwen/qwen3.5-9b", "state": "not-loaded", "type": "llm"},
                                {"id": "google/gemma-4-e4b", "state": "loaded", "type": "vlm"}]})

        def do_POST(self):
            vu.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self._env({"choices": [{"message": {"content": "<think>x</think>**Bonjour**"}}]})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), LM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ia = IALocale(f"http://127.0.0.1:{srv.server_address[1]}")
        assert ia.complete("salut") == "Bonjour" and vu["model"] == "google/gemma-4-e4b"
        assert ia.see(PNG, "lis") == "Bonjour"
        assert vu["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        srv.shutdown()
    assert IALocale("http://127.0.0.1:9").complete("x") is None


def test_version_et_arret(veille):
    from veille.__main__ import VERSION

    srv = ServeurExclusif(("127.0.0.1", 0), fabrique(veille))
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    assert json.load(urllib.request.urlopen(base + "/api/veille"))["version"] == VERSION
    req = urllib.request.Request(base + "/api/veille/arret", method="POST", data=b"{}")
    assert json.load(urllib.request.urlopen(req))["reponse"] == "arrêt"
    fil.join(5)
    assert not fil.is_alive()
    srv.server_close()
