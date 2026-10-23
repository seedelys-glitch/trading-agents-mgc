# -*- coding: utf-8 -*-
"""
Agent 9 — contrôle d'un point macro de l'agent 5 : relit les annonces gardées dans la base et refait les blocages
de l'instant avec son propre code (sans mgc/annonces.py), à partir du genre enregistré et des réglages du document.
"""

import datetime as dt
from zoneinfo import ZoneInfo

TYPE = "verification_calendrier"
AGENT = 9
TITRE = "Contrôler un point macro"
PARAMS = {"document": "numéro du document à contrôler"}
INTERNE = True
PARIS = ZoneInfo("Europe/Paris")


def blocages_attendus(annonces, instant, reg):
    """Liste de (genre, titre) qui bloquent à l'instant."""
    jour = dt.datetime.fromtimestamp(instant, PARIS).date()
    fenetres = {"discours_fed": (reg["discours_fed_avant_min"], reg["discours_fed_apres_min"]),
                "forte": (reg["annonce_avant_min"], reg["annonce_apres_min"]),
                "reunion_fomc": (reg["annonce_avant_min"], reg["annonce_apres_min"])}
    res = []
    for a in annonces:
        if a["genre"] == "reunion_fomc" and dt.datetime.fromtimestamp(a["quand"], PARIS).date() == jour:
            res.append(("jour_fomc", a["titre"]))
        elif a["genre"] in fenetres:
            avant, apres = fenetres[a["genre"]]
            if a["quand"] - 60 * avant <= instant <= a["quand"] + 60 * apres:
                res.append(("fenetre", a["titre"]))
    return res


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc or "blocages" not in doc["donnees"]:
        raise ValueError(f"point macro {ident} introuvable")
    d = doc["donnees"]
    ctx.etape("documentaliste", f"Relit le point macro {ident} et les annonces gardées")
    proches = ctx.base.lire("SELECT * FROM annonces WHERE quand BETWEEN ? AND ?", (d["instant"] - 86400, d["instant"] + 86400))
    ctx.etape("chercheur", "Refait les blocages avec son propre code")
    attendus = blocages_attendus(proches, d["instant"], d["reglages"])
    problemes = []
    for _genre, titre in attendus:
        if not any(titre in b for b in d["blocages"]):
            problemes.append(f"blocage manquant : {titre}")
    if len(set(attendus)) != len(d["blocages"]):
        problemes.append(f"{len(d['blocages'])} blocage(s) dans le document, {len(set(attendus))} attendu(s)")
    for i in d["annonces"]:
        if not ctx.base.un("SELECT id FROM annonces WHERE id=?", (i,)):
            problemes.append(f"annonce {i} citée mais absente de l'historique")
    verdict = "verifie" if not problemes else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Point macro contrôlé : n° {ident}.", "Blocages refaits avec un code indépendant, à partir de l'historique."]
    lignes += [f"Problème : {p}" for p in problemes] or ["Blocages identiques, annonces présentes dans l'historique."]
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Contrôle du point macro {ident}", "\n".join(lignes),
                      donnees={"document": ident, "problemes": problemes, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Point macro {ident} : {'vérifié' if verdict == 'verifie' else 'REJETÉ'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Point macro {ident} rejeté au contrôle.", pv)
    return {"document": ident, "verdict": verdict, "problemes": problemes}
