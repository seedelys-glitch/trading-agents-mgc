# -*- coding: utf-8 -*-
"""
Contrôles de qualité des bougies, AVANT toute analyse : la fiabilité des données prime sur l'avis des agents.

Convention commune à toutes les sources : index = DÉBUT de la bougie, en UTC avec fuseau ; colonnes o, h, l, c, v.
Pour le D1, l'index est la date de séance (minuit UTC).

Statuts, du pire au meilleur :
  « invalide »   données inutilisables (vides, sans fuseau, prix impossibles, contrat différent, gros trou)
  « perimee »    marché ouvert mais dernière bougie trop vieille
  « differee »   source différée (Yahoo) : analyse informative, au mieux « ATTENDRE »
  « temps_reel » source temps réel et tous les contrôles passés
"""

import datetime as dt

import numpy as np
import pandas as pd

from . import calendrier_cme as cal
from .instrument import TICK

ORDRE = ["invalide", "perimee", "differee", "temps_reel"]


def _pire(statuts):
    return min(statuts, key=ORDRE.index) if statuts else "invalide"


def trous_en_seance(index, periode_min, limite_etapes=5000):
    """Bougies manquantes pendant que la séance était ouverte : (nombre, plus long trou en minutes)."""
    pas = pd.Timedelta(minutes=periode_min)
    manquantes, plus_long = 0, 0
    for avant, apres in zip(index[:-1], index[1:], strict=True):
        if apres - avant <= pas:
            continue
        t, n, etapes = avant + pas, 0, 0
        while t < apres and etapes < limite_etapes:
            if cal.etat_seance(t.to_pydatetime())["etat"] == "ouverte":
                n += 1
            t += pas
            etapes += 1
        manquantes += n
        plus_long = max(plus_long, n * periode_min)
    return manquantes, plus_long


def controler(df, periode_min, instant, config, temps_reel, contrat=None, contrat_attendu=None):
    """Contrôle une série de bougies. periode_min = 1440 pour le D1. Renvoie le statut, les motifs et les bougies propres."""
    motifs, statuts = [], []
    if df is None or df.empty:
        return {"statut": "invalide", "motifs": ["Aucune bougie reçue."], "bougies": pd.DataFrame(), "nb": 0}
    if getattr(df.index, "tz", None) is None:
        return {"statut": "invalide", "motifs": ["Horodatage sans fuseau horaire : impossible de dater les bougies."],
                "bougies": pd.DataFrame(), "nb": len(df)}
    if contrat_attendu and contrat and contrat != contrat_attendu:
        motifs.append(f"Contrat de la source ({contrat}) différent du contrat actif ({contrat_attendu}).")
        statuts.append("invalide")

    df = df.sort_index()
    doublons = int(df.index.duplicated(keep="last").sum())
    if doublons:
        df = df[~df.index.duplicated(keep="last")]
        motifs.append(f"{doublons} bougie(s) en double retirée(s).")

    # bougie en cours (pas encore fermée) : retirée, l'analyse ne lit que des bougies fermées
    intraday = periode_min < 1440
    if intraday and df.index[-1] + pd.Timedelta(minutes=periode_min) > instant:
        df = df.iloc[:-1]
    if df.empty:
        return {"statut": "invalide", "motifs": motifs + ["Aucune bougie fermée."], "bougies": df, "nb": 0}

    recent = df.iloc[-config["bougies_controlees"]:]
    valeurs = recent[["o", "h", "l", "c"]].to_numpy(dtype=float)
    impossibles = int(((valeurs <= 0).any(axis=1) | (recent["h"] < recent[["o", "c"]].max(axis=1))
                       | (recent["l"] > recent[["o", "c"]].min(axis=1))).sum())
    # tolérance de 0,001 $ : absorbe les erreurs d'arrondi des nombres à virgule, pas un vrai prix hors échelon
    hors_grille = int((np.abs(valeurs / TICK - np.round(valeurs / TICK)) > 1e-2).any(axis=1).sum())
    if impossibles:
        motifs.append(f"{impossibles} bougie(s) aux prix impossibles (haut sous le corps, bas au-dessus, prix nul).")
        statuts.append("invalide")
    if hors_grille:
        motifs.append(f"{hors_grille} bougie(s) avec des prix hors de l'échelon de 0,10 : ce n'est pas un prix MGC brut.")
        statuts.append("invalide")

    fin = df.index[-1] + pd.Timedelta(minutes=periode_min if intraday else 0)
    age_min = round((instant - fin.to_pydatetime()).total_seconds() / 60, 1)
    if intraday:
        manquantes, plus_long = trous_en_seance(recent.index, periode_min)
        if manquantes:
            motifs.append(f"{manquantes} bougie(s) manquante(s) en séance ouverte (plus long trou : {plus_long} min).")
        if plus_long > config["trou_max_min"]:
            statuts.append("invalide")
        if cal.etat_seance(instant)["etat"] == "ouverte" and age_min > periode_min + config["fraicheur_marge_min"]:
            motifs.append(f"Données périmées : dernière bougie fermée il y a {age_min:g} min.")
            statuts.append("perimee")
    statuts.append("temps_reel" if temps_reel else "differee")
    return {
        "statut": _pire(statuts),
        "motifs": motifs,
        "bougies": df,
        "nb": len(df),
        "derniere_bougie": df.index[-1].isoformat(),
        "age_min": age_min,
        "doublons": doublons,
    }


def ensemble(controles):
    """Statut global de plusieurs séries {« M5 » : contrôle, ...} : le pire l'emporte."""
    motifs = [f"{nom} : {m}" for nom, c in controles.items() for m in c["motifs"]]
    return {"statut": _pire([c["statut"] for c in controles.values()]), "motifs": motifs}


def ecart_sources(prix_a, prix_b, config):
    """Motif si deux sources de prix s'écartent de plus du seuil (en points), sinon chaîne vide."""
    if prix_a is None or prix_b is None:
        return ""
    ecart = abs(prix_a - prix_b)
    seuil = config["ecart_sources_points"]
    return f"Écart de {ecart:.1f} points entre les sources (seuil {seuil:g})." if ecart > seuil else ""


def regrouper_cme(h1, heures):
    """H4 ou H12 à partir du H1, calées sur l'ouverture CME (17h à Chicago) et non sur minuit UTC.

    La pause quotidienne n'a pas de bougie H1 : elle ne fausse donc ni les plus hauts, ni les plus bas, ni l'ATR.
    """
    if h1.empty:
        return h1
    local = h1.index.tz_convert(cal.CHICAGO).tz_localize(None)
    decale = local - pd.Timedelta(hours=17)
    debut = decale.floor(f"{heures}h") + pd.Timedelta(hours=17)
    cle = debut.tz_localize(cal.CHICAGO, ambiguous=np.ones(len(debut), dtype=bool),
                            nonexistent="shift_forward").tz_convert(dt.UTC)
    groupes = h1.groupby(cle)
    return pd.DataFrame({"o": groupes["o"].first(), "h": groupes["h"].max(), "l": groupes["l"].min(),
                         "c": groupes["c"].last(), "v": groupes["v"].sum()})
