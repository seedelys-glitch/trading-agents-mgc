# -*- coding: utf-8 -*-
"""
Spécifications du Micro Gold (MGC) et conversions points / ticks / dollars.

Sources CME (vérifiées le 17/10/2026) : 10 onces troy, échelon de 0,10 USD par once = 1 USD par
contrat, fin de négociation le 3e dernier jour ouvré du mois d'échéance, Globex du dimanche 17h
au vendredi 16h (heure de Chicago) avec une pause d'une heure chaque jour à 16h.

Vocabulaire : un « point » = 1,00 USD de mouvement du prix de l'once = 10 ticks = 10 USD par contrat.
"""

import math

SYMBOLE = "MGC"
ONCES = 10
TICK = 0.10                 # échelon de prix (USD par once)
VALEUR_TICK = 1.0           # USD par contrat et par tick
VALEUR_POINT = ONCES * 1.0  # USD par contrat pour 1,00 USD de mouvement

# Les 12 codes de mois des futures (le MGC n'en cote qu'une partie : voir config « mois_cotes »)
CODES_MOIS = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
MOIS_CODES = {m: c for c, m in CODES_MOIS.items()}


def points_en_ticks(points):
    """Distance en points -> nombre de ticks, arrondi au-dessus (prudent pour le risque)."""
    return math.ceil(round(abs(points) / TICK, 6))


def ticks_en_usd(ticks, contrats=1):
    return round(ticks * VALEUR_TICK * contrats, 2)


def points_en_usd(points, contrats=1):
    return round(points * VALEUR_POINT * contrats, 2)


def usd_en_points(usd, contrats=1):
    if contrats <= 0:
        raise ValueError("Le nombre de contrats doit être positif.")
    return round(usd / (VALEUR_POINT * contrats), 6)


def sur_grille(prix):
    """True si le prix tombe exactement sur un échelon de 0,10."""
    return abs(prix / TICK - round(prix / TICK)) < 1e-6


def arrondi_tick(prix, sens="proche"):
    """Arrondit un prix à l'échelon de 0,10 : « proche », « haut » ou « bas »."""
    n = round(prix / TICK, 6)
    n = {"proche": round, "haut": math.ceil, "bas": math.floor}[sens](n)
    return round(n * TICK, 1)


def code_contrat(annee, mois):
    """(2026, 12) -> « MGCZ26 »."""
    if mois not in MOIS_CODES:
        raise ValueError(f"Mois invalide : {mois}")
    return f"{SYMBOLE}{MOIS_CODES[mois]}{annee % 100:02d}"


def lire_code(code):
    """« MGCZ26 » -> (2026, 12). Refuse les codes continus comme « MGC1! »."""
    code = code.strip().upper().removesuffix(".CMX")
    if not code.startswith(SYMBOLE) or len(code) != len(SYMBOLE) + 3:
        raise ValueError(f"Code de contrat MGC invalide : {code}")
    lettre, annee = code[len(SYMBOLE)], code[len(SYMBOLE) + 1:]
    if lettre not in CODES_MOIS or not annee.isdigit():
        raise ValueError(f"Code de contrat MGC invalide : {code}")
    return 2000 + int(annee), CODES_MOIS[lettre]
