# -*- coding: utf-8 -*-
"""
Agent 16 — l'Archiviste : retrouve dans la mémoire ce qui répond à une question et le redonne bloc par bloc
(date, dossier, session, numéro). Le secrétaire-auditeur (agent 9) contrôle ensuite que chaque bloc cité existe
et que le passage cité s'y trouve mot pour mot.
"""

from .. import memoire

TYPE = "recherche_memoire"
AGENT = memoire.ARCHIVISTE
TITRE = "Retrouver une information dans la mémoire"
PARAMS = {"question": "ce qu'on cherche (ex. décision sur le break-even)",
          "dossier": "facultatif : un seul dossier (Jarvis, Université, Stratégie…)"}


def executer(ctx):
    question = str(ctx.params.get("question") or "").strip()
    if not question:
        raise ValueError("question vide")
    dossier = memoire.dossier_nomme(ctx.params.get("dossier"))
    ctx.etape("documentaliste", f"Cherche « {memoire.court(question, 80)} » dans l'index"
                                + (f" (dossier {dossier})" if dossier else ""))
    trouves = memoire.chercher(ctx.base, question, dossier=dossier, n=8)
    ctx.detail({"blocs": len(trouves)})
    ctx.etape("professeur", "Rédige la réponse, bloc par bloc, avec la source de chacun")
    cites, lignes = [], [f"Question : {question}", ""]
    if not trouves:
        lignes.append("Rien trouvé dans la mémoire pour cette question.")
    for b in trouves:
        complet = memoire.bloc(ctx.base, b["id"])
        passage = memoire.court(complet["texte"], 500)
        cites.append({"id": b["id"], "ref": complet["ref"], "debut": complet["texte"][:120]})
        lignes += [f"Bloc n° {b['id']} — {memoire.date_paris(b['debut'])} — dossier {b['dossier']} — {b['session']}",
                   f"{b['titre']}", passage, ""]
    lignes.append("Limites : seulement ce que le Scribe a noté ; rien n'est ajouté de mémoire.")
    ctx.etape("connaissances", "Classe la réponse et demande le contrôle des citations", "verification")
    doc = ctx.document("memoire", f"Mémoire : {memoire.court(question, 120)}", "\n".join(lignes),
                       donnees={"question": question, "dossier": dossier, "blocs": cites},
                       sources=[{"bloc": c["id"], "ref": c["ref"]} for c in cites], role="professeur",
                       statut="a_verifier" if cites else "verifie")
    verif = None
    if cites:
        verif = ctx.demander(9, "verification_memoire", f"Contrôler les citations du document {doc}",
                             {"document": doc}, "Chaque bloc cité existe et dit bien ce qui est cité.", document=doc)
    return {"document": doc, "blocs": len(cites), "verification": verif}
