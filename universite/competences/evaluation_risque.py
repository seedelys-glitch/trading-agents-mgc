# -*- coding: utf-8 -*-
"""
Agent 8 — évalue une idée de trade avec le moteur de risque de la Salle (mgc/risque.py) : nombre de contrats MGC,
risque net (frais et glissement inclus), ratio au TP1, vetos. Calcul seulement : rien n'est envoyé à personne.
"""

TYPE = "evaluation_risque"
AGENT = 8
TITRE = "Évaluer le risque d'une idée de trade"
PARAMS = {"sens": "achat ou vente", "entree": "prix d'entrée", "stop": "prix du stop", "tp1": "premier objectif",
          "perte_du_jour": "perte déjà subie aujourd'hui en $ (0 par défaut)"}
CLES_REGLAGES = ("capital_usd", "risque_pct", "limite_perte_jour_usd", "frais_aller_retour_usd",
                 "glissement_ticks_par_cote", "ratio_min", "max_contrats", "break_even_pct")


def executer(ctx):
    from .. import config
    config.salle_importable()
    from mgc import config as cfg
    from mgc import risque

    p = ctx.params
    ctx.etape("documentaliste", "Relit les réglages de risque (capital, % par trade, limite du jour)")
    try:
        reglages = cfg.charger()
    except (OSError, ValueError):
        reglages = dict(cfg.DEFAUTS)
    if reglages.get("limite_perte_jour_usd") is None:
        reglages["limite_perte_jour_usd"] = 1000.0
    ctx.etape("chercheur", "Calcule contrats, risque net et ratio")
    try:
        entree, stop, tp1 = float(p["entree"]), float(p["stop"]), float(p["tp1"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("il faut une entrée, un stop et un TP1 chiffrés") from e
    r = risque.evaluer(p.get("sens", ""), entree, stop, tp1, reglages, float(p.get("perte_du_jour") or 0))
    ctx.detail({"exploitable": r["exploitable"], "contrats": r.get("contrats"), "vetos": len(r.get("vetos", []))})
    ctx.etape("professeur", "Rédige l'avis du gestionnaire des risques")
    lignes = [f"Idée : {p.get('sens')} à {entree}, stop {stop}, TP1 {tp1} (MGC : 1 point = 10 $ par contrat).",
              f"Réglages : capital {reglages['capital_usd']} $, risque {reglages['risque_pct']} % par trade, "
              f"limite du jour {reglages['limite_perte_jour_usd']} $, au plus {reglages['max_contrats']} contrat(s)."]
    if "risque_net_par_contrat" in r:
        lignes += [f"Distance au stop : {r['distance_points']} points ({r['distance_ticks']} ticks).",
                   f"Risque par contrat : {r['risque_brut_par_contrat']} $ + {r['couts_par_contrat']} $ de frais et "
                   f"glissement (estimés) = {r['risque_net_par_contrat']} $.",
                   f"Budget : {r['risque_autorise']} $ par trade, reste {r['reste_limite_jour']} $ avant la limite du jour.",
                   f"Contrats : {r['contrats']}" + (" (plafonné)" if r["plafonne"] else "")
                   + f" ; risque total {r['risque_total_net']} $ ; ratio net au TP1 {r['ratio_net_tp1']} ; "
                   f"break-even à {r['break_even']}."]
    lignes += [f"VETO : {v}" for v in r.get("vetos", [])]
    lignes.append("Avis : " + ("exploitable selon les règles." if r["exploitable"] else "REFUSÉ par les règles de risque."))
    lignes.append("Calcul seulement : aucun ordre n'est envoyé, ni maintenant ni plus tard.")
    ctx.etape("connaissances", "Classe l'avis", "verification")
    doc = ctx.document("risque", f"Risque : {p.get('sens')} {entree} / stop {stop}", "\n".join(lignes),
                       donnees={"parametres": p, "reglages": {k: reglages[k] for k in CLES_REGLAGES},
                                "perte_du_jour": float(p.get("perte_du_jour") or 0), "evaluation": r},
                       role="professeur", statut="a_verifier")
    verif = ctx.demander(9, "verification_risque", f"Recompter le risque (document {doc})", {"document": doc},
                         "Refaire le calcul du risque sans le moteur de la Salle.", document=doc)
    if not r["exploitable"]:
        ctx.message(14, "alerte", f"Veto du gestionnaire des risques : {'; '.join(r.get('vetos', []))[:300]}", doc)
    return {"document": doc, "verification": verif, "exploitable": r["exploitable"], "contrats": r.get("contrats"), "vetos": r.get("vetos", [])}
