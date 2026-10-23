# -*- coding: utf-8 -*-
"""
Configuration de trade calculée par le programme (jamais par l'IA), selon la version 1 de STRATEGIE.md :

  - entrée sur le 0.618, 0.705, 0.786 ou 0.893 de la dernière belle impulsion H1, seulement avec un FVG dessus ;
    jamais sur le 0.5 (absent par construction) ;
  - stop au-delà du FVG ET du niveau Fibo suivant (1 tick plus loin) ;
  - TP1 (25 %) au niveau 0, TP2 (50 %) au -0.618, TP3 au -1.618 ; break-even à 35 % du chemin vers le TP1 ;
  - confirmation : une bougie 1H dont la mèche dépasse la zone et dont le corps se pose dessus, entrée à la suivante.
"""

from .instrument import TICK, arrondi_tick

ORDRE = ["0.618", "0.705", "0.786", "0.893", "1"]


def construire(fibo, sens, prix_actuel):
    """sens : « achat » ou « vente ». Renvoie (setup, "") ou (None, motif)."""
    if not fibo or not fibo.get("disponible"):
        return None, (fibo or {}).get("raison") or "Pas de Fibo disponible."
    attendu = {"achat": "haussière", "vente": "baissière"}[sens]
    if fibo["impulsion"] != attendu:
        return None, f"La dernière impulsion H1 est {fibo['impulsion']} : pas de zone Fibo dans le sens {sens}."
    if fibo.get("retracement_actuel", 0) > 1:
        return None, "Le prix a dépassé le départ de l'impulsion : Fibo invalidé."
    valides = [z for z in fibo["zones_entree"] if z.get("fvg_dessus")]
    if not valides:
        return None, "Aucune zone Fibo 0.618 à 0.893 avec un FVG dessus."
    zone = min(valides, key=lambda z: abs(z["prix"] - prix_actuel))
    niveaux = fibo["niveaux"]
    suivant = niveaux[ORDRE[ORDRE.index(zone["niveau"]) + 1]]
    fvg_bas, fvg_haut = zone["fvg"]
    if sens == "achat":
        stop = arrondi_tick(min(fvg_bas, suivant) - TICK, "bas")
    else:
        stop = arrondi_tick(max(fvg_haut, suivant) + TICK, "haut")
    return {
        "sens": sens,
        "niveau": zone["niveau"],
        "entree": arrondi_tick(zone["prix"]),
        "fvg": [fvg_bas, fvg_haut],
        "stop": stop,
        "tp1": arrondi_tick(niveaux["0"]),
        "tp2": arrondi_tick(niveaux["-0.618"]),
        "tp3": arrondi_tick(niveaux["-1.618"]),
        "invalidation": stop,
        "confirmation": "une bougie 1H dont la mèche dépasse la zone et dont le corps se pose sur la zone ; "
                        "entrée à l'ouverture de la bougie suivante",
    }, ""
