# -*- coding: utf-8 -*-
"""
Agent 11 — historien : retrouve les précédents d'un thème (ex. « inflation elevated », « CPI ») dans ce que
l'université a réellement gardé : textes des discours de la Fed (agent 10), règles et documents de la bibliothèque,
annonces du calendrier (agent 5) avec leur date. Chaque précédent a sa date et sa source ; rien n'est cité de mémoire.
"""

import datetime as dt

from .. import bibliotheque

TYPE = "precedents"
AGENT = 11
TITRE = "Retrouver les précédents d'un thème (discours, annonces, bibliothèque)"
PARAMS = {"question": "thème à chercher (mots en anglais pour les discours de la Fed)"}


def _date(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%d/%m/%Y")


def executer(ctx):
    question = str(ctx.params.get("question") or "").strip()[:200]
    if not question:
        raise ValueError("il faut un thème à chercher")
    ctx.etape("documentaliste", f"Cherche « {question} » dans la bibliothèque")
    trouves = [r for r in bibliotheque.rechercher(ctx.base, question, n=12) if r["genre"] == "extrait"]
    ctx.etape("chercheur", "Cherche les annonces du calendrier portant ce nom")
    mots = [m for m in question.lower().split() if len(m) > 2]
    annonces = [a for a in ctx.base.lire("SELECT id, quand, titre, genre FROM annonces ORDER BY quand DESC LIMIT 2000")
                if mots and all(m in a["titre"].lower() for m in mots)][:20]
    ctx.detail({"extraits": len(trouves), "annonces": len(annonces)})
    ctx.etape("professeur", "Rédige la liste des précédents, avec date et source")
    lignes = [f"Thème : « {question} ».", ""]
    if trouves:
        lignes.append("Passages gardés (texte exact, début) :")
        for r in trouves:
            source = r["origine"][4:] if (r["origine"] or "").startswith("fed:") else r["origine"]
            lignes.append(f"   {r['titre']} — source {source}\n      « {' '.join(r['texte'].split())[:300]} »")
    if annonces:
        lignes += ["", "Annonces du calendrier portant ce nom :"]
        lignes += [f"   {_date(a['quand'])} — {a['titre']}" for a in annonces]
    if not trouves and not annonces:
        lignes.append("Aucun précédent dans ce que l'université a gardé : rien n'est cité de mémoire.")
    lignes += ["", "Limite : seulement ce qui a été lu et gardé depuis le lancement des agents 5 et 10."]
    ctx.etape("connaissances", "Classe la recherche et demande le contrôle des citations", "verification")
    doc = ctx.document("precedents", f"Précédents — {question[:60]}", "\n".join(lignes),
                       donnees={"question": question, "extraits": [{"id": r["id"], "debut": r["texte"][:300]} for r in trouves],
                                "annonces": [a["id"] for a in annonces]},
                       sources=[{"extrait": r["id"], "origine": r["origine"]} for r in trouves], role="professeur",
                       statut="a_verifier")
    verif = ctx.demander(9, "verification_citations", f"Contrôler les citations (document {doc})", {"document": doc},
                         "Chaque passage cité doit exister tel quel.", document=doc)
    return {"document": doc, "verification": verif, "extraits": len(trouves), "annonces": len(annonces)}
