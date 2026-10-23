# -*- coding: utf-8 -*-
"""Preuve que l'université ne peut passer aucun ordre : mêmes interdits que la Salle, appliqués à universite/."""

import ast
import importlib.util
from pathlib import Path

UNIVERSITE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "aucun_ordre_salle", UNIVERSITE.parent / "salle_des_marches" / "tests" / "test_aucun_ordre.py")
_salle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_salle)
INTERDITS, TEXTES_INTERDITS = _salle.INTERDITS, _salle.TEXTES_INTERDITS

INTERDITS_EN_PLUS = {"ordres", "requests_oauthlib", "websocket"}


def fichiers():
    return [f for f in UNIVERSITE.rglob("*.py") if "tests" not in f.parts and "__pycache__" not in f.parts]


def test_il_y_a_bien_des_fichiers():
    assert {"moteur.py", "serveur.py", "donnees.py", "analyse_vwap_ema.py"} <= {f.name for f in fichiers()}


def test_aucun_import_d_execution():
    interdits = {i.lower() for i in INTERDITS | INTERDITS_EN_PLUS}
    fautes = []
    for f in fichiers():
        for noeud in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Import):
                modules = [a.name for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                modules = [noeud.module or ""]
            else:
                continue
            fautes += [f"{f.name} : {m}" for m in modules if m.split(".")[0].lower() in interdits]
    assert fautes == []


def test_aucun_appel_d_ordre():
    fautes = [f"{f.name} : {t}" for f in fichiers() for t in TEXTES_INTERDITS
              if t in f.read_text(encoding="utf-8").lower()]
    assert fautes == []


def test_ui_sans_appel_d_ordre():
    ui = UNIVERSITE / "ui"
    textes = " ".join(f.read_text(encoding="utf-8").lower() for f in ui.rglob("*") if f.suffix in (".js", ".html"))
    assert not [t for t in TEXTES_INTERDITS if t in textes]


def test_serveur_ecoute_seulement_sur_le_pc():
    code = (UNIVERSITE / "serveur.py").read_text(encoding="utf-8")
    assert 'hote="127.0.0.1"' in code and "0.0.0.0" not in code
