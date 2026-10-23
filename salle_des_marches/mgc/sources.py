# -*- coding: utf-8 -*-
"""
Bougies MGC pour l'analyste : NinjaTrader en temps réel d'abord, sinon Yahoo (différé), toujours sur le CONTRAT RÉEL.

  1. le contrat actif est calculé (contrats.py), ex. MGCZ26 ;
  2. NinjaTrader en direct (battement récent, bon contrat) -> source « ninjatrader », temps réel ;
     chaque bougie 1 min est recoupée avec la même bougie Yahoo (écart maximal : 2 points) ;
  3. sinon Yahoo sur ce contrat (« MGCZ26.CMX ») -> source « yahoo », DIFFÉRÉE : au mieux « ATTENDRE » ;
  4. H4 et H12 sont reconstruits à partir du H1, calés sur l'ouverture CME (17h à Chicago) ;
  5. chaque unité de temps passe les contrôles de qualite.py.
"""

import pandas as pd

from . import qualite
from . import source_ninja as ninja
from .contrats import ContractManager

# Yahoo : historiques maximaux par intervalle
YAHOO = {"D1": ("2y", "1d"), "H1": ("180d", "1h"), "M15": ("30d", "15m"), "M5": ("5d", "5m"), "M1": ("5d", "1m")}
PERIODES = {"M1": 1, "M3": 3, "M5": 5, "M15": 15, "H1": 60, "D1": 1440}


def yahoo_brut(ticker, periode, intervalle):
    import yfinance as yf

    return yf.Ticker(ticker).history(period=periode, interval=intervalle, auto_adjust=False)


def depuis_yahoo(brut, quotidien=False):
    """Format Yahoo -> convention commune (index UTC = début de bougie ; date de séance pour le D1)."""
    if brut is None or brut.empty:
        return pd.DataFrame()
    df = brut[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "High", "Low", "Close"])
    df.columns = ["o", "h", "l", "c", "v"]
    # Yahoo stocke ses prix en précision réduite (4181.1 devient 4181.10009765625) : arrondi au centime
    df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].astype(float).round(2)
    if quotidien:
        df.index = pd.DatetimeIndex(pd.to_datetime(df.index.date)).tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def m3_depuis_m1(m1):
    if m1.empty:
        return m1
    return m1.resample("3min", label="left", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()


def charger_yahoo(contrat, chargeur=yahoo_brut):
    ticker = f"{contrat}.CMX"
    bougies = {nom: depuis_yahoo(chargeur(ticker, *args), quotidien=nom == "D1") for nom, args in YAHOO.items()}
    bougies["M3"] = m3_depuis_m1(bougies["M1"])
    return bougies


def recouper(ninja_m1, yahoo_m1, config):
    """Compare la clôture de la dernière bougie 1 min commune aux deux sources."""
    communes = ninja_m1.index.intersection(yahoo_m1.index) if not (ninja_m1.empty or yahoo_m1.empty) else []
    if not len(communes):
        return "Recoupement Yahoo impossible (aucune bougie 1 min commune)."
    t = communes[-1]
    return qualite.ecart_sources(float(ninja_m1.loc[t, "c"]), float(yahoo_m1.loc[t, "c"]), config)


def charger_mgc(instant, config, chargeur_yahoo=yahoo_brut, recoupement=True):
    """Bougies contrôlées, source, contrat réel, statut et motifs. instant : datetime avec fuseau."""
    etat = ContractManager(config).etat(instant)
    contrat, motifs = etat["contrat"], []

    lu = ninja.charger(ninja.dossier_par_defaut(config))
    direct, motif = ninja.en_direct(lu["battement"], instant, config)
    code_ninja = (lu["battement"] or {}).get("code")
    if direct and code_ninja != contrat:
        direct, motif = False, f"NinjaTrader affiche {code_ninja}, mais le contrat actif est {contrat}."
    if direct and lu["bougies"]["M1"].empty:
        direct, motif = False, "NinjaTrader : aucun fichier de bougies 1 min."

    if direct:
        source, bougies = "ninjatrader", dict(lu["bougies"])
        if len(bougies["D1"]) < 210:  # EMA 200 du D1 : complément Yahoo, sans enjeu de minute
            bougies["D1"] = depuis_yahoo(chargeur_yahoo(f"{contrat}.CMX", *YAHOO["D1"]), quotidien=True)
            motifs.append("D1 : historique NinjaTrader trop court, complété par Yahoo (journalier).")
        if recoupement:
            ecart = recouper(bougies["M1"], depuis_yahoo(chargeur_yahoo(f"{contrat}.CMX", *YAHOO["M1"])), config)
            if ecart:
                motifs.append(ecart)
    else:
        source, bougies = "yahoo", charger_yahoo(contrat, chargeur_yahoo)
        if motif:
            motifs.append(motif)

    controles = {}
    for nom, periode in PERIODES.items():
        controles[nom] = qualite.controler(bougies.get(nom), periode, instant, config, temps_reel=direct,
                                           contrat=code_ninja if direct else contrat, contrat_attendu=contrat)
    propres = {nom: c["bougies"] for nom, c in controles.items()}
    propres["H4"] = qualite.regrouper_cme(propres["H1"], 4)
    propres["H12"] = qualite.regrouper_cme(propres["H1"], 12)
    bilan = qualite.ensemble(controles)
    if any("Écart de" in m for m in motifs) and bilan["statut"] == "temps_reel":
        bilan["statut"] = "invalide"  # deux sources en désaccord : on ne choisit pas au hasard
    m1 = propres["M1"]
    return {
        "source": source,
        "contrat": contrat,
        "etat_contrat": etat,
        "temps_reel": bilan["statut"] == "temps_reel",
        "statut": bilan["statut"],
        "motifs": motifs + bilan["motifs"],
        "dernier_prix": (lu["battement"] or {}).get("dernier_prix") if direct else
                        (float(m1["c"].iloc[-1]) if not m1.empty else None),
        "controles": {nom: {k: v for k, v in c.items() if k != "bougies"} for nom, c in controles.items()},
        "bougies": propres,
    }
