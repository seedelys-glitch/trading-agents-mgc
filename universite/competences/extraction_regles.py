# -*- coding: utf-8 -*-
"""
Agent 9 — lit les fichiers de stratégie de Jabran (lecture seule) et propose chaque règle à sa validation.
Une règle déjà connue n'est reproposée que si son texte a changé (nouvelle version). Les fichiers sont aussi
découpés en extraits pour la recherche de la bibliothèque.
"""

from pathlib import Path

from .. import bibliotheque

TYPE = "extraction_regles"
AGENT = 9
TITRE = "Extraire les règles des fichiers de stratégie"
PARAMS = {"fichiers": "chemins des fichiers (vide = STRATEGIE.md du dossier « bot trad »)"}


def executer(ctx):
    fichiers = [Path(f) for f in (ctx.params.get("fichiers") or bibliotheque.fichiers_par_defaut())]
    ctx.etape("documentaliste", f"Ouvre {len(fichiers)} fichier(s) de référence, en lecture seule")
    trouves = [f for f in fichiers if f.is_file()]
    if not trouves:
        raise ValueError("aucun fichier de stratégie trouvé : " + ", ".join(str(f) for f in fichiers))
    ctx.etape("chercheur", "Repère chaque règle (un point de liste) avec sa section et sa ligne")
    bilan = {"nouvelles": 0, "versions": 0, "inchangees": 0, "extraits": 0, "fichiers": [str(f) for f in trouves]}
    for f in trouves:
        texte = f.read_text(encoding="utf-8", errors="replace")
        for r in bibliotheque.lire_regles(texte, f.name):
            effet = bibliotheque.proposer(ctx.base, r, ctx.agent)
            bilan[{"nouvelle": "nouvelles", "version": "versions", None: "inchangees"}[effet]] += 1
        bilan["extraits"] += bibliotheque.indexer_texte(ctx.base, f"fichier:{f.name}", f.name, texte)
    ctx.detail(bilan)
    ctx.etape("professeur", "Rédige le compte rendu")
    texte = (f"Fichiers lus : {', '.join(Path(f).name for f in bilan['fichiers'])}.\n"
             f"Règles nouvelles proposées : {bilan['nouvelles']} ; nouvelles versions : {bilan['versions']} ; "
             f"inchangées : {bilan['inchangees']}.\nExtraits mis à jour pour la recherche : {bilan['extraits']}.\n\n"
             "Chaque règle proposée attend ta décision dans la Bibliothèque (valider, corriger ou rejeter). "
             "Le texte est repris mot pour mot du fichier, sans reformulation.")
    ctx.etape("connaissances", "Classe le compte rendu", "verification")
    doc = ctx.document("bibliotheque", "Extraction des règles de stratégie", texte, donnees=bilan,
                       sources=[{"fichier": f} for f in bilan["fichiers"]], role="connaissances", statut="verifie")
    return {"document": doc, **bilan}
