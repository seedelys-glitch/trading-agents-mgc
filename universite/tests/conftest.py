# -*- coding: utf-8 -*-
"""L'université s'importe depuis Documents\\TradingAgents (comme avec python -m universite)."""

import random
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))

from universite import config, donnees  # noqa: E402
from universite.base import Base  # noqa: E402
from universite.ia import IALocale  # noqa: E402
from universite.moteur import Moteur  # noqa: E402

DEBUT = 1_792_360_800.0     # dimanche 18/10/2026 17 h à Chicago (22:00 UTC) : ouverture de séance


def bougies_m1(n, depart=DEBUT, prix=4000.0, graine=1):
    """Bougies 1 min ARTIFICIELLES, pour les tests seulement (marche aléatoire reproductible)."""
    alea = random.Random(graine)
    lignes, c = [], prix
    for i in range(n):
        o = c
        c = round(o + alea.choice((-1, 1)) * alea.randint(0, 8) / 10, 1)
        h, l = max(o, c) + alea.randint(0, 3) / 10, min(o, c) - alea.randint(0, 3) / 10
        lignes.append((depart + 60 * i, o, round(h, 1), round(l, 1), c, float(alea.randint(1, 50))))
    return lignes


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


def executer_tout(moteur, limite=20):
    """Exécute les missions prêtes une par une, dans ce fil (sans ouvriers)."""
    faites = []
    for _ in range(limite):
        m = moteur.base.prendre_mission()
        if m is None:
            break
        moteur.executer(m)
        faites.append(moteur.base.mission(m["id"]))
    return faites
