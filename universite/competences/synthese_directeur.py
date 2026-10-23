# -*- coding: utf-8 -*-
"""
Agent 14 — synthèse du directeur : uniquement à partir de ce qui existe dans la base
(missions, documents et leur statut de vérification). Il n'ajoute aucune analyse de marché.
"""

import time

from .. import agents

TYPE = "synthese_directeur"
AGENT = 14
TITRE = "Synthèse du directeur"
PARAMS = {"heures": "période couverte (24 par défaut)"}


def executer(ctx):
    from . import TYPES

    heures = float(ctx.params.get("heures") or 24)
    depuis = time.time() - heures * 3600
    ctx.etape("documentaliste", f"Relit les missions et les documents des {heures:g} dernières heures")
    missions = ctx.base.lire("SELECT agent, statut, COUNT(*) AS n FROM missions WHERE cree>=? GROUP BY agent, statut",
                             (depuis,))
    docs = ctx.base.lire("SELECT id, agent, genre, titre, statut FROM documents WHERE cree>=? ORDER BY id DESC",
                         (depuis,))
    ctx.etape("chercheur", "Fait le point agent par agent")
    branches = {m.AGENT for m in TYPES.values()}
    lignes = [f"Période : {heures:g} dernières heures.", ""]
    for a in agents.AGENTS:
        if a["n"] not in branches:
            continue
        compte = {m["statut"]: m["n"] for m in missions if m["agent"] == a["n"]}
        lignes.append(f"{a['nom']} : {compte.get('terminee', 0)} terminée(s), {compte.get('en_cours', 0)} en cours, "
                      f"{compte.get('en_attente', 0)} en attente, {compte.get('erreur', 0)} en erreur.")
    absents = [a["nom"] for a in agents.AGENTS if a["n"] not in branches]
    lignes += ["", f"En construction (aucune compétence branchée) : {', '.join(absents)}." if absents else "", ""]
    ctx.etape("professeur", "Rédige la synthèse")
    verifies = [d for d in docs if d["statut"] == "verifie" and d["genre"] not in ("verification", "synthese")]
    rejetes = [d for d in docs if d["statut"] == "rejete"]
    attente = [d for d in docs if d["statut"] == "a_verifier"]
    lignes.append(f"Travaux vérifiés (analyses, replays, risque, macro, réactions) : {len(verifies)} ; rejetées : {len(rejetes)} ; en attente de vérification : {len(attente)}.")
    lignes += [f"  - n° {d['id']} {d['titre']} (vérifiée)" for d in verifies[:10]]
    lignes += [f"  - n° {d['id']} {d['titre']} (REJETÉE)" for d in rejetes[:10]]
    if not docs:
        lignes.append("Aucun document produit sur la période.")
    ctx.etape("connaissances", "Classe la synthèse", "verification")
    doc = ctx.document("synthese", f"Synthèse du directeur ({heures:g} h)", "\n".join(lignes),
                       donnees={"verifies": [d["id"] for d in verifies], "rejetes": [d["id"] for d in rejetes]},
                       sources=[{"document": d["id"]} for d in docs[:50]], role="professeur")
    return {"document": doc, "verifies": len(verifies), "rejetes": len(rejetes)}
