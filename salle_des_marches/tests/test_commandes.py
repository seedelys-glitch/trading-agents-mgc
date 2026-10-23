# -*- coding: utf-8 -*-
import datetime as dt
import json

import pytest

import commandes
from mgc import calendrier_cme as cal
from mgc import config as cfg

INSTANT = dt.datetime(2026, 10, 20, 16, 0, tzinfo=cal.PARIS)


@pytest.fixture
def rapports(tmp_path, monkeypatch):
    monkeypatch.setattr(commandes, "RAPPORTS", tmp_path)
    monkeypatch.setattr(commandes, "BASE", tmp_path / "analyste.sqlite")
    monkeypatch.setattr(cfg, "FICHIER_PAUSE", tmp_path / "pause.demande")
    (tmp_path / "20261020-152000-XAUUSD").mkdir()
    (tmp_path / "20261020-152000-XAUUSD" / "comparaison.json").write_text(json.dumps({
        "id": "20261020-152000-XAUUSD", "type": "bureau", "debut": 1792509600.0, "fin": 1792509860.0,
        "decision": {"statut": "ATTENDRE", "contrat": "MGCZ26",
                     "setup": {"sens": "achat", "niveau": "0.705", "entree": 4200.0, "stop": 4195.0, "tp1": 4230.0},
                     "risque": {"contrats": 2}}}), encoding="utf-8")
    (tmp_path / "historique.json").write_text(json.dumps([
        {"id": "20261020-152000-XAUUSD", "type": "bureau", "date": "2026-10-20", "heure": "15:20", "ticker": "MGCZ26",
         "statut": "ATTENDRE"},
        {"id": "20261019-152000-XAUUSD", "type": "bureau", "date": "2026-10-19", "heure": "15:20", "ticker": "MGCZ26",
         "statut": "AUCUNE OPPORTUNITÉ"},
    ]), encoding="utf-8")
    return tmp_path


def test_contrat(config):
    texte = commandes.executer("/contrat", maintenant=INSTANT, config=config)
    assert "MGCZ26" in texte and "MGCG27" in texte and "2026-11-25" in texte


def test_pause_et_reprise(rapports, config):
    assert "ACTIVE" in commandes.executer("/pause", config=config)
    assert cfg.pause_active(rapports / "pause.demande")
    assert "levée" in commandes.executer("/resume", config=config)
    assert not (rapports / "pause.demande").exists()


def test_resultat(rapports, config):
    texte = commandes.executer("/resultat", "20261020-152000-XAUUSD win 4215.3", INSTANT, config)
    assert "Noté" in texte and "+15.3 points" in texte and "+3.06 R" in texte
    # même analyse notée de nouveau : remplacée, pas doublée
    commandes.executer("/resultat", "20261020-152000-XAUUSD loss 4195,0", INSTANT, config)
    from mgc import base
    conn = base.ouvrir(rapports / "analyste.sqlite")
    lignes = conn.execute("SELECT issue, r_multiple, pnl_usd_net FROM resultats").fetchall()
    conn.close()
    assert [tuple(lig) for lig in lignes] == [("loss", -1.0, -107.0)]  # 2 contrats : -100 $ - 7 $ de frais


@pytest.mark.parametrize("args, attendu", [
    ("", "Format"), ("20261020-152000-XAUUSD gagne 4215.3", "Format"), ("inconnu win 4215.3", "introuvable"),
    ("20261020-152000-XAUUSD win abc", "illisible"), ("20261020-152000-XAUUSD win 4215.35", "impossible"),
])
def test_resultat_refuse(rapports, config, args, attendu):
    assert attendu in commandes.executer("/resultat", args, INSTANT, config)


def test_memoire_et_stats(rapports, config):
    memoire = commandes.executer("/memoire", config=config)   # base vide : repli sur l'historique
    assert memoire.index("20261020") < memoire.index("20261019")
    assert "Aucune analyse" in commandes.executer("/stats", config=config)
    commandes.executer("/resultat", "20261020-152000-XAUUSD win 4215.3", INSTANT, config)
    stats = commandes.executer("/stats", config=config)
    assert "1 analyse(s)" in stats and "trop petit" in stats and "Trades réels" in stats
    assert "résultat win" in commandes.executer("/memoire", config=config)


def test_news_sans_reseau(monkeypatch, config):
    import calculs

    monkeypatch.setattr(calculs, "calendrier", lambda maintenant, config: {
        "disponible": True, "fomc_aujourdhui": False, "blocages": [],
        "annonces_48h": [{"quand": "20/10 14h30", "titre": "CPI m/m", "impact": "fort", "genre": "forte"}]})
    texte = commandes.executer("/news", maintenant=INSTANT, config=config)
    assert "CPI m/m" in texte and "Rien ne bloque" in texte


def test_commande_inconnue_et_erreur(monkeypatch, config):
    assert commandes.executer("/nimportequoi", config=config) == commandes.AIDE
    assert commandes.executer("/AIDE@javrisanonce_bot", config=config) == commandes.AIDE

    def panne(*a):
        raise OSError("réseau")
    monkeypatch.setattr(commandes, "regime_actuel", panne)
    assert "n'a pas abouti" in commandes.executer("/regime", config=config)
