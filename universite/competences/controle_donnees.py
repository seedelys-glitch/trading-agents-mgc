# -*- coding: utf-8 -*-
"""Agent 13 — inventaire et contrôle qualité d'un jeu de bougies (nombre, période, trous, coupures)."""

import datetime as dt

from .. import donnees

TYPE = "controle_donnees"
AGENT = 13
TITRE = "Contrôle qualité d'un jeu de bougies"
PARAMS = {"jeu": "numéro du jeu de bougies"}


def _date(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%d/%m/%Y %H:%M UTC")


def executer(ctx):
    jeu = int(ctx.params["jeu"])
    ctx.etape("documentaliste", f"Inventorie le jeu {jeu}")
    c = donnees.controle(ctx.base, jeu)
    ctx.etape("chercheur", "Cherche les trous et les coupures pendant les heures de séance")
    ctx.detail({u: {k: r[k] for k in ("n", "petits_trous", "longues_coupures")} for u, r in c["unites"].items()})
    ctx.etape("professeur", "Rédige le constat")
    j = c["jeu"]
    lignes = [f"Jeu « {j['nom']} » — source : {j['source']} ({'temps réel' if j['temps_reel'] else 'différé / historique'}).",
              f"Note : {j['note']}" if j["note"] else "", ""]
    if not c["unites"]:
        lignes.append("Ce jeu ne contient aucune bougie.")
    for u, r in sorted(c["unites"].items(), key=lambda x: donnees.PERIODES[x[0]]):
        lignes.append(f"{u} : {r['n']} bougies, du {_date(r['debut'])} au {_date(r['fin'])} ; "
                      f"{r['petits_trous']} petit(s) trou(s), {r['longues_coupures']} longue(s) coupure(s)"
                      + (f" (la plus longue : {r['plus_longue_coupure_h']} h)." if r["longues_coupures"] else "."))
    lignes += ["", "Pause quotidienne (16 h–17 h à Chicago) et week-end ne comptent pas comme des trous.",
               "Les jours fériés CME apparaissent comme de longues coupures : c'est normal."]
    ctx.etape("connaissances", "Classe le constat", "verification")
    doc = ctx.document("donnees", f"Contrôle du jeu « {j['nom']} »", "\n".join(x for x in lignes if x is not None),
                       donnees={"jeu": jeu, "unites": c["unites"]}, sources=[{"jeu": jeu}], role="professeur")
    return {"document": doc, "unites": {u: r["n"] for u, r in c["unites"].items()}}
