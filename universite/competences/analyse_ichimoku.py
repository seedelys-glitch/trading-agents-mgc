# -*- coding: utf-8 -*-
"""Agent 3 — Ichimoku (Tenkan, Kijun, nuage, Chikou) sur D1, H1 et M15 (calculs.ichimoku de la Salle)."""

from .. import config
from . import _commun

TYPE = "analyse_ichimoku"
AGENT = 3
TITRE = "Analyse Ichimoku"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "secondes UTC (vide = maintenant)"}
UNITES = ["D1", "H1", "M15"]
HISTORIQUE = 300


def calculer(cadres):
    config.salle_importable()
    import calculs

    return {u: calculs.ichimoku(df, u) for u, df in cadres.items()}


def rediger(r):
    lignes = []
    for u, i in r.items():
        if not i["disponible"]:
            lignes.append(f"{u} : moins de 80 bougies, Ichimoku non calculé.")
            continue
        cr = i["dernier_croisement_tenkan_kijun"]
        lignes.append(f"{u} : prix {i['prix']} {i['position_prix']} (nuage {i['nuage_actuel'][0]} – {i['nuage_actuel'][1]}) ; "
                      f"Tenkan {i['tenkan']}, Kijun {i['kijun']}{' (plate)' if i['kijun_plate'] else ''} ; nuage futur "
                      f"{i['nuage_futur']} ; Chikou {i['chikou']}"
                      + (f" ; dernier croisement {cr['sens']} il y a {cr['il_y_a']} bougies." if cr else "."))
    return lignes or ["Aucune unité de temps disponible."]


def executer(ctx):
    return _commun.executer_analyse(ctx, __import__(__name__, fromlist=["x"]), "Ichimoku")
