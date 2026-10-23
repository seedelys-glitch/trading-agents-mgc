# -*- coding: utf-8 -*-
"""
Agent 9 — recompte les réactions aux annonces de l'agent 12 : chaque mesure est refaite par une requête directe
sur la table des bougies (sans la fenêtre de replay ni le code de l'agent 12), avec la même définition écrite.
"""

TYPE = "verification_reactions"
AGENT = 9
TITRE = "Recompter les réactions aux annonces"
PARAMS = {"document": "numéro du document à recompter"}
INTERNE = True
PERIODES = {"M1": 60, "M3": 180, "M5": 300}


def _cloture_avant(cx, jeu, u, p, t, instant):
    return cx.execute("SELECT ts, c FROM bougies WHERE jeu=? AND unite=? AND ts + ? <= ? AND ts + ? <= ?"
                      " ORDER BY ts DESC LIMIT 1", (jeu, u, p, t, p, instant)).fetchone()


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc or "cas" not in doc["donnees"]:
        raise ValueError(f"document de réactions {ident} introuvable")
    d = doc["donnees"]
    jeu, u, instant = d["jeu"], d["unite"], d["instant"]
    p = PERIODES[u]
    cx = ctx.base.cx()
    ctx.etape("documentaliste", f"Relit les {len(d['cas'])} mesure(s) du document {ident}")
    ctx.etape("chercheur", "Refait chaque mesure par requête directe sur les bougies")
    ecarts = []
    for c in d["cas"]:
        a = ctx.base.un("SELECT quand FROM annonces WHERE id=?", (c["annonce"],))
        if not a or a["quand"] != c["quand"]:
            ecarts.append(f"annonce {c['annonce']} absente ou déplacée")
            continue
        q = a["quand"]
        if q + 3600 > instant:
            ecarts.append(f"annonce {c['annonce']} : l'heure suivante n'était pas passée (look-ahead)")
        ref = _cloture_avant(cx, jeu, u, p, q, instant)
        if not ref or abs(ref[1] - c["reference"]) > 1e-6:
            ecarts.append(f"annonce {c['annonce']} : référence différente")
            continue
        for h in (5, 15, 60):
            b = _cloture_avant(cx, jeu, u, p, q + 60 * h, instant)
            if not b or abs(round(b[1] - ref[1], 2) - c[f"mouvement_{h}"]) > 1e-6:
                ecarts.append(f"annonce {c['annonce']} : mouvement à +{h} min différent")
        hl = cx.execute("SELECT MAX(h), MIN(l) FROM bougies WHERE jeu=? AND unite=? AND ts >= ? AND ts + ? <= ?",
                        (jeu, u, q, p, min(q + 3600, instant))).fetchone()
        if abs(round(hl[0] - ref[1], 2) - c["hausse_max_60"]) > 1e-6 or abs(round(ref[1] - hl[1], 2) - c["baisse_max_60"]) > 1e-6:
            ecarts.append(f"annonce {c['annonce']} : excursions différentes")
    for t, r in d["resume"].items():
        n = sum(c["titre"] == t for c in d["cas"])
        if n != r["cas"] or r["suffisant"] != (n >= 20):
            ecarts.append(f"{t} : nombre de cas ou conclusion incohérents")
    verdict = "verifie" if not ecarts else "rejete"
    ctx.etape("professeur", "Rédige le procès-verbal")
    lignes = [f"Document contrôlé : n° {ident}.", f"{len(d['cas'])} mesure(s) refaites par requête directe."]
    lignes += [f"Écart : {e}" for e in ecarts[:30]] or ["Toutes les mesures concordent."]
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]
    ctx.etape("connaissances", "Enregistre le verdict", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Recompte des réactions {ident}", "\n".join(lignes),
                      donnees={"document": ident, "ecarts": ecarts, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Réactions {ident} : {'vérifiées' if verdict == 'verifie' else 'REJETÉES'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Mesure des réactions {ident} rejetée au recompte.", pv)
    return {"document": ident, "verdict": verdict, "ecarts": ecarts}
