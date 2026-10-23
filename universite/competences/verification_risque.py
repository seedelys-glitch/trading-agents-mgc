# -*- coding: utf-8 -*-
"""
Agent 9 — recompte une évaluation de risque de l'agent 8 SANS le moteur de la Salle (mgc/risque.py) :
calcul refait en Python pur, en ticks entiers (MGC : tick 0,10 = 1 $ par contrat, 1 point = 10 $), avec les
réglages enregistrés dans le document. Compare contrats, risque net, risque total, ratio et vetos.
"""

import math

TYPE = "verification_risque"
AGENT = 9
TITRE = "Recompter une évaluation de risque"
PARAMS = {"document": "numéro du document à recompter"}
INTERNE = True
TOLERANCE = 0.011        # dollars / ratio : arrondis au centime


def recalculer(sens, entree, stop, tp1, reg, perte_du_jour):
    """Le même raisonnement écrit autrement : tout en ticks entiers, sans importer la Salle."""
    t_entree, t_stop, t_tp1 = (round(x * 10) for x in (entree, stop, tp1))
    if any(abs(x * 10 - round(x * 10)) > 1e-6 or x <= 0 for x in (entree, stop, tp1)):
        return {"grille": False}
    coherent = t_stop < t_entree < t_tp1 if sens == "achat" else t_tp1 < t_entree < t_stop
    ticks_risque = abs(t_entree - t_stop)
    couts = reg["frais_aller_retour_usd"] + 2 * reg["glissement_ticks_par_cote"]
    net = ticks_risque + couts                                  # 1 tick = 1 $
    budget = min(reg["capital_usd"] * reg["risque_pct"] / 100,
                 reg["limite_perte_jour_usd"] - max(0.0, perte_du_jour))
    possibles = math.floor(budget / net + 1e-9) if net > 0 and budget > 0 else 0
    contrats = min(possibles, reg["max_contrats"])
    ratio = (abs(t_tp1 - t_entree) - couts) / net if net > 0 else 0.0
    bloque = not coherent or ticks_risque < 1 or contrats < 1 or ratio < reg["ratio_min"]
    return {"grille": True, "coherent": coherent, "risque_net": net, "contrats_calcules": max(contrats, 0),
            "risque_total": net * max(contrats, 0), "ratio": ratio, "exploitable": not bloque}


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc or "evaluation" not in doc["donnees"]:
        raise ValueError(f"document de risque {ident} introuvable")
    d = doc["donnees"]
    p, r = d["parametres"], d["evaluation"]
    ctx.etape("documentaliste", f"Relit l'évaluation {ident} et les réglages utilisés")
    ctx.etape("chercheur", "Refait le calcul en ticks, sans le moteur de risque")
    moi = recalculer(str(p.get("sens", "")).strip().lower(), float(p["entree"]), float(p["stop"]), float(p["tp1"]),
                     d["reglages"], d["perte_du_jour"])
    ecarts = []
    if not moi["grille"] or "risque_net_par_contrat" not in r:
        if r["exploitable"]:
            ecarts.append("prix hors grille ou sens inconnu, mais l'évaluation est déclarée exploitable")
    else:
        for nom, a, b in (("risque net par contrat", r["risque_net_par_contrat"], moi["risque_net"]),
                          ("contrats calculés", r["contrats_calcules"], moi["contrats_calcules"]),
                          ("risque total", r["risque_total_net"], moi["risque_total"]),
                          ("ratio net au TP1", r["ratio_net_tp1"], moi["ratio"])):
            if abs(float(a) - float(b)) > TOLERANCE:
                ecarts.append(f"{nom} : {a} dans le document, {round(b, 2)} recalculé")
        if bool(r["exploitable"]) != moi["exploitable"]:
            ecarts.append(f"avis : {'exploitable' if r['exploitable'] else 'refusé'} dans le document, "
                          f"{'exploitable' if moi['exploitable'] else 'refusé'} recalculé")
    verdict = "verifie" if not ecarts else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Évaluation contrôlée : n° {ident} « {doc['titre']} ».",
              f"Recalcul indépendant en ticks entiers (tolérance {TOLERANCE} sur les montants et le ratio)."]
    lignes += [f"Écart : {e}" for e in ecarts] or ["Tous les chiffres concordent."]
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Recompte du risque {ident}", "\n".join(lignes),
                      donnees={"document": ident, "ecarts": ecarts, "verdict": verdict, "recalcul": moi},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Risque {ident} : {'vérifié' if verdict == 'verifie' else 'REJETÉ'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Évaluation de risque {ident} rejetée au recompte.", pv)
    return {"document": ident, "verdict": verdict, "ecarts": ecarts}
