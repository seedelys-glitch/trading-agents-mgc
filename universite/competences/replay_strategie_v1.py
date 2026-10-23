# -*- coding: utf-8 -*-
"""
Agent 13 — laboratoire de replay : la stratégie de Jabran (STRATEGIE.md, règles du 23/10, 1H / 12H) rejouée bougie par bougie
sur un jeu de l'université, avec le moteur de backtest de la Salle (mgc/backtest.py : aucune donnée future,
stop compté avant l'objectif, frais et glissement, moteur de risque).

En plus du rapport de la Salle :
  - découpage chronologique FIXÉ AVANT le test : entraînement 60 %, validation 20 %, test 20 % ;
  - Monte-Carlo (rééchantillonnage des trades, graine fixe donc reproductible) : fourchette du total et du drawdown ;
  - régimes au moment de l'entrée, calculés avec les seules bougies passées : pente de l'EMA 200 H1 et
    volatilité (ATR 14 comparé à sa médiane des 500 bougies précédentes).
Aucun paramètre n'est réglé sur les résultats. Moins de 30 trades : aucune conclusion.
Le rapport part ensuite au secrétaire-auditeur, qui recompte tout.
"""

import datetime as dt
import random
import time

from .. import config, donnees

TYPE = "replay_strategie_v1"
AGENT = 13
TITRE = "Replay de la stratégie (règles du 23/10, 1H / 12H)"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "fin du replay en secondes UTC (vide = tout le jeu)",
          "compte": "A (25 % à chaque objectif, par défaut) ou B (50 / 0 / 25 / 25)"}

DECOUPAGE = (("entrainement", 0.6), ("validation", 0.2), ("test", 0.2))
TIRAGES = 2000
GRAINE = 20261023
MIN_H1 = 300


