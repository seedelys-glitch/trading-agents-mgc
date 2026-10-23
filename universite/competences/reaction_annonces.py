# -*- coding: utf-8 -*-
"""
Agent 12 — comment le gold a RÉELLEMENT réagi aux annonces gardées par l'agent 5, mesuré sur les bougies d'un jeu.

Mesure fixée AVANT de regarder les résultats (et jamais changée ensuite) :
  - prix de référence = clôture de la dernière bougie fermée au moment de l'annonce (au plus 5 min avant) ;
  - mouvement à +5, +15 et +60 min = clôture de la dernière bougie fermée à ce moment, moins la référence ;
  - excursions = plus haut et plus bas des bougies fermées dans l'heure qui suit, par rapport à la référence.
Seules les annonces dont l'heure suivante est entièrement passée à l'instant choisi sont mesurées (pas de
look-ahead). Moins de 20 cas pour un type d'annonce : « échantillon insuffisant », aucune conclusion.
"""

import statistics
import time

from .. import donnees
from . import calendrier_macro

TYPE = "reaction_annonces"
AGENT = 12
TITRE = "Réaction du gold aux annonces (mesure sur les bougies)"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "secondes UTC (vide = maintenant)"}
HORIZONS_MIN = (5, 15, 60)
ECART_MAX_S = 300
MIN_CAS = 20


def unite_fine(base, jeu):
    stock = donnees.disponibles(base, jeu)
    for u in ("M1", "M3", "M5"):
        if u in stock:
            return u
    return None


def mesurer(bougies, periode, quand):
    """bougies : [(ts, o, h, l, c, v)] triées, fermées à l'instant. None si les données ne couvrent pas l'annonce."""
    def derniere_fermee(t):
        res = None
        for b in bougies:
            if b[0] + periode <= t:
                res = b
            else:
                break
        return res

    ref = derniere_fermee(quand)
    if ref is None or quand - (ref[0] + periode) > ECART_MAX_S:
        return None
    m = {"reference": ref[4], "reference_ts": ref[0]}
    for h in HORIZONS_MIN:
        b = derniere_fermee(quand + 60 * h)
        if b is None or b[0] < quand or quand + 60 * h - (b[0] + periode) > ECART_MAX_S:
            return None
        m[f"mouvement_{h}"] = round(b[4] - ref[4], 2)
    heure = [b for b in bougies if b[0] >= quand and b[0] + periode <= quand + 3600]
    m["hausse_max_60"] = round(max(b[2] for b in heure) - ref[4], 2)
    m["baisse_max_60"] = round(ref[4] - min(b[3] for b in heure), 2)
    return m


def executer(ctx):
    jeu = int(ctx.params["jeu"])
    instant = float(ctx.params.get("instant") or time.time())
    infos = ctx.base.un("SELECT * FROM jeux WHERE id=?", (jeu,))
    if not infos:
        raise ValueError(f"jeu de bougies {jeu} introuvable")
    u = unite_fine(ctx.base, jeu)
    if u is None:
        raise ValueError("ce jeu n'a pas de bougies de 1, 3 ou 5 minutes : la réaction ne se mesure pas en H1")
    periode = donnees.PERIODES[u]
    ctx.etape("documentaliste", "Liste les annonces fortes de l'historique dont l'heure suivante est passée")
    annonces = ctx.base.lire("SELECT * FROM annonces WHERE genre<>'autre' AND quand + 3600 <= ? ORDER BY quand", (instant,))
    ctx.etape("chercheur", f"Mesure chaque réaction sur les bougies {u} fermées")
    bougies = donnees.fenetre(ctx.base, jeu, u, instant)["bougies"]
    cas, hors = [], 0
    for a in annonces:
        if not bougies or not bougies[0][0] <= a["quand"] <= bougies[-1][0]:
            hors += 1
            continue
        autour = [b for b in bougies if a["quand"] - 3600 <= b[0] <= a["quand"] + 3600]
        m = mesurer(autour, periode, a["quand"])
        if m is None:
            hors += 1
            continue
        cas.append({"annonce": a["id"], "titre": a["titre"], "quand": a["quand"], **m})
    ctx.detail({"annonces": len(annonces), "mesurees": len(cas), "non_couvertes": hors})
    par_titre = {}
    for c in cas:
        par_titre.setdefault(c["titre"], []).append(c)
    resume = {}
    for titre, liste in sorted(par_titre.items()):
        m60 = [c["mouvement_60"] for c in liste]
        resume[titre] = {"cas": len(liste), "mediane_abs_60": round(statistics.median(abs(x) for x in m60), 2),
                         "part_hausse_60": round(sum(x > 0 for x in m60) / len(m60), 3),
                         "suffisant": len(liste) >= MIN_CAS}
    ctx.etape("professeur", "Rédige le compte rendu, cas par cas")
    lignes = [f"Jeu : {infos['nom']} ({infos['source']}), bougies {u}. Instant : {calendrier_macro.heure(instant)}.",
              f"{len(annonces)} annonce(s) forte(s) dans l'historique ; {len(cas)} mesurée(s) ; {hors} non couverte(s) "
              "par les bougies de ce jeu.", ""]
    for c in cas[-15:]:
        lignes.append(f"   {calendrier_macro.heure(c['quand'])} {c['titre']} : référence {c['reference']} ; "
                      + ", ".join(f"+{h} min {c[f'mouvement_{h}']:+}" for h in HORIZONS_MIN)
                      + f" ; dans l'heure +{c['hausse_max_60']} / -{c['baisse_max_60']}")
    if resume:
        lignes += ["", "Par type d'annonce (mouvement à +60 min) :"]
        lignes += [f"   {t} : {r['cas']} cas, médiane {r['mediane_abs_60']} points, en hausse {r['part_hausse_60']:.0%}"
                   + ("" if r["suffisant"] else f" — échantillon insuffisant (moins de {MIN_CAS} cas), aucune conclusion")
                   for t, r in resume.items()]
    lignes += ["", "Mesure fixée à l'avance (référence, +5 / +15 / +60 min, excursions sur 1 h), bougies fermées seulement.",
               "L'historique des annonces commence le jour où l'agent 5 a été lancé : il grossit chaque semaine."]
    ctx.etape("connaissances", "Classe les mesures et demande leur recompte", "verification")
    doc = ctx.document("reaction", f"Réactions aux annonces — {infos['nom']}", "\n".join(lignes),
                       donnees={"jeu": jeu, "instant": instant, "unite": u, "cas": cas, "resume": resume},
                       sources=[{"jeu": jeu, "unite": u, "n": len(bougies)}], role="professeur", statut="a_verifier")
    verif = ctx.demander(9, "verification_reactions", f"Recompter les réactions (document {doc})", {"document": doc},
                         "Refaire chaque mesure directement depuis les bougies.", document=doc)
    return {"document": doc, "verification": verif, "mesurees": len(cas)}
