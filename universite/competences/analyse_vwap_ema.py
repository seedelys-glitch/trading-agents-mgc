# -*- coding: utf-8 -*-
"""
Agent 6 — VWAP de séance et EMA 200, à un instant donné (en direct ou en replay), sans look-ahead.

Calculs : calculs.ema de la Salle (la même EMA que le desk) ; VWAP de séance CME (depuis 17 h à Chicago,
prix typique (H+B+C)/3 pondéré par le volume) avec bandes à 1 et 2 écarts-types.
Le document part ensuite au secrétaire-auditeur (agent 9), qui recalcule tout de son côté.
"""

import datetime as dt
import time
from zoneinfo import ZoneInfo

from .. import config, donnees

TYPE = "analyse_vwap_ema"
AGENT = 6
TITRE = "Analyse VWAP & EMA 200"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "secondes UTC (vide = maintenant)",
          "unites": "unités de temps de l'EMA (par défaut M5, M15, H1)"}

PERIODE_EMA = 200
HISTORIQUE = 600       # bougies lues par unité : 200 pour l'EMA + de quoi la stabiliser
PENTE = 20             # la pente compare l'EMA à celle d'il y a 20 bougies


def heure(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %Hh%M")


def calculer_ema(lignes):
    config.salle_importable()
    import pandas as pd
    from calculs import ema

    serie = pd.Series([r[4] for r in lignes], dtype=float)
    e = ema(serie, PERIODE_EMA)
    return float(e.iloc[-1]), float(e.iloc[-1 - PENTE])


def calculer_vwap(lignes):
    """lignes de la séance -> (vwap, écart-type) ou None si pas de volume."""
    volume = sum(r[5] for r in lignes)
    if len(lignes) < 3 or volume <= 0:
        return None
    pv = sum((r[2] + r[3] + r[4]) / 3 * r[5] for r in lignes)
    v = pv / volume
    variance = sum((((r[2] + r[3] + r[4]) / 3) - v) ** 2 * r[5] for r in lignes) / volume
    return v, variance ** 0.5


def executer(ctx):
    p = ctx.params
    jeu = int(p["jeu"])
    instant = float(p.get("instant") or time.time())
    unites = p.get("unites") or ["M5", "M15", "H1"]
    infos = ctx.base.un("SELECT * FROM jeux WHERE id=?", (jeu,))
    if not infos:
        raise ValueError(f"jeu de bougies {jeu} introuvable")

    # 1. Documentaliste : les bougies fermées à l'instant t, rien d'autre
    ctx.etape("documentaliste", f"Rassemble les bougies fermées au {heure(instant)} (jeu « {infos['nom']} »)")
    fenetres, sources = {}, []
    for u in unites:
        f = donnees.fenetre(ctx.base, jeu, u, instant, HISTORIQUE)
        fenetres[u] = f
        if f["bougies"]:
            sources.append({"jeu": jeu, "unite": u, "n": len(f["bougies"]), "debut": f["bougies"][0][0],
                            "fin": f["bougies"][-1][0], "reconstruite_depuis": f["reconstruite_depuis"]})
    debut_seance = donnees.debut_seance(instant)
    petite = next((u for u in ("M1", "M5", "M15") if donnees.fenetre(ctx.base, jeu, u, instant, 1)["bougies"]), None)
    seance = []
    if petite:
        seance = [r for r in donnees.fenetre(ctx.base, jeu, petite, instant, 2000)["bougies"] if r[0] >= debut_seance]
    ctx.detail({"unites": {u: len(f["bougies"]) for u, f in fenetres.items()}, "seance": len(seance),
                "unite_seance": petite})
    if not any(f["bougies"] for f in fenetres.values()) and not seance:
        raise ValueError("aucune bougie fermée à cet instant dans ce jeu")

    # 2. Chercheur : les calculs
    ctx.etape("chercheur", "Calcule l'EMA 200 sur chaque unité et le VWAP de la séance")
    prix_source = seance or next((f["bougies"] for f in fenetres.values() if f["bougies"]), [])
    prix = prix_source[-1][4]
    ema_res = {}
    for u, f in fenetres.items():
        n = len(f["bougies"])
        if n < PERIODE_EMA + PENTE + 1:
            ema_res[u] = {"disponible": False, "raison": f"{n} bougies fermées, il en faut {PERIODE_EMA + PENTE + 1}"}
            continue
        valeur, avant = calculer_ema(f["bougies"])
        ema_res[u] = {"disponible": True, "valeur": round(valeur, 2), "pente": "montante" if valeur > avant else "descendante",
                      "prix": "au-dessus" if prix > valeur else "en dessous",
                      "ecart_points": round(prix - valeur, 2), "ecart_usd_1_contrat": round((prix - valeur) * 10, 2),
                      "bougies": n, "premiere": f["bougies"][0][0], "derniere": f["bougies"][-1][0]}
    vw = calculer_vwap(seance)
    if vw:
        v, e = vw
        vwap_res = {"disponible": True, "valeur": round(v, 2), "bande_haute_1": round(v + e, 2),
                    "bande_basse_1": round(v - e, 2), "bande_haute_2": round(v + 2 * e, 2),
                    "bande_basse_2": round(v - 2 * e, 2), "prix": "au-dessus" if prix > v else "en dessous",
                    "ecart_points": round(prix - v, 2), "bougies": len(seance), "unite": petite,
                    "debut_seance": debut_seance}
    else:
        vwap_res = {"disponible": False,
                    "raison": "pas de volume dans la séance" if seance else "aucune bougie depuis l'ouverture de la séance"}
    ctx.detail({"ema": {u: r.get("valeur") for u, r in ema_res.items()}, "vwap": vwap_res.get("valeur")})

    # 3. Professeur : le compte rendu, en clair
    ctx.etape("professeur", "Rédige le compte rendu et ses limites")
    nature = "temps réel" if infos["temps_reel"] else "différées ou historiques"
    lignes = [f"Instant analysé : {heure(instant)} (heure de Paris). Dernier prix de clôture : {prix:.2f}.",
              f"Données : {infos['source']} — {infos['nom']} ({nature}).", ""]
    for u, r in ema_res.items():
        if r["disponible"]:
            lignes.append(f"EMA 200 {u} : {r['valeur']:.2f}, pente {r['pente']} ; prix {r['prix']} "
                          f"({r['ecart_points']:+.2f} points, soit {r['ecart_usd_1_contrat']:+.2f} $ pour 1 contrat MGC).")
        else:
            lignes.append(f"EMA 200 {u} : non calculée ({r['raison']}).")
    if vwap_res["disponible"]:
        lignes.append(f"VWAP de séance (depuis {heure(debut_seance)}, {vwap_res['bougies']} bougies {petite}) : "
                      f"{vwap_res['valeur']:.2f} ; bandes 1 écart-type {vwap_res['bande_basse_1']:.2f} – "
                      f"{vwap_res['bande_haute_1']:.2f} ; prix {vwap_res['prix']} ({vwap_res['ecart_points']:+.2f} points).")
    else:
        lignes.append(f"VWAP de séance : non calculé ({vwap_res['raison']}).")
    lignes += ["", "Limites : ces chiffres décrivent une situation, ce n'est pas un signal. "
                   "Aucune bougie postérieure à l'instant n'a été lue."]
    if not infos["temps_reel"]:
        lignes.append("Les données ne sont pas en temps réel : à ne pas utiliser pour décider en direct.")
    texte = "\n".join(lignes)
    commentaire = ctx.ia.commenter(texte, mission=ctx.id, agent=ctx.agent) if ctx.ia else None
    if commentaire:
        texte += "\n\nCommentaire du professeur (IA locale, sans chiffres, à lire avec prudence) :\n" + commentaire

    # 4. Gestionnaire des connaissances : classement et demande de vérification
    ctx.etape("connaissances", "Classe le document et demande sa vérification au secrétaire-auditeur", "verification")
    resultat = {"jeu": jeu, "instant": instant, "prix": prix, "ema": ema_res, "vwap": vwap_res,
                "commentaire_ia": bool(commentaire)}
    doc = ctx.document("analyse", f"VWAP & EMA 200 — {heure(instant)}", texte, donnees=resultat, sources=sources,
                       role="professeur", statut="a_verifier")
    verif = ctx.demander(9, "verification_analyse", f"Vérifier le document {doc} (VWAP & EMA 200)",
                         {"document": doc}, "Recalcul indépendant de tous les chiffres.", document=doc)
    return {"document": doc, "verification": verif, "prix": prix,
            "ema": {u: r.get("valeur") for u, r in ema_res.items()}, "vwap": vwap_res.get("valeur")}
