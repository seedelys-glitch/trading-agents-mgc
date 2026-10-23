# -*- coding: utf-8 -*-
"""Agent 9 — contrôle d'une recherche de précédents (agent 11) : chaque passage cité existe tel quel dans la
bibliothèque et chaque annonce citée existe dans l'historique, avec la même date."""

TYPE = "verification_citations"
AGENT = 9
TITRE = "Contrôler les citations d'une recherche de précédents"
PARAMS = {"document": "numéro du document à contrôler"}
INTERNE = True


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc or "question" not in doc["donnees"]:
        raise ValueError(f"recherche de précédents {ident} introuvable")
    d = doc["donnees"]
    ctx.etape("documentaliste", f"Relit les {len(d['extraits'])} passage(s) et {len(d['annonces'])} annonce(s) cités")
    problemes = []
    ctx.etape("chercheur", "Retrouve chaque passage et chaque annonce")
    for e in d["extraits"]:
        x = ctx.base.un("SELECT texte FROM extraits WHERE id=?", (e["id"],))
        if not x or not x["texte"].startswith(e["debut"]):
            problemes.append(f"passage {e['id']} introuvable ou modifié")
    for i in d["annonces"]:
        if not ctx.base.un("SELECT id FROM annonces WHERE id=?", (i,)):
            problemes.append(f"annonce {i} absente de l'historique")
    verdict = "verifie" if not problemes else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Recherche contrôlée : n° {ident}."] + ([f"Problème : {p}" for p in problemes]
                                                     or ["Toutes les citations existent telles quelles."])
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Contrôle des citations {ident}", "\n".join(lignes),
                      donnees={"document": ident, "problemes": problemes, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Précédents {ident} : {'vérifiés' if verdict == 'verifie' else 'REJETÉS'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Recherche de précédents {ident} rejetée.", pv)
    return {"document": ident, "verdict": verdict, "problemes": problemes}
