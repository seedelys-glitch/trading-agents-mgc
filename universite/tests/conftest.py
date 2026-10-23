# -*- coding: utf-8 -*-
"""L'université s'importe depuis Documents\\TradingAgents (comme avec python -m universite)."""

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))

from universite import config, donnees  # noqa: E402
from universite.base import Base  # noqa: E402
from universite.ia import IALocale  # noqa: E402
from universite.moteur import Moteur  # noqa: E402

from aides_universite import DEBUT, bougies_m1, executer_tout  # noqa: E402,F401


@pytest.fixture
def base(tmp_path):
    b = Base(tmp_path / "u.sqlite")
    yield b
    b.fermer()


@pytest.fixture
def reglages():
    r = dict(config.DEFAUTS)
    r["ia_commentaires"] = False     # aucun appel réseau pendant les tests
    return r


@pytest.fixture
def moteur(base, reglages):
    return Moteur(base, reglages, IALocale(base, reglages))


@pytest.fixture
def jeu(base):
    j = donnees.creer_jeu(base, "test", "artificiel (tests)", "MGC")
    donnees.ajouter_bougies(base, j, "M1", bougies_m1(4 * 1440))
    return j
