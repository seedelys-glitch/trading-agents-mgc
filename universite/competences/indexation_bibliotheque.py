# -*- coding: utf-8 -*-
"""
Agent 9 — met les documents vérifiés de l'université dans la bibliothèque (extraits) et, si LM Studio a un
modèle d'embeddings chargé ou chargeable, ajoute les vecteurs pour la recherche par le sens.
"""

from .. import bibliotheque

TYPE = "indexation_bibliotheque"
AGENT = 9
TITRE = "Ranger les documents dans la bibliothèque"
PARAMS = {}


def executer(ctx):
    ctx.etape("documentaliste", "Rassemble les documents vérifiés")
    docs = ctx.base.lire("SELECT id, titre, contenu FROM documents WHERE statut='verifie'")
    ctx.etape("connaissances", "Découpe et range les documents en extraits", "verification")
    ecrits = sum(bibliotheque.indexer_texte(ctx.base, f"document:{d['id']}", d["titre"], d["contenu"]) for d in docs)
    ctx.etape("chercheur", "Ajoute la recherche par le sens (si LM Studio le permet)")
    modele = ctx.moteur.reglages.get("ia_embeddings", "")
    vecteurs, remarque = 0, ""
    if not modele:
        remarque = "Recherche par le sens désactivée (aucun modèle d'embeddings choisi dans les réglages)."
    else:
        try:
            vecteurs = bibliotheque.vectoriser(ctx.base, ctx.moteur.reglages["ia_url"], modele)
        except OSError as e:
            remarque = f"Recherche par le sens indisponible ({e}) : la recherche par mots reste active."
    ctx.detail({"documents": len(docs), "extraits": ecrits, "vecteurs": vecteurs})
    total = ctx.base.un("SELECT COUNT(*) AS n, SUM(vecteur IS NOT NULL) AS v FROM extraits")
    return {"documents": len(docs), "extraits_ecrits": ecrits, "vecteurs_ajoutes": vecteurs,
            "extraits_total": total["n"], "extraits_avec_sens": total["v"] or 0, "remarque": remarque}
