# -*- coding: utf-8 -*-
"""Base de l'analyste, statistiques, journal de Jarvis (lecture seule), journaux JSON, suivi des appels IA."""

import datetime as dt
import json
import logging

import pytest

from mgc import base, journal_jarvis, journal_json, stats


def analyse(ident="A1", statut="ACHAT ENVISAGEABLE", sens="achat", entree=4200.0, stop=4195.0, niveau="0.705"):
    return {
        "id": ident, "debut": 1792509600.0, "fin": 1792509863.0, "moteur": "lmstudio", "modele": "qwen3.5-9b",
        "appels": 7, "ticker": "MGCZ26", "donnees": {"marche": {"prix": 4201.0}},
        "decision": {"statut": statut, "contrat": "MGCZ26", "vetos": ["v1"], "vetos_informatifs": ["i1", "i2"],
                     "setup": {"sens": sens, "niveau": niveau, "entree": entree, "stop": stop, "tp1": 4230.0},
                     "risque": {"contrats": 9, "risque_net_par_contrat": 53.5, "ratio_net_tp1": 5.54},
                     "regime": {"regime": "GOLD_BULL"}, "donnees": {"source": "yahoo", "statut": "differee", "config": "abc"}},
        "specialistes": {"smc": {"tour1": {"biais": "haussier", "confiance": 4, "argument": "BOS"}, "tour2": None},
                         "fibo": {"erreur": "délai dépassé"}},
        "llm_calls": [{"agent": "smc (tour 1)", "fournisseur": "lmstudio", "modele": "qwen3.5-9b", "duree_s": 12.5,
                       "jetons_entree": 900, "jetons_sortie": 80, "statut": "ok", "version_prompt": "p1"}],
    }


@pytest.fixture
def conn(tmp_path):
    c = base.ouvrir(tmp_path / "analyste.sqlite")
    yield c
    c.close()


# ------------------------------------------------------------------ base

def test_migrations_montee_et_descente(conn):
    assert base.version(conn) == 1
    assert base.migrer(conn, 0) == 0
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "analyses" not in tables
    assert base.migrer(conn) == 1


def test_enregistrer_une_analyse(conn, config):
    base.enregistrer_analyse(conn, analyse(), config=config, version_prompt="p1")
    a = conn.execute("SELECT * FROM analyses").fetchone()
    assert (a["statut"], a["contrat"], a["entree"], a["contrats"], a["duree_s"], a["config_hash"]) == (
        "ACHAT ENVISAGEABLE", "MGCZ26", 4200.0, 9, 263.0, "abc")
    assert conn.execute("SELECT COUNT(*) FROM vetos WHERE famille = 'informatif'").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM avis_agents").fetchone()[0] == 2  # 1 avis + 1 erreur
    appel = conn.execute("SELECT * FROM llm_calls").fetchone()
    assert (appel["jetons_entree"], appel["duree_s"], appel["statut"]) == (900, 12.5, "ok")
    assert json.loads(conn.execute("SELECT donnees FROM instantanes").fetchone()[0])["marche"]["prix"] == 4201.0
    assert json.loads(conn.execute("SELECT contenu FROM configs").fetchone()[0])["risque_pct"] == 1.0


def test_reenregistrer_garde_le_resultat(conn, config):
    base.enregistrer_analyse(conn, analyse())
    base.enregistrer_resultat(conn, "A1", "win", 4210.0, config)
    base.enregistrer_analyse(conn, analyse(statut="ATTENDRE"))
    assert conn.execute("SELECT statut FROM analyses").fetchone()[0] == "ATTENDRE"
    assert conn.execute("SELECT COUNT(*) FROM resultats").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM vetos").fetchone()[0] == 3  # pas de doublons


