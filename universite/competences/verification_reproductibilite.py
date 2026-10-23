# -*- coding: utf-8 -*-
"""
Agent 9 — contrôle de REPRODUCTIBILITÉ d'une analyse de la vague 1 (SMC, Fibonacci, Ichimoku) :
mêmes bougies relues dans la base, aucune bougie non fermée à l'instant, calcul refait, résultat identique.
Ce n'est pas un recalcul indépendant (même fonction de calculs.py) : le procès-verbal le dit clairement.
"""

from . import _commun

TYPE = "verification_reproductibilite"
AGENT = 9
TITRE = "Contrôle de reproductibilité d'une analyse"
PARAMS = {"document": "numéro du document à contrôler"}
INTERNE = True
DUREES = {"M1": 60, "M3": 180, "M5": 300, "M15": 900, "H1": 3600, "D1": 86400}


def executer(ctx):
    from . import TYPES

    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc:
        raise ValueError(f"document {ident} introuvable")
    d = doc["donnees"]
    module = TYPES.get(d.get("calcul"))
    if module is None or not hasattr(module, "calculer"):
        raise ValueError("ce document ne se contrôle pas par reproductibilité")
    ctx.etape("documentaliste", f"Relit le document {ident} et ses {len(doc['sources'])} fenêtres de bougies")
    problemes = []
    for s in doc["sources"]:
        if s["fin"] + DUREES[s["unite"]] > d["instant"]:
            problemes.append(f"{s['unite']} : bougie non fermée à l'instant analysé (look-ahead)")
    cadres = _commun.recharger(ctx.base, doc["sources"], d["instant"])
    for s in doc["sources"]:
        if len(cadres[s["unite"]]) != s["n"]:
            problemes.append(f"{s['unite']} : {len(cadres[s['unite']])} bougies retrouvées au lieu de {s['n']}")
    ctx.etape("chercheur", "Refait le calcul sur les mêmes bougies et compare")
    refait = _commun.normaliser(module.calculer(cadres))
    if refait != d["resultat"]:
        problemes.append("le calcul refait ne donne pas le même résultat que le document")
    verdict = "verifie" if not problemes else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Document contrôlé : n° {ident} « {doc['titre']} ».",
              "Nature du contrôle : reproductibilité (mêmes bougies, même fonction de calcul, aucune bougie future).",
              "Ce n'est pas un recalcul indépendant."]
    lignes += [f"Problème : {p}" for p in problemes] or ["Résultat identique, aucune bougie future."]
    lignes += ["", f"Verdict : {'VÉRIFIÉ (reproductible)' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict et prévient l'auteur", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Contrôle du document {ident}", "\n".join(lignes),
                      donnees={"document": ident, "problemes": problemes, "verdict": verdict, "nature": "reproductibilite"},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Document {ident} : {'reproductible' if verdict == 'verifie' else 'REJETÉ'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Document {ident} rejeté au contrôle.", pv)
    return {"document": ident, "verdict": verdict, "problemes": problemes}
