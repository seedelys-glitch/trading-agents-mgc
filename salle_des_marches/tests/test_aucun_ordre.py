# -*- coding: utf-8 -*-
"""Preuve que l'analyste ne peut passer aucun ordre : aucun module n'importe d'outil d'exécution."""

import ast
from pathlib import Path

SALLE = Path(__file__).resolve().parent.parent
DOSSIERS = [SALLE, SALLE.parent / "pour-jarvis"]

INTERDITS = {
    "alpaca", "alpaca_trade_api", "ib_insync", "ib_async", "ibapi", "ccxt", "MetaTrader5", "oandapyV20",
    "tradovate", "ninjatrader", "rithmic", "async_rithmic", "tastytrade", "topstepx", "projectx",
    "discipline",  # coupe-circuit Tradovate de Jarvis : jamais importé par l'analyste
}
TEXTES_INTERDITS = ("api.tradovate", "placeorder", "place_order", "submit_order", "cancelorder", "modifyorder")


def fichiers():
    for dossier in DOSSIERS:
        for f in dossier.rglob("*.py"):
            if "tests" not in f.parts and "__pycache__" not in f.parts:
                yield f


def test_il_y_a_bien_des_fichiers_a_verifier():
    noms = {f.name for f in fichiers()}
    assert {"bureau.py", "calculs.py", "serveur.py", "risque.py"} <= noms


def test_aucun_import_d_execution_d_ordres():
    fautes = []
    for f in fichiers():
        arbre = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                modules = [a.name for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                modules = [noeud.module or ""]
            else:
                continue
            fautes += [f"{f.name} : {m}" for m in modules if m.split(".")[0].lower() in {i.lower() for i in INTERDITS}]
    assert fautes == []


def test_indicateur_ninjatrader_sans_aucune_fonction_d_ordre():
    """L'indicateur est un Indicator (jamais une Strategy) et n'appelle aucune méthode d'ordre de NinjaScript."""
    code = (SALLE.parent / "ninjatrader" / "ExportBougiesMGC.cs").read_text(encoding="utf-8")
    assert ": Indicator" in code
    interdits = ("Strategy", "EnterLong", "EnterShort", "ExitLong", "ExitShort", "SubmitOrder", "CreateOrder",
                 "ChangeOrder", "CancelOrder", "Account", "Atm", "SetStopLoss", "SetProfitTarget", "Flatten")
    assert [m for m in interdits if m in code] == []


def test_aucun_appel_d_ordre_dans_le_code():
    fautes = [f"{f.name} : {t}" for f in fichiers() for t in TEXTES_INTERDITS
              if t in f.read_text(encoding="utf-8").lower()]
    assert fautes == []
