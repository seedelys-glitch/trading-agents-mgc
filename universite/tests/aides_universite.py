# -*- coding: utf-8 -*-
"""Aides communes aux tests de l'université (nom unique : les tests de la Salle ont leur propre conftest)."""

import random

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
