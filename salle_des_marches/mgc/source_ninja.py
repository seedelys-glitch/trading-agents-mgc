# -*- coding: utf-8 -*-
"""
Lecture des fichiers écrits par l'indicateur NinjaTrader « ExportBougiesMGC » (lecture seule, aucun ordre).

  donnees_ninja\\MGC_M1.csv ... MGC_H1.csv  debut_utc,o,h,l,c,v   (bougies fermées)
  donnees_ninja\\MGC_D1.csv                 date_seance,o,h,l,c,v
  donnees_ninja\\battement.json             contrat, dernier prix, heure UTC (toutes les 2 s au plus)

L'indicateur écrit pendant qu'on lit : une dernière ligne coupée en deux est simplement ignorée.
"""

import datetime as dt
import io
import json
import os
from pathlib import Path

import pandas as pd

from .instrument import MOIS_CODES

UNITES = {"M1": 1, "M3": 3, "M5": 5, "M15": 15, "H1": 60, "D1": 1440}


def dossier_par_defaut(config):
    if config.get("dossier_ninja"):
        return Path(config["dossier_ninja"])
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "TradingAgents" / "donnees_ninja"


def code_depuis_ninja(nom):
    """« MGC 12-26 » (nom NinjaTrader) -> « MGCZ26 ». None si le nom n'est pas compris."""
    try:
        racine, echeance = nom.strip().split(" ")
        mois, annee = echeance.split("-")
        return f"{racine.upper()}{MOIS_CODES[int(mois)]}{int(annee):02d}"
    except (ValueError, KeyError, AttributeError):
        return None


def lire_battement(dossier):
    """Contenu de battement.json, ou None s'il est absent ou en cours d'écriture."""
    try:
        donnees = json.loads((Path(dossier) / "battement.json").read_text(encoding="utf-8-sig"))
        donnees["heure"] = dt.datetime.fromisoformat(donnees["heure_utc"].replace("Z", "+00:00"))
        donnees["code"] = code_depuis_ninja(donnees.get("contrat", ""))
        return donnees
    except (OSError, ValueError, KeyError, TypeError):
        return None


def lire_bougies(fichier):
    """Un fichier MGC_<unité>.csv -> DataFrame (index UTC, colonnes o, h, l, c, v). Lignes abîmées ignorées."""
    try:
        with open(fichier, encoding="utf-8-sig", newline="") as f:
            texte = f.read()
    except OSError:
        return pd.DataFrame()
    lignes = texte.splitlines()
    if not lignes:
        return pd.DataFrame()
    entete, corps = lignes[0], [ligne for ligne in lignes[1:] if ligne.count(",") == 5]
    df = pd.read_csv(io.StringIO("\n".join([entete, *corps])), on_bad_lines="skip")
    if df.empty:
        return pd.DataFrame()
    colonne = df.columns[0]
    df.index = pd.to_datetime(df.pop(colonne), utc=True, errors="coerce")
    df = df[df.index.notna()].apply(pd.to_numeric, errors="coerce").dropna()
    return df[["o", "h", "l", "c", "v"]]


def charger(dossier):
    """Toutes les unités de temps disponibles + le battement."""
    dossier = Path(dossier)
    return {
        "bougies": {nom: lire_bougies(dossier / f"MGC_{nom}.csv") for nom in UNITES},
        "battement": lire_battement(dossier),
    }


def en_direct(battement, instant, config):
    """(True, "") si NinjaTrader a donné signe de vie récemment, sinon (False, motif)."""
    if not battement:
        return False, "NinjaTrader : aucun fichier battement.json (indicateur pas lancé ?)."
    if battement.get("erreur"):
        return False, f"NinjaTrader : {battement['erreur']}"
    age = (instant - battement["heure"]).total_seconds()
    if age > config["battement_max_s"]:
        return False, f"NinjaTrader : pas de nouvelle donnée depuis {int(age // 60)} min (connexion coupée ?)."
    if battement.get("etat") != "temps_reel":
        return False, "NinjaTrader : indicateur en cours de chargement."
    return True, ""
