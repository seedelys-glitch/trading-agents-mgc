# -*- coding: utf-8 -*-
"""
Ce que les agents savent RÉELLEMENT faire. Chaque module expose :
  TYPE     nom du type de mission
  AGENT    numéro de l'agent qui l'exécute
  TITRE    libellé lisible
  PARAMS   paramètres attendus (nom -> explication)
  executer(ctx) -> résultat (dict), en notant chaque étape avec ctx.etape(role, libellé)
"""

from . import (analyse_vwap_ema, controle_donnees, demande_directeur, extraction_regles, indexation_bibliotheque,
               replay_strategie_v1, synthese_directeur, verification_analyse, verification_replay)

MODULES = [analyse_vwap_ema, verification_analyse, controle_donnees, replay_strategie_v1, verification_replay,
           extraction_regles, indexation_bibliotheque, synthese_directeur, demande_directeur]
TYPES = {m.TYPE: m for m in MODULES}


def catalogue():
    return [{"type": m.TYPE, "agent": m.AGENT, "titre": m.TITRE, "params": m.PARAMS,
             "interne": getattr(m, "INTERNE", False)} for m in MODULES]
