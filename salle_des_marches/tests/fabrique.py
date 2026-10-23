# -*- coding: utf-8 -*-
"""Bougies artificielles pour les tests (seulement pendant les heures où le CME est ouvert)."""

import datetime as dt

import pandas as pd

from mgc import calendrier_cme as cal

UTC = dt.UTC


def bougies(fin, n, periode_min, prix=4200.0):
    """Les n dernières bougies de `periode_min` minutes fermées à l'instant `fin`, séance ouverte uniquement."""
    pas = dt.timedelta(minutes=periode_min)
    debuts, t = [], fin - pas
    while len(debuts) < n:
        if cal.etat_seance(t)["etat"] == "ouverte":
            debuts.append(t)
        t -= pas
    index = pd.DatetimeIndex(sorted(debuts)).tz_convert(UTC)
    return pd.DataFrame({"o": prix, "h": prix + 1.0, "l": prix - 1.0, "c": prix + 0.5, "v": 100.0}, index=index)


def journalier(fin, n, prix=4200.0):
    jours = pd.bdate_range(end=fin.date(), periods=n)
    index = pd.DatetimeIndex(jours).tz_localize("UTC")
    return pd.DataFrame({"o": prix, "h": prix + 10.0, "l": prix - 10.0, "c": prix + 5.0, "v": 1000.0}, index=index)


def format_yahoo(df, quotidien=False):
    """Convention commune -> format Yahoo (colonnes Open..., heure de New York)."""
    y = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    if quotidien:
        y.index = y.index.tz_localize(None).tz_localize("America/New_York")
    else:
        y.index = y.index.tz_convert("America/New_York")
    return y


def ecrire_csv(fichier, df, quotidien=False):
    lignes = ["date_seance,o,h,l,c,v" if quotidien else "debut_utc,o,h,l,c,v"]
    for t, b in df.iterrows():
        quand = t.strftime("%Y-%m-%d") if quotidien else t.strftime("%Y-%m-%dT%H:%M:%SZ")
        lignes.append(f"{quand},{b.o},{b.h},{b.l},{b.c},{int(b.v)}")
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")
