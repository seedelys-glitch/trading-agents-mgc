# -*- coding: utf-8 -*-
"""Les modules de la Salle s'importent depuis salle_des_marches (comme quand serveur.py les lance)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mgc import config as cfg  # noqa: E402


@pytest.fixture
def config():
    """Réglages par défaut, limite du jour fixée à 1000 $ (indépendante du PC)."""
    c = dict(cfg.DEFAUTS)
    c["limite_perte_jour_usd"] = 1000.0
    return c
