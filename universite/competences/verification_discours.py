# -*- coding: utf-8 -*-
"""
Agent 9 — recompte une fiche de discours de l'agent 10 à partir du texte gardé dans la bibliothèque : chaque
expression du lexique est recomptée autrement (recherche mot à mot) et chaque citation doit se retrouver telle quelle.
"""

TYPE = "verification_discours"
AGENT = 9
TITRE = "Recompter une fiche de discours"
PARAMS = {"document": "numéro du document à recompter"}
INTERNE = True


def _occurrences(mots, expression):
    cible = expression.split()
    return sum(mots[i:i + len(cible)] == cible for i in range(len(mots) - len(cible) + 1))


def _mots(texte):
    import re
    return re.findall(r"[a-z]+", texte.lower())


def executer(ctx):
    from . import discours_fed

    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc or "comptes" not in doc["donnees"]:
        raise ValueError(f"fiche de discours {ident} introuvable")
    d = doc["donnees"]
    ctx.etape("documentaliste", "Retrouve le texte gardé dans la bibliothèque")
    morceaux = ctx.base.lire("SELECT texte FROM extraits WHERE origine=? ORDER BY position", ("fed:" + d["lien"],))
    texte = "\n\n".join(m["texte"] for m in morceaux)
    problemes = [] if texte else ["texte du discours absent de la bibliothèque"]
    ctx.etape("chercheur", "Recompte mot à mot et retrouve les citations")
    mots = _mots(texte)
    totaux = {}
    for cote, lexique in (("faucon", discours_fed.FAUCON), ("colombe", discours_fed.COLOMBE)):
        totaux[cote] = 0
        for e in lexique:
            n = _occurrences(mots, e)
            totaux[cote] += n
            if n != d["comptes"][cote].get(e, 0):
                problemes.append(f"« {e} » : {d['comptes'][cote].get(e, 0)} dans la fiche, {n} recompté(s)")
    if (d["faucon"], d["colombe"]) != (totaux["faucon"], totaux["colombe"]):
        problemes.append("totaux différents")
    plat = " ".join(texte.split())
    for c in d["comptes"]["citations"]:
        if " ".join(c.split()) not in plat:
            problemes.append(f"citation introuvable dans le texte : « {c[:80]} »")
    if d["penchant"] != discours_fed.penchant(totaux["faucon"], totaux["colombe"]):
        problemes.append("penchant incohérent avec les totaux")
    verdict = "verifie" if not problemes else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Fiche contrôlée : n° {ident}.", "Expressions recomptées mot à mot ; citations recherchées dans le texte gardé."]
    lignes += [f"Problème : {p}" for p in problemes[:20]] or ["Comptes et citations concordent."]
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Recompte du discours {ident}", "\n".join(lignes),
                      donnees={"document": ident, "problemes": problemes, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Discours {ident} : {'vérifié' if verdict == 'verifie' else 'REJETÉ'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Fiche de discours {ident} rejetée au recompte.", pv)
    return {"document": ident, "verdict": verdict, "problemes": problemes}