def test_resultat_vente_et_inconnu(conn, config):
    base.enregistrer_analyse(conn, analyse(sens="vente", entree=4200.0, stop=4205.0))
    calcul = base.enregistrer_resultat(conn, "A1", "win", 4190.0, config)
    assert calcul == {"pnl_points": 10.0, "r_multiple": 2.0, "pnl_usd_net": 868.5}  # 9 x 100 $ - 9 x 3,50 $
    with pytest.raises(KeyError):
        base.enregistrer_resultat(conn, "absente", "win", 4190.0, config)


def test_sauvegarde_quotidienne(tmp_path, conn):
    fichier = tmp_path / "analyste.sqlite"
    dossier = tmp_path / "sauvegardes"
    assert base.sauvegarder(fichier, dossier, jour="2026-10-20")
    assert base.sauvegarder(fichier, dossier, jour="2026-10-20") is None  # une seule par jour
    for jour in ("2026-10-21", "2026-10-22", "2026-10-23"):
        base.sauvegarder(fichier, dossier, garder=2, jour=jour)
    assert [f.name for f in sorted(dossier.iterdir())] == ["analyste-2026-10-22.sqlite", "analyste-2026-10-23.sqlite"]
    assert base.sauvegarder(tmp_path / "absente.sqlite", dossier) is None


def test_evenement(conn):
    base.evenement(conn, "systeme", "démarrage")
    assert conn.execute("SELECT genre, message FROM evenements").fetchone()[:] == ("systeme", "démarrage")


# ------------------------------------------------------------------ statistiques

def test_wilson():
    assert stats.wilson(5, 10) == (0.2366, 0.7634)
    assert stats.wilson(0, 0) == (0.0, 0.0)
    assert stats.wilson(10, 10)[1] == 1.0


def test_drawdown():
    assert stats.drawdown_max([1, -1, -2, 3, -1]) == 3
    assert stats.drawdown_max([1, 2]) == 0


def test_resumer():
    res = [{"issue": "win", "r_multiple": 2.0, "pnl_usd_net": 200.0},
           {"issue": "loss", "r_multiple": -1.0, "pnl_usd_net": -107.0},
           {"issue": "win", "r_multiple": 3.0, "pnl_usd_net": 300.0}]
    s = stats.resumer(res)
    assert (s["nombre"], s["gagnants"], s["profit_factor"], s["esperance_R"], s["drawdown_max_R"]) == (3, 2, 5.0, 1.333, 1.0)
    assert "trop petit" in s["conclusion"]
    assert stats.resumer(res * 10)["conclusion"].startswith("Taux de réussite entre")
    assert stats.resumer([])["nombre"] == 0


def test_stats_par_setup_et_texte(conn, config):
    assert "Aucune analyse" in stats.texte(conn)
    base.enregistrer_analyse(conn, analyse("A1"))
    assert "aucun résultat noté" in stats.texte(conn)
    base.enregistrer_analyse(conn, analyse("A2", niveau="0.618"))
    base.enregistrer_resultat(conn, "A1", "win", 4210.0, config)
    base.enregistrer_resultat(conn, "A2", "loss", 4195.0, config)
    groupes = stats.par_groupe(conn, "setup")
    assert set(groupes) == {"achat 0.705", "achat 0.618"}
    assert stats.par_groupe(conn, "config")["abc"]["nombre"] == 2
    assert "achat 0.705" in stats.texte(conn)


# ------------------------------------------------------------------ journal de Jarvis (lecture seule)

def test_perte_du_jour(tmp_path):
    fichier = tmp_path / "trades.jsonl"
    assert journal_jarvis.perte_du_jour(dt.date(2026, 10, 20), fichier)[0] == 0.0
    lignes = [{"date": "20/10/2026", "heure_sortie": "15h40", "pnl": "-120"},
              {"date": "20/10/2026", "heure_sortie": "16h10", "resultat": "perte de 80 dollars"},
              {"date": "20/10/2026", "heure_sortie": "", "pnl": "-500"},          # pas encore fermé
              {"date": "19/10/2026", "heure_sortie": "15h00", "pnl": "-300"}]     # autre jour
    fichier.write_text("\n".join(json.dumps(x) for x in lignes) + "\nligne abîmée\n", encoding="utf-8")
    perte, message = journal_jarvis.perte_du_jour(dt.date(2026, 10, 20), fichier)
    assert perte == 200.0
    assert "2 trade(s)" in message
    assert "3 trade(s)" in journal_jarvis.resume(fichier)


