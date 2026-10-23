# -*- coding: utf-8 -*-
"""
Configuration de trade calculée par le programme (jamais par l'IA), selon STRATEGIE.md (règles du 18/10/2026) :

  - entrée sur le 0.618, 0.705, 0.786 ou 0.893 de la dernière belle impulsion H1, seulement avec un FVG dessus ;
    jamais sur le 0.5 (absent par construction) ;
  - stop : bord du FVG + 20 % de sa hauteur (évite les mèches de liquidité) ; si ça ne donne pas un stop
    au-delà de l'entrée, 20 % de l'écart jusqu'au niveau Fibo suivant ;
  - objectifs : TP1 au niveau 0, TP2 au -0.272, TP3 au -1.272, TP4 au -2.618 ;
    compte A : 25 % à chaque objectif ; compte B : 50 % au 0, rien au -0.272, 25 % au -1.272, 25 % au -2.618 ;
    stop au point d'entrée dès que la bougie qui suit l'entrée clôture en gain, au 0.5 après le -0.272, au 0 après le -1.272 ;
  - entrée : méthode en cascade Weekly -> 12H -> 48 min -> 12 min (suivie en direct par Jarvis, cascade.py) :
    le desk ne voit que jusqu'au H1, il donne donc le biais et la zone, l'entrée se prend sur la confirmation 12 min.
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
    entree = arrondi_tick(zone["prix"])
    marge = 0.2 * (fvg_haut - fvg_bas)   # 20 % de la hauteur du FVG
    if sens == "achat":
        stop = arrondi_tick(fvg_bas - marge, "bas")
        if stop >= entree - TICK:  # FVG au-dessus du niveau : 20 % de l'écart jusqu'au niveau suivant
            stop = arrondi_tick(entree - max(0.2 * abs(entree - suivant), TICK), "bas")
    else:
        stop = arrondi_tick(fvg_haut + marge, "haut")
        if stop <= entree + TICK:
            stop = arrondi_tick(entree + max(0.2 * abs(suivant - entree), TICK), "haut")
    objectif = lambda cle, ancien: arrondi_tick(niveaux[cle] if cle in niveaux else niveaux[ancien])
    return {
        "sens": sens,
        "niveau": zone["niveau"],
        "entree": entree,
        "fvg": [fvg_bas, fvg_haut],
        "stop": stop,
        "tp1": arrondi_tick(niveaux["0"]),
        "tp2": objectif("-0.272", "-0.618"),
        "tp3": objectif("-1.272", "-1.618"),
        "tp4": objectif("-2.618", "-1.618"),
        "invalidation": stop,
        "confirmation": "cascade Weekly → 12H → 48 min → 12 min : entrée sur la bougie de confirmation 12 min "
                        "sur la zone, entre 15h30 et 20h ; stop au point d'entrée dès que la bougie suivante clôture "
                        "en gain, au 0.5 après le -0.272, au 0 après le -1.272",
        "gestion": "compte A : 25 % au 0, au -0.272, au -1.272 et au -2.618 ; "
                   "compte B : 50 % au 0, 25 % au -1.272, 25 % au -2.618",
    }, ""
