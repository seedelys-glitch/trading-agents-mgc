# -*- coding: utf-8 -*-
"""
Backtest de la stratégie V1 de Jabran (STRATEGIE.md, 1H / 12H), sur bougies H1. Aucune IA.

Règles appliquées (fixées AVANT le test, aucun paramètre réglé sur les résultats) :
  - biais : structure (BOS) H12 ET H1 dans le même sens ET EMA 200 H1 dans ce sens ;
  - zone : setup.construire (Fibo 0.618 / 0.705 / 0.786 / 0.893 de la dernière belle impulsion H1, avec FVG) ;
  - confirmation : bougie H1 dont la mèche dépasse la zone et dont la clôture se pose dans la zone ;
  - entrée à l'OUVERTURE de la bougie suivante, si elle est dans la fenêtre de Paris et la séance ouverte ;
  - moteur de risque (risque.py) : contrats, ratio minimal, stop cohérent — sinon trade refusé ;
  - sorties : 25 % au TP1, 50 % au TP2, 25 % au TP3 ; break-even à 35 % du chemin vers le TP1 ;
  - sortie forcée à 15h00 (Chicago), avant la limite de Topstep (15h10, à vérifier) ; rien près du rollover.

Prudence (biais contrôlés) :
  - aucune donnée future : à la bougie i, seules les bougies 0..i sont lues (pivots confirmés 3 bougies plus tard) ;
  - bougie qui touche le stop ET un objectif : le stop est compté en premier ; le break-even ne joue qu'à la
    bougie suivante ; une ouverture au-delà du stop sort au prix d'ouverture ;
  - tous les signaux sont pris (pas de sélection) ; une même impulsion ne sert qu'une fois.
Limites : pas de calendrier d'annonces historique (FOMC, NFP... non filtrés) ; contrat continu Yahoo (sauts de
rollover) ; sorties partielles en fractions de contrat ; frais et glissement estimés.
"""

import pandas as pd

import calculs

from . import calendrier_cme as cal
from . import qualite, risque, setup
from .contrats import ContractManager
from .instrument import VALEUR_POINT, arrondi_tick

PARTS = (0.25, 0.50, 0.25)
FENETRE_FIBO = 500
SORTIE_FORCEE_CHICAGO = 15  # heure de début de la dernière bougie H1 interdite (15h-16h)


def confirmation(bougie, zone, sens):
    """Mèche au-delà de la zone, clôture posée dans la zone."""
    bas, haut = zone
    if sens == "achat":
        return bougie["l"] < bas and bas <= bougie["c"] <= haut
    return bougie["h"] > haut and bas <= bougie["c"] <= haut


class Position:
    def __init__(self, sens, entree, stop, cibles, contrats, couts, ouverture, niveau, be_pct):
        self.sens, self.entree, self.stop, self.cibles = sens, entree, stop, list(cibles)
        self.contrats, self.couts, self.ouverture, self.niveau = contrats, couts, ouverture, niveau
        self.risque_pts, self.stop_initial = abs(entree - stop), stop
        self.seuil_be = entree + be_pct / 100 * (cibles[0] - entree)
        self.restant, self.be, self.sorties = 1.0, False, []
        self.signe = 1 if sens == "achat" else -1

    def _sortir(self, part, prix, quand, motif):
        self.sorties.append({"part": part, "prix": prix, "quand": quand, "motif": motif})
        self.restant = round(self.restant - part, 6)

    def avancer(self, t, b, forcer=False):
        """Traite une bougie ; True quand la position est entièrement fermée."""
        s = self.signe
        if forcer:
            self._sortir(self.restant, b["o"], t, "sortie forcée (fin de séance)")
            return True
        if s * (b["o"] - self.stop) <= 0:  # ouverture déjà au-delà du stop
            self._sortir(self.restant, b["o"], t, "stop (ouverture au-delà)")
            return True
        extreme_contre, extreme_pour = (b["l"], b["h"]) if s == 1 else (b["h"], b["l"])
        if s * (extreme_contre - self.stop) <= 0:  # prudence : le stop passe avant les objectifs
            self._sortir(self.restant, self.stop, t, "break-even" if self.be else "stop")
            return True
        while self.cibles and s * (extreme_pour - self.cibles[0]) >= 0:
            rang = 3 - len(self.cibles)
            self._sortir(min(PARTS[rang], self.restant), self.cibles.pop(0), t, f"TP{rang + 1}")
        if self.restant <= 1e-9:
            return True
        if not self.be and s * (extreme_pour - self.seuil_be) >= 0:
            self.stop, self.be = self.entree, True  # effectif à partir de la bougie suivante
        return False

    def bilan(self):
        pts = sum(x["part"] * self.signe * (x["prix"] - self.entree) for x in self.sorties)
        brut = self.contrats * pts * VALEUR_POINT
        net = brut - self.contrats * self.couts
        unite = self.contrats * self.risque_pts * VALEUR_POINT
        return {
            "sens": self.sens, "niveau": self.niveau, "ouverture": self.ouverture.isoformat(),
            "fermeture": self.sorties[-1]["quand"].isoformat(), "entree": self.entree, "stop_initial": self.stop_initial,
            "contrats": self.contrats, "points": round(pts, 2), "usd_brut": round(brut, 2), "usd_net": round(net, 2),
            "R_brut": round(pts / self.risque_pts, 3), "R_net": round(net / unite, 3),
            "sorties": [x["motif"] for x in self.sorties],
            "issue": "win" if net > 0 else "loss",
        }


def biais(h12_tendance, h1_tendance, ema_montante):
    if h12_tendance == h1_tendance == "haussier" and ema_montante:
        return "achat"
    if h12_tendance == h1_tendance == "baissier" and not ema_montante:
        return "vente"
    return None


