# -*- coding: utf-8 -*-
"""
Agent 9 — vérification d'un replay : recompte les trades et recalcule les statistiques en Python pur
(sans mgc/stats.py), contrôle que chaque trade est dans la période et dans le bon ordre, et que le
découpage entraînement / validation / test ne se chevauche pas.
"""

import math

TYPE = "verification_replay"
AGENT = 9
TITRE = "Vérification d'un replay"
PARAMS = {"document": "numéro du rapport de replay"}
INTERNE = True


def _stats(rs):
    n = len(rs)
    if not n:
        return {"nombre": 0}
    gagnants = sum(r > 0 for r in rs)
    p, z = gagnants / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    cumul = sommet = pire = 0.0
    for r in rs:
        cumul += r
        sommet = max(sommet, cumul)
        pire = max(pire, sommet - cumul)
    return {"nombre": n, "gagnants": gagnants, "esperance_R": round(sum(rs) / n, 3), "drawdown_max_R": round(pire, 2),
            "wilson_95": [round(max(0.0, centre - marge), 4), round(min(1.0, centre + marge), 4)]}


def _iso(s):
    import datetime as dt
    return dt.datetime.fromisoformat(s).timestamp()


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc:
        raise ValueError(f"document {ident} introuvable")
    d = doc["donnees"]
    ctx.etape("documentaliste", f"Relit le rapport {ident} ({len(d['trades'])} trades)")
    problemes, ecarts = [], []

    ctx.etape("chercheur", "Recompte les trades et recalcule les statistiques")
    precedent = None
    for i, t in enumerate(d["trades"]):
        o, f = _iso(t["ouverture"]), _iso(t["fermeture"])
        if not d["debut"] <= o <= f <= d["fin"]:
            problemes.append(f"trade {i + 1} hors de la période ou fermé avant d'être ouvert")
        if precedent is not None and o < precedent:
            problemes.append(f"trade {i + 1} ouvert avant la fermeture du précédent")
        precedent = f
    recalcul = _stats([t["R_net"] for t in d["trades"]])
    annonce = d["tout"]
    for cle in ("nombre", "gagnants", "esperance_R", "drawdown_max_R", "wilson_95"):
        if cle in recalcul and recalcul[cle] != annonce.get(cle):
            ecarts.append(f"{cle} : annoncé {annonce.get(cle)}, recalculé {recalcul[cle]}")
    parts = list(d["parts"].values())
    if any(abs(a["fin"] - b["debut"]) > 1e-6 for a, b in zip(parts, parts[1:], strict=False)):
        problemes.append("découpage entraînement / validation / test discontinu")
    if sum(p["net"]["nombre"] for p in parts) != len(d["trades"]):
        problemes.append("la somme des trades des trois parties ne fait pas le total")

    verdict = "verifie" if not problemes and not ecarts else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Rapport vérifié : n° {ident} « {doc['titre']} ».",
              f"Trades recomptés : {recalcul['nombre']} ; espérance recalculée : {recalcul.get('esperance_R')} R ; "
              f"drawdown recalculé : {recalcul.get('drawdown_max_R')} R."]
    lignes += [f"Écart : {e}" for e in ecarts] + [f"Problème : {p}" for p in problemes]
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict et prévient l'auteur", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Vérification du replay {ident}", "\n".join(lignes),
                      donnees={"document": ident, "ecarts": ecarts, "problemes": problemes, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Replay {ident} : {'vérifié' if verdict == 'verifie' else 'REJETÉ'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Replay {ident} rejeté.", pv)
    return {"document": ident, "verdict": verdict, "ecarts": ecarts, "problemes": problemes}