@pytest.mark.parametrize("ligne, attendu", [
    ({"pnl": "45,5"}, 45.5), ({"resultat": "+120 dollars"}, 120.0), ({"resultat": "-80 dollars"}, -80.0),
    ({"resultat": "stop touché 50"}, -50.0), ({"resultat": "break even"}, 0.0), ({"resultat": "rien"}, None),
])
def test_pnl_d_une_ligne(ligne, attendu):
    assert journal_jarvis.pnl(ligne) == attendu


def test_jamais_d_ecriture_dans_le_journal_de_jarvis():
    import inspect

    code = inspect.getsource(journal_jarvis)
    assert "write_text" not in code and '"w"' not in code and '"a"' not in code


# ------------------------------------------------------------------ journaux JSON et secrets

@pytest.mark.parametrize("texte", [
    "clé AIzaSyA1234567890abcdefghijklmnop", "groq gsk_abcdefghijklmnopqrstuvwxyz123",
    "deepseek sk-abcdefghijklmnop1234", "bot 1234567890:AAH9zXyWvUtSrQpOnMlKjIhGfEdCbA12345",
    "Authorization: Bearer abc.def.ghijklmnop", "api_key=superSecret123", "password: hunter22",
])
def test_secrets_masques(texte):
    propre = journal_json.masquer(texte)
    assert "[masqué]" in propre
    for morceau in ("AIzaSy", "gsk_abc", "sk-abc", "AAH9z", "abc.def", "superSecret", "hunter22"):
        assert morceau not in propre


def test_ecrire_et_filtre_de_logs(tmp_path):
    fichier = tmp_path / "evenements.jsonl"
    journal_json.ecrire("analyse", "fini", fichier=fichier, details={"erreur": "clé gsk_abcdefghijklmnopqrstuvwxyz123 refusée"})
    ligne = json.loads(fichier.read_text(encoding="utf-8"))
    assert ligne["genre"] == "analyse" and "gsk_" not in ligne["details"]["erreur"]
    record = logging.LogRecord("x", logging.INFO, "", 0, "token=%s", ("abc123456",), None)
    journal_json.FiltreSecrets().filter(record)
    assert record.getMessage() == "token=[masqué]"


# ------------------------------------------------------------------ suivi des appels IA

class FausseIA:
    def __init__(self, erreur=None):
        self.erreur = erreur

    def invoke(self, consigne):
        if self.erreur:
            raise self.erreur
        return type("Reponse", (), {"content": "BIAIS: haussier", "usage_metadata": {"input_tokens": 50, "output_tokens": 7}})()


def test_appel_ia_mesure(capsys):
    import bureau

    compteur = {"appels": 0, "fournisseur": "lmstudio", "modele": "qwen3.5-9b", "version_prompt": "p1"}
    assert bureau.appeler(FausseIA(), "consigne", "smc (tour 1)", compteur) == "BIAIS: haussier"
    with pytest.raises(RuntimeError):
        bureau.appeler(FausseIA(RuntimeError("délai dépassé")), "consigne", "chef", compteur)
    lignes = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [x["statut"] for x in lignes] == ["ok", "erreur"]
    assert lignes[0]["jetons_entree"] == 50 and lignes[0]["cout_usd"] == 0.0 and lignes[0]["type"] == "llm_call"
    assert lignes[1]["erreur"] == "délai dépassé" and compteur["appels"] == 2
    assert len(bureau.version_prompts()) == 10