def simuler(h1, config, journal=None, trace=None):
    """Rejoue la stratégie bougie par bougie. h1 : index UTC (début de bougie), colonnes o, h, l, c, v.

    trace (liste, facultatif) : la décision de CHAQUE bougie (biais, zone) pour vérifier qu'aucune donnée future
    n'est lue (les tests comparent un historique coupé et l'historique complet).
    """
    h1 = h1.sort_index()
    index, n = h1.index, len(h1)
    ema = calculs.ema(h1["c"], 200)
    a_h1 = calculs.atr(h1)
    h12 = qualite.regrouper_cme(h1, 12)
    fins_h12 = h12.index + pd.Timedelta(hours=12)
    cm = ContractManager(config)
    trades, refus, deja_vues = [], {"risque": 0, "fenetre": 0, "rollover": 0}, set()
    position, tendance12, nb12 = None, "indéfinie", -1
    for i in range(220, n - 1):
        t, b = index[i], h1.iloc[i]
        if position is not None:
            forcer = t.tz_convert(cal.CHICAGO).hour == SORTIE_FORCEE_CHICAGO or cal.etat_seance(
                t.to_pydatetime())["etat"] != "ouverte"
            if position.avancer(t, b, forcer=forcer):
                trades.append(position.bilan())
                position = None
            continue
        # biais : H12 calculé seulement sur les bougies H12 terminées à la clôture de la bougie i
        fin_i = t + pd.Timedelta(hours=1)
        nb = int((fins_h12 <= fin_i).sum())
        if nb != nb12:
            nb12 = nb
            tendance12 = calculs.structure(h12.iloc[:nb])["tendance"] if nb > 30 else "indéfinie"
        fenetre = h1.iloc[max(0, i + 1 - FENETRE_FIBO):i + 1]
        sens = biais(tendance12, calculs.structure(fenetre)["tendance"], bool(ema.iloc[i] > ema.iloc[i - 20]))
        if not sens:
            if trace is not None:
                trace.append((t, None, None))
            continue
        fibo = calculs.fibo({"H1": fenetre}, float(a_h1.iloc[i]))
        conf, _ = setup.construire(fibo, sens, float(b["c"]))
        if trace is not None:
            trace.append((t, sens, (conf["entree"], conf["stop"], conf["tp1"]) if conf else None))
        if not conf:
            continue
        cle = (fibo["depart"]["prix"], fibo["fin"]["prix"])
        zone = (min(conf["fvg"][0], conf["entree"]), max(conf["fvg"][1], conf["entree"]))
        if cle in deja_vues or not confirmation(b, zone, sens):
            continue
        suivante_t, suivante = index[i + 1], h1.iloc[i + 1]
        instant = suivante_t.to_pydatetime()
        if not cal.dans_fenetre(instant, config["fenetre_paris"]) or cal.etat_seance(instant)["etat"] != "ouverte":
            refus["fenetre"] += 1
            continue
        if cm.etat(instant)["restriction_rollover"]:
            refus["rollover"] += 1
            continue
        entree = arrondi_tick(float(suivante["o"]))
        evaluation = risque.evaluer(sens, entree, conf["stop"], conf["tp1"], config)
        if not evaluation["exploitable"]:
            refus["risque"] += 1
            continue
        deja_vues.add(cle)
        position = Position(sens, entree, conf["stop"], (conf["tp1"], conf["tp2"], conf["tp3"]),
                            evaluation["contrats"], evaluation["couts_par_contrat"], suivante_t, conf["niveau"],
                            config["break_even_pct"])
        if journal is not None:
            journal.append((t, sens, conf))
    return {"trades": trades, "refus": refus, "debut": index[0].isoformat(), "fin": index[-1].isoformat(),
            "bougies": n}


def _resume(trades, net):
    from .stats import resumer

    cle = "R_net" if net else "R_brut"
    usd = "usd_net" if net else "usd_brut"
    lignes = [{"issue": "win" if t[cle] > 0 else "loss", "r_multiple": t[cle], "pnl_usd_net": t[usd]} for t in trades]
    return resumer(lignes)


def rapport(resultat, part_dans_echantillon=0.6):
    """Brut et net ; découpage chronologique ; walk-forward par trimestre ; par setup."""
    trades = resultat["trades"]
    debut, fin = pd.Timestamp(resultat["debut"]), pd.Timestamp(resultat["fin"])
    coupure = debut + (fin - debut) * part_dans_echantillon
    dedans = [t for t in trades if pd.Timestamp(t["ouverture"]) < coupure]
    dehors = [t for t in trades if pd.Timestamp(t["ouverture"]) >= coupure]
    trimestres = {}
    for t in trades:
        q = pd.Timestamp(t["ouverture"]).tz_convert(None).to_period("Q")
        trimestres.setdefault(str(q), []).append(t)
    setups = {}
    for t in trades:
        setups.setdefault(f"{t['sens']} {t['niveau']}", []).append(t)
    return {
        "periode": [resultat["debut"], resultat["fin"]], "bougies_H1": resultat["bougies"],
        "coupure": coupure.isoformat(), "refus": resultat["refus"], "nombre_trades": len(trades),
        "tout": {"brut": _resume(trades, False), "net": _resume(trades, True)},
        "premiere_partie": {"brut": _resume(dedans, False), "net": _resume(dedans, True)},
        "hors_echantillon": {"brut": _resume(dehors, False), "net": _resume(dehors, True)},
        "walk_forward_trimestres": {q: _resume(v, True) for q, v in sorted(trimestres.items())},
        "par_setup": {k: _resume(v, True) for k, v in sorted(setups.items())},
        "sorties": pd.Series([s for t in trades for s in t["sorties"]]).value_counts().to_dict() if trades else {},
    }

