# -*- coding: utf-8 -*-
"""Agent 2 — Fibonacci sur la dernière belle impulsion H1, zones d'entrée de Jabran (0.618 à 0.893, jamais 0.5),
valides seulement avec un FVG dessus (calculs.fibo de la Salle)."""

from .. import config
from . import _commun

TYPE = "analyse_fibo"
AGENT = 2
TITRE = "Analyse Fibonacci (zones 0.618 à 0.893 avec FVG)"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "secondes UTC (vide = maintenant)"}
UNITES = ["H1"]
HISTORIQUE = 500


def calculer(cadres):
    config.salle_importable()
    import calculs

    h1 = cadres.get("H1")
    if h1 is None or len(h1) < 50:
        return {"disponible": False, "raison": "moins de 50 bougies H1 fermées"}
    return calculs.fibo({"H1": h1}, float(calculs.atr(h1).iloc[-1]))


def rediger(r):
    if not r.get("disponible"):
        return [f"Fibonacci non tracé : {r.get('raison')}."]
    lignes = [f"Impulsion {r['impulsion']} de {r['depart']['prix']} ({r['depart']['quand']}) à {r['fin']['prix']} "
              f"({r['fin']['quand']}). Retracement actuel : {r['retracement_actuel']} — {r['lecture']}."]
    for z in r["zones_entree"]:
        lignes.append(f"   Zone {z['niveau']} à {z['prix']} : " +
                      (f"FVG dessus ({z['fvg'][0]} – {z['fvg'][1]}), zone valable" if z["fvg_dessus"] else "pas de FVG, zone NON valable"))
    lignes.append("Rappel de la règle de Jabran : on n'entre jamais sur le 0.5.")
    return lignes


def executer(ctx):
    return _commun.executer_analyse(ctx, __import__(__name__, fromlist=["x"]), "Fibonacci H1")
