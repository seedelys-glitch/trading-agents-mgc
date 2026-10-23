# -*- coding: utf-8 -*-
"""Backtest : confirmation, gestion de position prudente, coûts, découpage, et AUCUN regard vers le futur."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

import calculs
from mgc import backtest, qualite
from mgc import calendrier_cme as cal

T0 = pd.Timestamp("2026-10-20 14:00", tz="UTC")


def b(o, h, l, c):  # noqa: E741
    return {"o": o, "h": h, "l": l, "c": c}


def position(sens="achat", contrats=1, couts=3.5):
    if sens == "achat":
        return backtest.Position("achat", 4200.0, 4195.0, (4230.0, 4261.8, 4361.8), contrats, couts, T0, "0.705", 35)
    return backtest.Position("vente", 4200.0, 4205.0, (4170.0, 4138.2, 4038.2), contrats, couts, T0, "0.705", 35)


def jouer(p, bougies):
    for k, bougie in enumerate(bougies):
        if p.avancer(T0 + pd.Timedelta(hours=k), bougie):
            return p.bilan()
    return None


# ------------------------------------------------------------------ règles

def test_confirmation():
    zone = (4127.0, 4132.0)
    assert backtest.confirmation(b(4135, 4136, 4125, 4128), zone, "achat")       # mèche dessous, clôture dedans
    assert not backtest.confirmation(b(4135, 4136, 4128, 4129), zone, "achat")   # pas de mèche au-delà
    assert not backtest.confirmation(b(4135, 4136, 4125, 4126), zone, "achat")   # clôture sous la zone
    assert backtest.confirmation(b(4125, 4134, 4124, 4131), zone, "vente")
    assert not backtest.confirmation(b(4125, 4134, 4124, 4133), zone, "vente")


def test_biais():
    assert backtest.biais("haussier", "haussier", True) == "achat"
    assert backtest.biais("baissier", "baissier", False) == "vente"
    assert backtest.biais("haussier", "haussier", False) is None
    assert backtest.biais("haussier", "baissier", True) is None


# ------------------------------------------------------------------ gestion de position

def test_tp1_puis_break_even():
    r = jouer(position(), [b(4200, 4231, 4199, 4228), b(4228, 4229, 4199, 4205)])
    assert r["sorties"] == ["TP1", "break-even"]
    assert r["R_brut"] == 1.5                     # 25 % x 30 points / 5 points de risque
    assert r["usd_brut"] == 75.0 and r["usd_net"] == 71.5


def test_les_trois_objectifs():
    r = jouer(position(), [b(4200, 4232, 4199, 4230), b(4230, 4262, 4229, 4260), b(4260, 4362, 4259, 4360)])
    assert r["sorties"] == ["TP1", "TP2", "TP3"]
    assert r["R_brut"] == pytest.approx((0.25 * 30 + 0.5 * 61.8 + 0.25 * 161.8) / 5, abs=1e-3)


def test_stop_avant_objectif_dans_la_meme_bougie():
    r = jouer(position(), [b(4200, 4232, 4194, 4210)])
    assert r["sorties"] == ["stop"] and r["R_brut"] == -1.0


def test_break_even_seulement_a_la_bougie_suivante():
    # seuil du break-even (4210,5) et stop touchés dans la même bougie : c'est le stop initial qui compte
    r = jouer(position(), [b(4200, 4211, 4194, 4201)])
    assert r["sorties"] == ["stop"] and r["R_brut"] == -1.0
    # seuil atteint, puis retour sous l'entrée à la bougie suivante : sortie à l'entrée (0 R brut)
    r = jouer(position(), [b(4200, 4211, 4196, 4201), b(4201, 4202, 4194, 4195)])
    assert r["sorties"] == ["break-even"] and r["R_brut"] == 0.0 and r["usd_net"] == -3.5


def test_ouverture_au_dela_du_stop():
    r = jouer(position(), [b(4200, 4202, 4198, 4199), b(4190, 4192, 4185, 4188)])
    assert r["sorties"] == ["stop (ouverture au-delà)"] and r["R_brut"] == -2.0


def test_vente_et_sortie_forcee():
    p = position("vente", contrats=2)
    assert not p.avancer(T0, b(4200, 4201, 4169, 4180))
    assert p.avancer(T0 + pd.Timedelta(hours=1), b(4180, 4181, 4175, 4178), forcer=True)
    r = p.bilan()
    assert r["sorties"] == ["TP1", "sortie forcée (fin de séance)"]
    assert r["points"] == pytest.approx(0.25 * 30 + 0.75 * 20)
    assert r["usd_net"] == pytest.approx(2 * 22.5 * 10 - 2 * 3.5)


# ------------------------------------------------------------------ aucun regard vers le futur

def serie(n, graine=11):
    rng = np.random.default_rng(graine)
    debuts, t = [], dt.datetime(2026, 1, 5, 0, 0, tzinfo=dt.UTC)
    while len(debuts) < n:
        if cal.etat_seance(t)["etat"] == "ouverte":
            debuts.append(t)
        t += dt.timedelta(hours=1)
    i = np.arange(n)
    milieu = 4000 + 250 * np.sin(2 * np.pi * i / 300) + 0.15 * i + np.cumsum(rng.normal(0, 3, n))
    o = np.round(milieu + rng.normal(0, 2, n), 1)
    c = np.round(milieu + rng.normal(0, 2, n), 1)
    h = np.round(np.maximum(o, c) + np.abs(rng.normal(0, 4, n)), 1)
    l = np.round(np.minimum(o, c) - np.abs(rng.normal(0, 4, n)), 1)  # noqa: E741
    return pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "v": 100.0}, index=pd.DatetimeIndex(debuts))


def test_aucune_decision_ne_depend_du_futur(config):
    config["fenetre_paris"] = ["00:00", "23:59"]
    complet = serie(1100)
    coupe = complet.iloc[:800]
    trace_complete, trace_coupee = [], []
    backtest.simuler(complet, config, trace=trace_complete)
    backtest.simuler(coupe, config, trace=trace_coupee)
    limite = coupe.index[-2]  # la dernière bougie de l'historique coupé n'est pas évaluée
    avant = [x for x in trace_complete if x[0] <= limite]
    assert len(avant) > 300 and any(x[2] for x in avant)  # le test porte sur de vraies zones calculées
    assert trace_coupee == avant


def test_ema_atr_et_h12_causaux():
    h1 = serie(600)
    for nom, f in (("ema", lambda d: calculs.ema(d["c"], 200)), ("atr", calculs.atr)):
        assert f(h1).iloc[399] == pytest.approx(f(h1.iloc[:400]).iloc[-1]), nom
    complet, coupe = qualite.regrouper_cme(h1, 12), qualite.regrouper_cme(h1.iloc[:400], 12)
    fin = h1.index[399] + pd.Timedelta(hours=1)
    terminees = coupe[coupe.index + pd.Timedelta(hours=12) <= fin]
    pd.testing.assert_frame_equal(terminees, complet.loc[terminees.index])


# ------------------------------------------------------------------ rapport

def test_rapport_brut_net_et_decoupage():
    trades = [{"sens": "achat", "niveau": "0.705", "ouverture": f"2026-0{m}-10T14:00:00+00:00", "R_brut": r, "R_net": r - 0.1,
               "usd_brut": r * 100, "usd_net": r * 100 - 7, "sorties": ["stop" if r < 0 else "TP1"]}
              for m, r in ((1, 1.5), (2, -1.0), (4, 2.0), (6, -1.0), (8, 1.0))]
    r = backtest.rapport({"trades": trades, "refus": {}, "debut": "2026-01-01T00:00:00+00:00",
                          "fin": "2026-10-01T00:00:00+00:00", "bougies": 4000})
    assert r["nombre_trades"] == 5
    # coupure à 60 % de la période (13/06/2026) : janvier à juin 10 avant, août après
    assert r["premiere_partie"]["net"]["nombre"] == 4 and r["hors_echantillon"]["net"]["nombre"] == 1
    assert r["tout"]["brut"]["esperance_R"] == 0.5 and r["tout"]["net"]["esperance_R"] == 0.4
    assert set(r["walk_forward_trimestres"]) == {"2026Q1", "2026Q2", "2026Q3"}
    assert "trop petit" in r["tout"]["net"]["conclusion"]
    assert r["sorties"] == {"TP1": 3, "stop": 2}
