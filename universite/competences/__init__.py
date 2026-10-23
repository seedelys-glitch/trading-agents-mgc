# -*- coding: utf-8 -*-
"""
Ce que les agents savent RÉELLEMENT faire. Chaque module expose :
  TYPE     nom du type de mission
  AGENT    numéro de l'agent qui l'exécute
  TITRE    libellé lisible
  PARAMS   paramètres attendus (nom -> explication)
  executer(ctx) -> résultat (dict), en notant chaque étape avec ctx.etape(role, libellé)
"""

from . import (analyse_fibo, analyse_flux, analyse_ichimoku, analyse_smc, analyse_vwap_ema, calendrier_macro,
               controle_donnees, demande_directeur, discours_fed, evaluation_risque, extraction_regles,
               import_tradingview, indexation_bibliotheque, precedents, reaction_annonces, replay_strategie_v1, synthese_directeur,
               verification_analyse, verification_calendrier, verification_citations, verification_discours,
               verification_reactions, verification_replay, verification_reproductibilite, verification_risque)

MODULES = [analyse_smc, analyse_fibo, analyse_ichimoku, calendrier_macro, analyse_vwap_ema, analyse_flux, evaluation_risque,
           reaction_annonces, discours_fed, precedents, verification_analyse, verification_reproductibilite,
           verification_risque, verification_calendrier, verification_reactions, verification_discours,
           verification_citations, import_tradingview, controle_donnees, replay_strategie_v1, verification_replay, extraction_regles,
           indexation_bibliotheque, synthese_directeur, demande_directeur]
TYPES = {m.TYPE: m for m in MODULES}


def catalogue():
    return [{"type": m.TYPE, "agent": m.AGENT, "titre": m.TITRE, "params": m.PARAMS,
             "interne": getattr(m, "INTERNE", False)} for m in MODULES]
