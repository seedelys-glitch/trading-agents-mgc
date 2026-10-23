# -*- coding: utf-8 -*-
"""
Moteur de risque déterministe, indépendant des IA (droit de veto absolu).

  distance_ticks       = |entrée - stop| / 0,10                (arrondi au-dessus)
  risque_brut_contrat  = distance_ticks x 1 USD
  couts_contrat        = frais aller-retour + glissement (ticks par côté x 2 x 1 USD)
  risque_net_contrat   = risque_brut_contrat + couts_contrat
  budget               = min(capital x risque %, reste de la limite de perte du jour)
  contrats             = floor(budget / risque_net_contrat), plafonné à max_contrats ; < 1 => bloqué
  ratio_net            = (gain au TP1 x contrat - couts) / risque_net_contrat
"""

import math

from .instrument import TICK, VALEUR_TICK, arrondi_tick, points_en_ticks, points_en_usd, sur_grille, ticks_en_usd


def evaluer(sens, entree, stop, tp1, config, perte_du_jour_usd=0.0):
    """sens : « achat » ou « vente ». perte_du_jour_usd : perte déjà subie aujourd'hui (nombre positif, 0 si gain)."""
    vetos = []
    sens = (sens or "").strip().lower()
    if sens not in ("achat", "vente"):
        return {"exploitable": False, "contrats": 0, "vetos": [f"Sens inconnu : « {sens} »."]}
    for nom, prix in (("entrée", entree), ("stop", stop), ("TP1", tp1)):
        if prix is None or prix <= 0 or not sur_grille(prix):
            vetos.append(f"Prix {nom} invalide ({prix}) : il doit tomber sur un échelon de 0,10.")
    if vetos:
        return {"exploitable": False, "contrats": 0, "vetos": vetos}

    coherent = stop < entree < tp1 if sens == "achat" else tp1 < entree < stop
    ticks = points_en_ticks(entree - stop)
    if not coherent or ticks < 1:
        vetos.append("Stop incohérent : il faut stop < entrée < TP1 à l'achat, et l'inverse à la vente.")

    risque_brut = ticks_en_usd(ticks)
    couts = round(config["frais_aller_retour_usd"] + 2 * config["glissement_ticks_par_cote"] * VALEUR_TICK, 2)
    risque_net = round(risque_brut + couts, 2)
    risque_autorise = round(config["capital_usd"] * config["risque_pct"] / 100, 2)
    reste_jour = round(config["limite_perte_jour_usd"] - max(0.0, perte_du_jour_usd), 2)
    budget = min(risque_autorise, reste_jour)

    if reste_jour <= 0:
        vetos.append(f"Limite de perte du jour atteinte ({config['limite_perte_jour_usd']:.0f} $).")
    contrats = math.floor(budget / risque_net + 1e-9) if risque_net > 0 and budget > 0 else 0
    plafonne = contrats > config["max_contrats"]
    contrats = min(contrats, config["max_contrats"])
    if contrats < 1 and reste_jour > 0:
        vetos.append(f"Moins d'un contrat possible : risque net de {risque_net:.2f} $ par contrat "
                     f"pour un budget de {budget:.2f} $.")

    gain_net = points_en_usd(abs(tp1 - entree)) - couts
    ratio = round(gain_net / risque_net, 2) if risque_net > 0 else 0.0
    if coherent and ratio < config["ratio_min"]:
        vetos.append(f"Ratio rendement/risque insuffisant au TP1 : {ratio} (minimum {config['ratio_min']}).")

    break_even = arrondi_tick(entree + config["break_even_pct"] / 100 * (tp1 - entree))
    return {
        "exploitable": not vetos,
        "sens": sens,
        "distance_points": round(abs(entree - stop), 2),
        "distance_ticks": ticks,
        "risque_brut_par_contrat": risque_brut,
        "couts_par_contrat": couts,
        "risque_net_par_contrat": risque_net,
        "risque_autorise": risque_autorise,
        "reste_limite_jour": reste_jour,
        "contrats": max(contrats, 0) if not vetos else 0,
        "contrats_calcules": max(contrats, 0),
        "plafonne": plafonne,
        "risque_total_net": round(risque_net * max(contrats, 0), 2),
        "ratio_net_tp1": ratio,
        "break_even": break_even,
        "tick": TICK,
        "vetos": vetos,
    }
