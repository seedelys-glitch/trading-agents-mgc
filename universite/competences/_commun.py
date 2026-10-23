# -*- coding: utf-8 -*-
"""
Outils communs aux analyses de la vague 1 (SMC, Fibonacci, Ichimoku) : chargement des bougies fermées à l'instant t,
calcul avec les fonctions de la Salle (calculs.py), compte rendu, puis contrôle de reproductibilité par l'agent 9.

Chaque module d'analyse fournit : UNITES, HISTORIQUE, calculer(cadres) -> dict, rediger(resultat) -> [lignes].
"""

import datetime as dt
import json
import time
from zoneinfo import ZoneInfo

from .. import config, donnees


def heure(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %Hh%M")


def cadre(lignes):
    config.salle_importable()
    import pandas as pd

    return pd.DataFrame([r[1:] for r in lignes], columns=["o", "h", "l", "c", "v"],
                        index=pd.DatetimeIndex([pd.Timestamp(r[0], unit="s", tz="UTC") for r in lignes]))


def charger(base, jeu, unites, instant, historique):
    cadres, sources = {}, []
    for u in unites:
        f = donnees.fenetre(base, jeu, u, instant, historique)
        if f["bougies"]:
            cadres[u] = cadre(f["bougies"])
            sources.append({"jeu": jeu, "unite": u, "n": len(f["bougies"]), "debut": f["bougies"][0][0],
                            "fin": f["bougies"][-1][0], "reconstruite_depuis": f["reconstruite_depuis"]})
    return cadres, sources


def recharger(base, sources, instant):
    """Les mêmes fenêtres qu'au moment de l'analyse (pour le contrôle de reproductibilité)."""
    cadres = {}
    for s in sources:
        lignes = [b for b in donnees.fenetre(base, s["jeu"], s["unite"], instant, None)["bougies"]
                  if s["debut"] <= b[0] <= s["fin"]]
        cadres[s["unite"]] = cadre(lignes)
    return cadres


def normaliser(obj):
    """Résultat -> forme JSON stable (pour comparer deux calculs)."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str, sort_keys=True))


def executer_analyse(ctx, module, titre):
    p = ctx.params
    jeu = int(p["jeu"])
    instant = float(p.get("instant") or time.time())
    infos = ctx.base.un("SELECT * FROM jeux WHERE id=?", (jeu,))
    if not infos:
        raise ValueError(f"jeu de bougies {jeu} introuvable")
    ctx.etape("documentaliste", f"Rassemble les bougies fermées au {heure(instant)} (jeu « {infos['nom']} »)")
    cadres, sources = charger(ctx.base, jeu, module.UNITES, instant, module.HISTORIQUE)
    ctx.detail({s["unite"]: s["n"] for s in sources})
    if not cadres:
        raise ValueError("aucune bougie fermée à cet instant dans ce jeu")
    ctx.etape("chercheur", f"Calcule ({', '.join(cadres)}) avec les fonctions de la Salle des marchés")
    resultat = normaliser(module.calculer(cadres))
    ctx.etape("professeur", "Rédige le compte rendu et ses limites")
    nature = "temps réel" if infos["temps_reel"] else "différées ou historiques"
    lignes = [f"Instant analysé : {heure(instant)} (heure de Paris). Données : {infos['source']} — {infos['nom']} ({nature}).",
              ""] + module.rediger(resultat) + ["", "Limites : description de la situation, pas un signal. "
                                                "Aucune bougie postérieure à l'instant n'a été lue."]
    ctx.etape("connaissances", "Classe le document et demande son contrôle au secrétaire-auditeur", "verification")
    doc = ctx.document("analyse", f"{titre} — {heure(instant)}", "\n".join(lignes),
                       donnees={"calcul": module.TYPE, "jeu": jeu, "instant": instant, "resultat": resultat},
                       sources=sources, role="professeur", statut="a_verifier")
    verif = ctx.demander(9, "verification_reproductibilite", f"Contrôler le document {doc} ({titre})",
                         {"document": doc}, "Refaire le calcul sur les mêmes bougies.", document=doc)
    return {"document": doc, "verification": verif}