def _date(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%d/%m/%Y")


def monte_carlo(r_valeurs, tirages=TIRAGES, graine=GRAINE):
    """Rééchantillonnage avec remise de la suite des R : percentiles 5/50/95 du total et du drawdown maximal."""
    if not r_valeurs:
        return None
    alea = random.Random(graine)
    totaux, dds = [], []
    for _ in range(tirages):
        tirage = [alea.choice(r_valeurs) for _ in r_valeurs]
        cumul = sommet = pire = 0.0
        for v in tirage:
            cumul += v
            sommet = max(sommet, cumul)
            pire = max(pire, sommet - cumul)
        totaux.append(cumul)
        dds.append(pire)
    totaux.sort()
    dds.sort()

    def p(serie, q):
        return round(serie[min(len(serie) - 1, int(q * len(serie)))], 2)

    return {"tirages": tirages, "graine": graine, "total_R": [p(totaux, .05), p(totaux, .5), p(totaux, .95)],
            "drawdown_R": [p(dds, .05), p(dds, .5), p(dds, .95)],
            "part_negative": round(sum(t < 0 for t in totaux) / tirages, 3)}


def regimes(h1, trades):
    """Régime de chaque trade à la clôture de la bougie de signal (bougies passées seulement)."""
    config.salle_importable()
    import pandas as pd
    from calculs import atr, ema

    e = ema(h1["c"], 200)
    a = atr(h1)
    res = []
    for t in trades:
        ouverture = pd.Timestamp(t["ouverture"])
        i = h1.index.searchsorted(ouverture) - 1          # bougie de signal (la précédente)
        if i < 520:
            res.append({"tendance": "indéfini", "volatilite": "indéfini"})
            continue
        mediane = float(a.iloc[i - 500:i].median())
        res.append({"tendance": "EMA montante" if e.iloc[i] > e.iloc[i - 20] else "EMA descendante",
                    "volatilite": "volatilité haute" if a.iloc[i] > mediane else "volatilité basse"})
    return res


def executer(ctx):
    config.salle_importable()
    import pandas as pd
    from mgc import backtest
    from mgc import config as cfg

    jeu = int(ctx.params["jeu"])
    infos = ctx.base.un("SELECT * FROM jeux WHERE id=?", (jeu,))
    if not infos:
        raise ValueError(f"jeu de bougies {jeu} introuvable")
    instant = float(ctx.params.get("instant") or time.time())

    ctx.etape("documentaliste", f"Rassemble les bougies H1 fermées du jeu « {infos['nom']} »")
    f = donnees.fenetre(ctx.base, jeu, "H1", instant)
    lignes = f["bougies"]
    ctx.detail({"H1": len(lignes), "reconstruite_depuis": f["reconstruite_depuis"]})
    if len(lignes) < MIN_H1:
        raise ValueError(f"{len(lignes)} bougies H1 seulement : il en faut au moins {MIN_H1} pour ce replay")
    h1 = pd.DataFrame([r[1:] for r in lignes], columns=["o", "h", "l", "c", "v"],
                      index=pd.DatetimeIndex([pd.Timestamp(r[0], unit="s", tz="UTC") for r in lignes]))

    ctx.etape("chercheur", f"Rejoue la stratégie sur {len(lignes)} bougies H1, sans regarder la suite")
    try:
        reglages = cfg.charger()
    except (OSError, ValueError):
        reglages = dict(cfg.DEFAUTS)
    if reglages.get("limite_perte_jour_usd") is None:
        reglages["limite_perte_jour_usd"] = 1000.0
    compte = str(ctx.params.get("compte") or "A").strip().upper()
    if compte not in backtest.PARTS_COMPTES:
        raise ValueError("compte inconnu : A ou B")
    res = backtest.simuler(h1, reglages, compte=compte)
    trades = res["trades"]
    ctx.verifier()

    ctx.etape("chercheur", "Découpe entraînement / validation / test, Monte-Carlo et régimes")
    debut, fin = lignes[0][0], lignes[-1][0] + 3600
    bornes, t0 = [], debut
    for nom, part in DECOUPAGE:
        t1 = t0 + (fin - debut) * part
        bornes.append((nom, t0, t1))
        t0 = t1
    parts = {}
    for nom, a, b in bornes:
        dedans = [t for t in trades if a <= pd.Timestamp(t["ouverture"]).timestamp() < b]
        parts[nom] = {"debut": a, "fin": b, "net": backtest._resume(dedans, True)}
    mc = monte_carlo([t["R_net"] for t in trades])
    for t, r in zip(trades, regimes(h1, trades), strict=True):
        t["regime"] = r
    par_regime = {}
    for t in trades:
        for cle in ("tendance", "volatilite"):
            par_regime.setdefault(t["regime"][cle], []).append(t)
    par_regime = {k: backtest._resume(v, True) for k, v in sorted(par_regime.items())}
    tout = backtest._resume(trades, True)

    ctx.etape("professeur", "Rédige le rapport, avec ses limites")
    def ligne(nom, s):
        if not s["nombre"]:
            return f"{nom} : aucun trade."
        return (f"{nom} : {s['nombre']} trade(s), réussite {s['taux_reussite']:.0%} (Wilson 95 % "
                f"{s['wilson_95'][0]:.0%}–{s['wilson_95'][1]:.0%}), espérance {s['esperance_R']} R, "
                f"drawdown max {s['drawdown_max_R']} R, total {s['total_usd']} $.")

    texte = [f"Données : {infos['source']} — {infos['nom']} ({'temps réel' if infos['temps_reel'] else 'différé / historique'}),"
             f" {len(lignes)} bougies H1 du {_date(debut)} au {_date(lignes[-1][0])}"
             + (f" (reconstruites depuis {f['reconstruite_depuis']})." if f["reconstruite_depuis"] else "."),
             f"Règles du 23/10 (STRATEGIE.md), fixées avant le test : objectifs 0 / -0.272 / -1.272 / -2.618, compte {compte} "
             f"({' / '.join(f'{x:.0%}' for x in backtest.PARTS_COMPTES[compte])}), stop au point d'entrée puis au 0.5 puis "
             f"au 0, risque {reglages['risque_pct']} % ; frais et glissement inclus (résultats nets).",
             "Entrée simulée sur la confirmation H1 : la cascade 48 min / 12 min n'est pas rejouée (pas assez de bougies fines).",
             f"Signaux refusés : {res['refus']['risque']} par le risque, {res['refus']['fenetre']} hors fenêtre, "
             f"{res['refus']['rollover']} près du rollover.", "",
             ligne("Ensemble", tout)]
    texte += [ligne(f"{nom.capitalize()} ({_date(p['debut'])} → {_date(p['fin'])})", p["net"]) for nom, p in parts.items()]
    if mc:
        texte += ["", f"Monte-Carlo ({mc['tirages']} tirages, graine {mc['graine']}) : total entre {mc['total_R'][0]} R et "
                      f"{mc['total_R'][2]} R (5 %–95 %), médiane {mc['total_R'][1]} R ; drawdown médian {mc['drawdown_R'][1]} R, "
                      f"pire 5 % au-delà de {mc['drawdown_R'][2]} R ; {mc['part_negative']:.0%} des tirages finissent en perte."]
    texte += ["", "Par régime au moment de l'entrée :"] + [ligne(k, v) for k, v in par_regime.items()]
    texte += ["", f"Conclusion statistique : {tout.get('conclusion', '')}",
              "Limites : annonces économiques non filtrées (pas de calendrier historique), sorties partielles en "
              "fractions de contrat, frais et glissement estimés. Ce rejeu n'est pas une promesse de résultat."]
    if tout["nombre"] < 30:
        texte.append("Monte-Carlo et régimes sont seulement indicatifs : trop peu de trades.")

    ctx.etape("connaissances", "Classe le rapport et demande sa vérification", "verification")
    donnees_doc = {"jeu": jeu, "instant": instant, "compte": compte, "h1": len(lignes), "debut": debut, "fin": fin,
                   "trades": trades, "refus": res["refus"], "tout": tout, "parts": parts, "monte_carlo": mc,
                   "par_regime": par_regime}
    doc = ctx.document("replay", f"Replay stratégie (compte {compte}) — {infos['nom']}", "\n".join(texte), donnees=donnees_doc,
                       sources=[{"jeu": jeu, "unite": "H1", "n": len(lignes), "debut": lignes[0][0],
                                 "fin": lignes[-1][0], "reconstruite_depuis": f["reconstruite_depuis"]}],
                       role="professeur", statut="a_verifier")
    verif = ctx.demander(9, "verification_replay", f"Vérifier le replay (document {doc})", {"document": doc},
                         "Recompter les trades et les statistiques.", document=doc)
    return {"document": doc, "verification": verif, "trades": len(trades), "esperance_R": tout.get("esperance_R")}
