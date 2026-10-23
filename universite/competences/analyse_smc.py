# -*- coding: utf-8 -*-
"""Agent 1 — structure SMC : tendance (BOS / CHoCH), derniers événements, FVG et order blocks proches."""

from .. import config
from . import _commun

TYPE = "analyse_smc"
AGENT = 1
TITRE = "Analyse SMC (BOS / CHoCH, FVG, order blocks)"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "secondes UTC (vide = maintenant)"}
UNITES = ["D1", "H1", "M15"]
HISTORIQUE = 500


def calculer(cadres):
    config.salle_importable()
    import calculs

    return {u: calculs.resume_smc(df, u, float(calculs.atr(df).iloc[-1])) for u, df in cadres.items() if len(df) > 30}


def rediger(r):
    if not r:
        return ["Pas assez de bougies (plus de 30 par unité) pour lire la structure."]
    lignes = []
    for u, s in r.items():
        lignes.append(f"{u} : tendance {s['tendance']} ; dernier sommet {s['dernier_sommet']}, dernier creux {s['dernier_creux']}.")
        for e in s["derniers_evenements"]:
            lignes.append(f"   {e['type']} {e['sens']} au niveau {e['niveau']} ({e['quand']})")
        for z in s["fvg_proches"]:
            lignes.append(f"   FVG {z['sens']} {z['zone'][0]} – {z['zone'][1]} ({z['etat']}, {z['quand']})")
        for b in s["order_blocks_proches"]:
            lignes.append(f"   Order block {b['sens']} {b['zone'][0]} – {b['zone'][1]} ({b['etat']}, {b['quand']})")
    return lignes


def executer(ctx):
    return _commun.executer_analyse(ctx, __import__(__name__, fromlist=["x"]), "Structure SMC")
