# -*- coding: utf-8 -*-
"""Adaptateur TradingView : exports CSV déposés dans un dossier, importés une seule fois, puis contrôlés."""

from aides_universite import DEBUT, bougies_m1, executer_tout

from universite import donnees
from universite.competences import import_tradingview


def _csv(lignes):
    return "time,open,high,low,close,Volume\n" + "\n".join(f"{int(t)},{o},{h},{l},{c},{v}" for t, o, h, l, c, v in lignes)


def test_nom_des_exports():
    assert import_tradingview.lire_nom("COMEX_MINI_DL_MGC1!, 5_ab12c.csv") == ("MGC1!", "M5")
    assert import_tradingview.lire_nom("COMEX_DL_GC1!, 1D (1).csv") == ("GC1!", "D1")
    assert import_tradingview.lire_nom("EURUSD, 5.csv") == (None, None)


def test_dossier_importe_une_seule_fois(moteur, tmp_path):
    m1 = bougies_m1(600)
    h1 = donnees.regrouper(m1, "M1", "H1", DEBUT + 600 * 60)
    (tmp_path / "COMEX_MINI_DL_MGC1!, 1_x1.csv").write_text(_csv(m1))
    (tmp_path / "COMEX_MINI_DL_MGC1!, 60_x2.csv").write_text(_csv(h1))
    (tmp_path / "abime.csv").write_text("n'importe quoi\n1,2")
    m = moteur.base.nouvelle_mission(13, "import_tradingview", "test", {"dossier": str(tmp_path)})
    faites = executer_tout(moteur)
    assert [f["type"] for f in faites] == ["import_tradingview", "controle_donnees"]
    res = moteur.base.mission(m)["resultat"]
    assert res["importes"] == 2 and len(res["erreurs"]) == 1
    jeux = donnees.liste_jeux(moteur.base)
    assert [j["nom"] for j in jeux] == ["TradingView MGC1!"] and not jeux[0]["temps_reel"]
    assert set(donnees.disponibles(moteur.base, jeux[0]["id"])) == {"M1", "H1"}
    # deuxième passage : rien n'est réimporté
    m = moteur.base.nouvelle_mission(13, "import_tradingview", "test", {"dossier": str(tmp_path)})
    executer_tout(moteur)
    assert moteur.base.mission(m)["resultat"]["importes"] == 0


def test_telechargements_seulement_les_exports_mgc(tmp_path):
    (tmp_path / "COMEX_MGC1!, 5.csv").write_text("x")
    (tmp_path / "releve-banque.csv").write_text("x")
    assert [f.name for f in import_tradingview.a_lire(tmp_path, True)] == ["COMEX_MGC1!, 5.csv"]
