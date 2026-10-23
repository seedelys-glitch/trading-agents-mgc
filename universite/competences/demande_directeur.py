# -*- coding: utf-8 -*-
"""
Agent 14 — le directeur reçoit une demande de Jabran et la confie à l'agent qui sait réellement la faire.
Si aucun agent n'a la compétence, il le dit (pas de mission fantôme).
"""

from .. import agents

TYPE = "demande_directeur"
AGENT = 14
TITRE = "Demande transmise par le directeur"
PARAMS = {"type": "type de mission demandé", "params": "paramètres de cette mission", "consigne": "texte libre"}


def executer(ctx):
    from . import TYPES  # import tardif : le catalogue se charge lui-même

    genre = ctx.params.get("type", "")
    ctx.etape("documentaliste", f"Reçoit la demande : {ctx.params.get('consigne') or genre}")
    comp = TYPES.get(genre)
    if comp is None or getattr(comp, "INTERNE", False) or comp.AGENT == agents.DIRECTEUR:
        raise ValueError(f"aucun agent ne sait faire « {genre} » pour l'instant")
    ctx.etape("chercheur", f"Choisit l'agent compétent : {agents.agent(comp.AGENT)['nom']}")
    m = ctx.demander(comp.AGENT, genre, comp.TITRE, ctx.params.get("params") or {},
                     ctx.params.get("consigne") or "Demande de Jabran.")
    ctx.etape("connaissances", f"Suit la mission {m}", "verification")
    return {"mission_confiee": m, "agent": comp.AGENT}
