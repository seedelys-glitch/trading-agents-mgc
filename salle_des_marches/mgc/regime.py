# -*- coding: utf-8 -*-
"""
Détecteur de régime de marché pour l'or (déterministe, aucune IA). PREMIÈRE VERSION : seuils dans la config.

Entrées (calculées par calculs.py) : tendance de fond de l'or (prix et pente de l'EMA 200 en D1), variation
sur 5 jours du dollar (DXY) et du taux US à 10 ans.

  GOLD_BULL   l'or est en tendance haussière, ni le dollar ni les taux ne montent
  HAVEN_TEST  l'or monte MALGRÉ un dollar ou des taux en hausse (demande refuge, fragile)
  HEADWIND    dollar ou taux en hausse et l'or sans tendance haussière (vent contraire)
  GOLDILOCKS  dollar et taux calmes ou en baisse, l'or sans tendance haussière nette (marché calme)
  UNKNOWN     données manquantes
"""

import datetime as dt

SEUILS = {"dollar_pct": 0.5, "taux_pct": 2.0}


def _direction(variation, seuil):
    if variation is None:
        return None
    return "hausse" if variation > seuil else "baisse" if variation < -seuil else "stable"


def detecter(calculs_faits, maintenant=None):
    maintenant = maintenant or dt.datetime.now(dt.UTC)
    macro = calculs_faits.get("macro") or {}
    ema = (calculs_faits.get("tendance") or {}).get("ema200_D1") or {}
    dollar = _direction((macro.get("dollar_DXY") or {}).get("variation_5_jours_pct"), SEUILS["dollar_pct"])
    taux = _direction((macro.get("taux_10_ans_US") or {}).get("variation_5_jours_pct"), SEUILS["taux_pct"])
    base = {"horodatage": maintenant.isoformat(timespec="seconds"), "dollar_5j": dollar, "taux_5j": taux}
    if dollar is None or taux is None or not ema:
        return {**base, "regime": "UNKNOWN", "confiance": "aucune",
                "justification": "Dollar, taux ou EMA 200 D1 indisponible : régime inconnu."}
    or_haussier = ema.get("prix") == "au-dessus" and ema.get("pente") == "montante"
    vent_contraire = "hausse" in (dollar, taux)
    lecture = (f"or {'en tendance haussière' if or_haussier else 'sans tendance haussière'} (EMA 200 D1 "
               f"{ema.get('pente')}, prix {ema.get('prix')}), dollar en {dollar}, taux 10 ans en {taux} sur 5 jours")
    if or_haussier and not vent_contraire:
        regime = "GOLD_BULL"
    elif or_haussier:
        regime = "HAVEN_TEST"
    elif vent_contraire:
        regime = "HEADWIND"
    else:
        regime = "GOLDILOCKS"
    nets = sum(d != "stable" for d in (dollar, taux))
    confiance = {0: "faible", 1: "moyenne", 2: "haute"}[nets]
    return {**base, "regime": regime, "confiance": confiance,
            "justification": f"{lecture} ; confiance {confiance} ({nets} signal(s) macro net(s) sur 2)."}
