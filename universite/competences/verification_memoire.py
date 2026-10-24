# -*- coding: utf-8 -*-
"""Agent 9 — contrôle d'une réponse de l'Archiviste (agent 16) : chaque bloc cité existe encore, avec la même
origine, et son texte commence bien par le passage cité."""

TYPE = "verification_memoire"
AGENT = 9
TITRE = "Contrôler les citations d'une réponse de l'Archiviste"
PARAMS = {"document": "numéro du document à contrôler"}
INTERNE = True


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc or doc["genre"] != "memoire":
        raise ValueError(f"réponse de l'Archiviste {ident} introuvable")
    blocs = doc["donnees"].get("blocs", [])
    ctx.etape("documentaliste", f"Relit les {len(blocs)} bloc(s) cités")
    problemes = []
    ctx.etape("chercheur", "Retrouve chaque bloc dans la mémoire, sans passer par l'index")
    for c in blocs:
        b = ctx.base.un("SELECT ref, texte FROM memoire_blocs WHERE id=?", (c["id"],))
        if not b:
            problemes.append(f"bloc {c['id']} introuvable")
        elif b["ref"] != c["ref"] or not b["texte"].startswith(c["debut"]):
            problemes.append(f"bloc {c['id']} modifié depuis la réponse")
    verdict = "verifie" if not problemes else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Réponse contrôlée : n° {ident}."] + ([f"Problème : {p}" for p in problemes]
                                                   or ["Tous les blocs cités existent et disent bien ce qui est cité."])
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Contrôle de la mémoire {ident}", "\n".join(lignes),
                      donnees={"document": ident, "problemes": problemes, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Réponse {ident} : {'vérifiée' if verdict == 'verifie' else 'REJETÉE'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Réponse de l'Archiviste {ident} rejetée.", pv)
    return {"document": ident, "verdict": verdict, "problemes": problemes}
