# -*- coding: utf-8 -*-
"""
Calculs exacts pour chaque spécialiste du desk.

Les niveaux (FVG, order blocks, Fibo, Ichimoku, EMA, VWAP, profil de volume...)
sont calculés ici, en Python, à partir des bougies Yahoo Finance. L'IA ne fait
que les lire et les commenter : elle n'invente aucun chiffre.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

PARIS = "Europe/Paris"
NIVEAUX_FIBO = [1.0, 0.893, 0.786, 0.705, 0.618, 0.5, 0.0, -0.618, -1.618]
ZONES_ENTREE = [0.618, 0.705, 0.786, 0.893]  # zones d'entrée de Jabran (jamais le 0.5)


# ---------------------------------------------------------------- données


def charger(ticker):
    """Télécharge les bougies D1, H1, M15 et M5, et construit H4 et H12."""
    import yfinance as yf

    titre = yf.Ticker(ticker)

    def recuperer(periode, intervalle):
        df = titre.history(period=periode, interval=intervalle, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "High", "Low", "Close"])
        df.columns = ["o", "h", "l", "c", "v"]
        return df

    d1 = recuperer("2y", "1d")
    h1 = recuperer("180d", "1h")
    m15 = recuperer("30d", "15m")
    m5 = recuperer("5d", "5m")
    if h1.empty or d1.empty:
        raise RuntimeError(f"Pas de données Yahoo Finance pour {ticker}.")
    return {"D1": d1, "H12": regrouper(h1, "12h"), "H4": regrouper(h1, "4h"), "H1": h1, "M15": m15, "M5": m5}


def regrouper(df, regle):
    """Construit une unité de temps plus grande (ex. H4 à partir de H1)."""
    if df.empty:
        return df
    return df.resample(regle).agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()


# ---------------------------------------------------------------- outils


def arrondi(prix):
    """Arrondi lisible selon l'ordre de grandeur du prix."""
    if prix is None or (isinstance(prix, float) and np.isnan(prix)):
        return None
    prix = float(prix)
    if abs(prix) >= 1000:
        return round(prix, 1)
    if abs(prix) >= 10:
        return round(prix, 2)
    return round(prix, 4)


def heure(ts):
    """Date et heure de Paris, lisibles."""
    try:
        return pd.Timestamp(ts).tz_convert(PARIS).strftime("%d/%m %Hh%M")
    except (TypeError, ValueError):
        return pd.Timestamp(ts).strftime("%d/%m %Hh%M")


def ema(serie, n):
    return serie.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    precedent = df["c"].shift(1)
    vrai = pd.concat([df["h"] - df["l"], (df["h"] - precedent).abs(), (df["l"] - precedent).abs()], axis=1).max(axis=1)
    return vrai.ewm(alpha=1 / n, adjust=False).mean()


def heikin_ashi(df):
    cloture = (df["o"] + df["h"] + df["l"] + df["c"]) / 4
    ouverture = np.empty(len(df))
    ouverture[0] = (df["o"].iloc[0] + df["c"].iloc[0]) / 2
    for i in range(1, len(df)):
        ouverture[i] = (ouverture[i - 1] + cloture.iloc[i - 1]) / 2
    ouverture = pd.Series(ouverture, index=df.index)
    haut = pd.concat([df["h"], ouverture, cloture], axis=1).max(axis=1)
    bas = pd.concat([df["l"], ouverture, cloture], axis=1).min(axis=1)
    return pd.DataFrame({"o": ouverture, "h": haut, "l": bas, "c": cloture})


# ---------------------------------------------------------------- structure SMC


def pivots(df, cote=3):
    """Sommets et creux confirmés (fractales de `cote` bougies de chaque côté)."""
    hauts, bas = [], []
    h, l = df["h"].values, df["l"].values
    for i in range(cote, len(df) - cote):
        fenetre_h = h[i - cote:i + cote + 1]
        fenetre_l = l[i - cote:i + cote + 1]
        if h[i] == fenetre_h.max() and (fenetre_h == h[i]).sum() == 1:
            hauts.append((i, float(h[i])))
        if l[i] == fenetre_l.min() and (fenetre_l == l[i]).sum() == 1:
            bas.append((i, float(l[i])))
    return hauts, bas


def structure(df, cote=3):
    """BOS et CHoCH : cassures en clôture du dernier sommet ou creux confirmé."""
    hauts, bas = pivots(df, cote)
    confirmations = {}
    for i, p in hauts:
        confirmations.setdefault(i + cote, []).append(("haut", i, p))
    for i, p in bas:
        confirmations.setdefault(i + cote, []).append(("bas", i, p))
    dernier_haut = dernier_bas = None
    tendance = None
    evenements = []
    clotures = df["c"].values
    for i in range(len(df)):
        for genre, j, prix in confirmations.get(i, []):
            if genre == "haut":
                dernier_haut = {"i": j, "prix": prix, "casse": False}
            else:
                dernier_bas = {"i": j, "prix": prix, "casse": False}
        if dernier_haut and not dernier_haut["casse"] and clotures[i] > dernier_haut["prix"]:
            dernier_haut["casse"] = True
            evenements.append({"type": "BOS" if tendance == "haussier" else "CHoCH", "sens": "haussier",
                               "niveau": dernier_haut["prix"], "i": i, "origine": dernier_haut["i"]})
            tendance = "haussier"
        if dernier_bas and not dernier_bas["casse"] and clotures[i] < dernier_bas["prix"]:
            dernier_bas["casse"] = True
            evenements.append({"type": "BOS" if tendance == "baissier" else "CHoCH", "sens": "baissier",
                               "niveau": dernier_bas["prix"], "i": i, "origine": dernier_bas["i"]})
            tendance = "baissier"
    return {"tendance": tendance or "indéfinie", "evenements": evenements, "hauts": hauts, "bas": bas,
            "haut_actif": dernier_haut, "bas_actif": dernier_bas}


def fvg(df, taille_min):
    """Fair Value Gaps sur 3 bougies, avec leur état (intact, entamé, comblé)."""
    zones = []
    h, l = df["h"].values, df["l"].values
    for i in range(2, len(df)):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= taille_min:
            zones.append({"sens": "haussier", "bas": float(h[i - 2]), "haut": float(l[i]), "i": i - 1})
        if h[i] < l[i - 2] and l[i - 2] - h[i] >= taille_min:
            zones.append({"sens": "baissier", "bas": float(h[i]), "haut": float(l[i - 2]), "i": i - 1})
    for z in zones:
        apres = df.iloc[z["i"] + 2:]
        if z["sens"] == "haussier":
            plus_bas = apres["l"].min() if len(apres) else np.inf
            z["etat"] = "comblé" if plus_bas <= z["bas"] else ("entamé" if plus_bas < z["haut"] else "intact")
        else:
            plus_haut = apres["h"].max() if len(apres) else -np.inf
            z["etat"] = "comblé" if plus_haut >= z["haut"] else ("entamé" if plus_haut > z["bas"] else "intact")
    return zones


def order_blocks(df, struct):
    """Dernière bougie opposée avant l'impulsion qui a fait le BOS/CHoCH."""
    blocs = []
    o, c = df["o"].values, df["c"].values
    for ev in struct["evenements"][-12:]:
        debut, fin = ev["origine"], ev["i"]
        if fin - debut < 1:
            continue
        segment = df.iloc[debut:fin + 1]
        if ev["sens"] == "haussier":
            depart = debut + int(np.argmin(segment["l"].values))
            candidates = [k for k in range(max(0, depart - 5), depart + 1) if c[k] < o[k]]
        else:
            depart = debut + int(np.argmax(segment["h"].values))
            candidates = [k for k in range(max(0, depart - 5), depart + 1) if c[k] > o[k]]
        if not candidates:
            continue
        k = candidates[-1]
        bloc = {"sens": ev["sens"], "bas": float(df["l"].iloc[k]), "haut": float(df["h"].iloc[k]), "i": k}
        apres = df.iloc[fin + 1:]
        if ev["sens"] == "haussier":
            bloc["etat"] = "invalidé" if len(apres) and apres["c"].min() < bloc["bas"] else (
                "testé" if len(apres) and apres["l"].min() <= bloc["haut"] else "intact")
        else:
            bloc["etat"] = "invalidé" if len(apres) and apres["c"].max() > bloc["haut"] else (
                "testé" if len(apres) and apres["h"].max() >= bloc["bas"] else "intact")
        blocs.append(bloc)
    return blocs


def liquidite(donnees, a):
    """Liquidité : plus haut/bas de la veille, de la semaine, de la session Asie, égalités."""
    d1, h1, m15 = donnees["D1"], donnees["H1"], donnees["M15"]
    res = {}
    if len(d1) >= 2:
        res["plus_haut_veille"] = arrondi(d1["h"].iloc[-2])
        res["plus_bas_veille"] = arrondi(d1["l"].iloc[-2])
    semaine = h1[h1.index >= h1.index[-1] - pd.Timedelta(days=h1.index[-1].dayofweek, hours=h1.index[-1].hour)]
    if len(semaine):
        res["plus_haut_semaine"] = arrondi(semaine["h"].max())
        res["plus_bas_semaine"] = arrondi(semaine["l"].min())
    if len(m15):
        paris = m15.tz_convert(PARIS) if m15.index.tz is not None else m15
        jour = paris[paris.index.date == paris.index[-1].date()]
        asie = jour[(jour.index.hour >= 1) & (jour.index.hour < 8)]
        if len(asie):
            res["plus_haut_asie"] = arrondi(asie["h"].max())
            res["plus_bas_asie"] = arrondi(asie["l"].min())
    hauts, bas = pivots(h1.iloc[-300:], 3)
    tolerance = 0.15 * a
    egaux_hauts = sorted({arrondi((p1 + p2) / 2) for (i1, p1) in hauts[-20:] for (i2, p2) in hauts[-20:]
                          if i1 < i2 and abs(p1 - p2) <= tolerance and h1["h"].iloc[-300:].iloc[i2 + 1:].max() < max(p1, p2)})
    egaux_bas = sorted({arrondi((p1 + p2) / 2) for (i1, p1) in bas[-20:] for (i2, p2) in bas[-20:]
                        if i1 < i2 and abs(p1 - p2) <= tolerance and h1["l"].iloc[-300:].iloc[i2 + 1:].min() > min(p1, p2)})
    res["sommets_egaux_H1"] = egaux_hauts[-3:]
    res["creux_egaux_H1"] = egaux_bas[-3:]
    return res


def resume_smc(df, nom, a):
    struct = structure(df)
    zones = [z for z in fvg(df, 0.1 * a) if z["etat"] != "comblé"]
    blocs = [b for b in order_blocks(df, struct) if b["etat"] != "invalidé"]
    prix = float(df["c"].iloc[-1])
    proches = lambda liste: sorted(liste, key=lambda z: abs((z["haut"] + z["bas"]) / 2 - prix))[:3]
    return {
        "unite": nom,
        "tendance": struct["tendance"],
        "derniers_evenements": [
            {"type": e["type"], "sens": e["sens"], "niveau": arrondi(e["niveau"]), "quand": heure(df.index[e["i"]])}
            for e in struct["evenements"][-3:]
        ],
        "dernier_sommet": arrondi(struct["haut_actif"]["prix"]) if struct["haut_actif"] else None,
        "dernier_creux": arrondi(struct["bas_actif"]["prix"]) if struct["bas_actif"] else None,
        "fvg_proches": [{"sens": z["sens"], "zone": [arrondi(z["bas"]), arrondi(z["haut"])], "etat": z["etat"],
                         "quand": heure(df.index[z["i"]])} for z in proches(zones)],
        "order_blocks_proches": [{"sens": b["sens"], "zone": [arrondi(b["bas"]), arrondi(b["haut"])], "etat": b["etat"],
                                  "quand": heure(df.index[b["i"]])} for b in proches(blocs)],
    }


# ---------------------------------------------------------------- Fibo (méthode de Jabran)


def fibo(donnees, a_h1):
    """Fibo sur la dernière belle impulsion H1, zones valides seulement avec un FVG dessus."""
    h1 = donnees["H1"].iloc[-500:]
    hauts, bas = pivots(h1, 3)
    points = sorted([(i, p, "haut") for i, p in hauts] + [(i, p, "bas") for i, p in bas])
    jambe = None
    for k in range(len(points) - 1, 0, -1):
        (i2, p2, g2), (i1, p1, g1) = points[k], points[k - 1]
        if g1 != g2 and abs(p2 - p1) >= 2.5 * a_h1:
            jambe = (i1, p1, g1, i2, p2, g2)
            break
    if not jambe:
        return {"disponible": False, "raison": "Pas d'impulsion nette récente en H1."}
    i1, p1, g1, i2, p2, g2 = jambe
    # Après le pivot final, l'extrême peut avoir été dépassé : on prolonge la jambe
    suite = h1.iloc[i2:]
    if g2 == "haut" and suite["h"].max() > p2:
        p2 = float(suite["h"].max())
        i2 = i2 + int(np.argmax(suite["h"].values))
    if g2 == "bas" and suite["l"].min() < p2:
        p2 = float(suite["l"].min())
        i2 = i2 + int(np.argmin(suite["l"].values))
    sens = "haussière" if g2 == "haut" else "baissière"
    niveaux = {f"{x:g}": arrondi(p2 + x * (p1 - p2)) for x in NIVEAUX_FIBO}  # 0 = fin de l'impulsion, 1 = départ
    zones_fvg = [z for z in fvg(h1, 0.1 * a_h1) if i1 <= z["i"] <= i2 + 1
                 and z["sens"] == ("haussier" if sens == "haussière" else "baissier")]
    zones = []
    for x in ZONES_ENTREE:
        niveau = p2 + x * (p1 - p2)
        marge = 0.15 * a_h1
        avec_fvg = [z for z in zones_fvg if z["bas"] - marge <= niveau <= z["haut"] + marge]
        zones.append({"niveau": f"{x:g}", "prix": arrondi(niveau), "fvg_dessus": bool(avec_fvg),
                      "fvg": [arrondi(avec_fvg[0]["bas"]), arrondi(avec_fvg[0]["haut"])] if avec_fvg else None})
    prix = float(h1["c"].iloc[-1])
    retracement = (p2 - prix) / (p2 - p1) if p2 != p1 else 0
    return {
        "disponible": True,
        "impulsion": sens,
        "depart": {"prix": arrondi(p1), "quand": heure(h1.index[i1])},
        "fin": {"prix": arrondi(p2), "quand": heure(h1.index[i2])},
        "niveaux": niveaux,
        "zones_entree": zones,
        "retracement_actuel": round(float(retracement), 3),
        "lecture": ("le prix a dépassé le départ de l'impulsion : Fibo invalidé" if retracement > 1 else
                    "le prix est dans les zones d'entrée 0.618-0.893" if retracement >= 0.618 else
                    "le prix est autour du 50 % : zone interdite pour entrer" if 0.45 <= retracement < 0.618 else
                    "le prix n'a pas encore assez retracé" if retracement >= 0 else
                    "le prix prolonge l'impulsion (au-delà du niveau 0)"),
    }


# ---------------------------------------------------------------- Ichimoku


def ichimoku(df, nom):
    if len(df) < 80:
        return {"unite": nom, "disponible": False}
    haut, bas, c = df["h"], df["l"], df["c"]
    tenkan = (haut.rolling(9).max() + bas.rolling(9).min()) / 2
    kijun = (haut.rolling(26).max() + bas.rolling(26).min()) / 2
    ssa = (tenkan + kijun) / 2
    ssb = (haut.rolling(52).max() + bas.rolling(52).min()) / 2
    # nuage sous le prix actuel = valeurs calculées il y a 26 bougies
    nuage_a, nuage_b = ssa.iloc[-27], ssb.iloc[-27]
    prix = c.iloc[-1]
    haut_nuage, bas_nuage = max(nuage_a, nuage_b), min(nuage_a, nuage_b)
    position = "au-dessus du nuage" if prix > haut_nuage else "sous le nuage" if prix < bas_nuage else "dans le nuage"
    croisements = np.sign(tenkan - kijun).diff().fillna(0)
    dernier = croisements[croisements != 0]
    croisement = None
    if len(dernier):
        rang = df.index.get_loc(dernier.index[-1])
        croisement = {"sens": "haussier" if dernier.iloc[-1] > 0 else "baissier", "il_y_a": int(len(df) - 1 - rang)}
    chikou_vs = c.iloc[-27]
    return {
        "unite": nom,
        "disponible": True,
        "prix": arrondi(prix),
        "tenkan": arrondi(tenkan.iloc[-1]),
        "kijun": arrondi(kijun.iloc[-1]),
        "kijun_plate": bool(abs(kijun.iloc[-1] - kijun.iloc[-6]) < 1e-9),
        "nuage_actuel": [arrondi(bas_nuage), arrondi(haut_nuage)],
        "position_prix": position,
        "nuage_futur": "haussier (vert)" if ssa.iloc[-1] > ssb.iloc[-1] else "baissier (rouge)",
        "dernier_croisement_tenkan_kijun": croisement,
        "chikou": "au-dessus du prix d'il y a 26 bougies" if prix > chikou_vs else "sous le prix d'il y a 26 bougies",
    }


# ---------------------------------------------------------------- tendance


def tendance(donnees, ticker):
    res = {}
    for nom in ("D1", "H4", "H1"):
        df = donnees[nom]
        if len(df) < 210:
            continue
        e = ema(df["c"], 200)
        res[f"ema200_{nom}"] = {
            "valeur": arrondi(e.iloc[-1]),
            "prix": "au-dessus" if df["c"].iloc[-1] > e.iloc[-1] else "en dessous",
            "pente": "montante" if e.iloc[-1] > e.iloc[-21] else "descendante",
        }
    for nom in ("H4", "H1"):
        ha = heikin_ashi(donnees[nom].iloc[-60:])
        couleurs = np.where(ha["c"] >= ha["o"], "verte", "rouge")
        serie = 1
        while serie < len(couleurs) and couleurs[-1 - serie] == couleurs[-1]:
            serie += 1
        derniere = ha.iloc[-1]
        sans_meche = (derniere["l"] >= min(derniere["o"], derniere["c"]) - 1e-9) if couleurs[-1] == "verte" else (
            derniere["h"] <= max(derniere["o"], derniere["c"]) + 1e-9)
        res[f"heikin_ashi_{nom}"] = {"couleur": str(couleurs[-1]), "bougies_de_suite": int(serie),
                                     "bougie_de_force_sans_meche": bool(sans_meche)}
    res["vwap"] = vwap(donnees, ticker)
    return res


def debut_session(index, ticker):
    """Début de la session en cours : 18h New York pour les futures, minuit sinon."""
    dernier = index[-1]
    if ticker.endswith("=F"):
        ny = dernier.tz_convert("America/New_York")
        debut = ny.normalize() + pd.Timedelta(hours=18)
        if ny < debut:
            debut -= pd.Timedelta(days=1)
        return debut
    return dernier.normalize()


def vwap(donnees, ticker):
    df = donnees["M5"] if len(donnees["M5"]) else donnees["M15"]
    if df.empty:
        return None
    session = df[df.index >= debut_session(df.index, ticker)]
    if len(session) < 3 or session["v"].sum() == 0:
        return None
    typique = (session["h"] + session["l"] + session["c"]) / 3
    v = typique.mul(session["v"]).cumsum() / session["v"].cumsum()
    ecart = np.sqrt(((typique - v) ** 2).mul(session["v"]).cumsum() / session["v"].cumsum())
    prix = session["c"].iloc[-1]
    return {"valeur": arrondi(v.iloc[-1]), "bande_haute_1": arrondi(v.iloc[-1] + ecart.iloc[-1]),
            "bande_basse_1": arrondi(v.iloc[-1] - ecart.iloc[-1]),
            "prix": "au-dessus" if prix > v.iloc[-1] else "en dessous",
            "depuis": heure(session.index[0])}


# ---------------------------------------------------------------- order flow estimé


def order_flow(donnees, ticker):
    """Profil de volume et delta ESTIMÉS à partir de bougies 5 minutes (pas un vrai footprint)."""
    df = donnees["M5"] if len(donnees["M5"]) else donnees["M15"]
    if df.empty or df["v"].sum() == 0:
        return {"disponible": False, "raison": "Pas de volume disponible pour ce marché."}
    debut = debut_session(df.index, ticker)
    session = df[df.index >= debut - pd.Timedelta(days=1)]  # session actuelle + précédente
    if len(session) < 10:
        session = df.iloc[-200:]
    bas, haut = session["l"].min(), session["h"].max()
    cases = np.linspace(bas, haut, 61)
    volume = np.zeros(60)
    for _, b in session.iterrows():
        dans = (cases[1:] >= b["l"]) & (cases[:-1] <= b["h"])
        if dans.sum():
            volume[dans] += b["v"] / dans.sum()
    centres = (cases[1:] + cases[:-1]) / 2
    poc = int(np.argmax(volume))
    gauche = droite = poc
    total, cible = volume[poc], 0.7 * volume.sum()
    while total < cible and (gauche > 0 or droite < 59):
        ajout_g = volume[gauche - 1] if gauche > 0 else -1
        ajout_d = volume[droite + 1] if droite < 59 else -1
        if ajout_d >= ajout_g:
            droite += 1
            total += volume[droite]
        else:
            gauche -= 1
            total += volume[gauche]
    etendue = (session["h"] - session["l"]).replace(0, np.nan)
    delta = (session["v"] * (2 * session["c"] - session["h"] - session["l"]) / etendue).fillna(0)
    du_jour = session[session.index >= debut]
    delta_jour = delta[delta.index >= debut]
    cumul = delta_jour.cumsum()
    divergence = None
    if len(du_jour) >= 24:
        recent, avant = du_jour.iloc[-12:], du_jour.iloc[-24:-12]
        if recent["h"].max() > avant["h"].max() and cumul.iloc[-1] < cumul.iloc[-13]:
            divergence = "prix plus haut mais delta en baisse (acheteurs qui s'essoufflent)"
        elif recent["l"].min() < avant["l"].min() and cumul.iloc[-1] > cumul.iloc[-13]:
            divergence = "prix plus bas mais delta en hausse (vendeurs qui s'essoufflent)"
    moyenne, ecart = session["v"].mean(), session["v"].std()
    gros = session[session["v"] > moyenne + 2 * ecart].tail(5)
    gros_volumes = []
    for ts, b in gros.iterrows():
        petite = (b["h"] - b["l"]) < 0.5 * (session["h"] - session["l"]).mean()
        gros_volumes.append({"quand": heure(ts), "prix": arrondi(b["c"]),
                             "sens_estime": "acheteur" if delta.loc[ts] > 0 else "vendeur",
                             "absorption_possible": bool(petite)})
    return {
        "disponible": True,
        "avertissement": "Estimé à partir de bougies, pas un vrai footprint ni un vrai CVD.",
        "poc": arrondi(centres[poc]),
        "zone_de_valeur": [arrondi(centres[gauche]), arrondi(centres[droite])],
        "prix": "au-dessus de la zone de valeur" if session["c"].iloc[-1] > centres[droite] else
                "sous la zone de valeur" if session["c"].iloc[-1] < centres[gauche] else "dans la zone de valeur",
        "delta_cumule_session": "positif" if len(cumul) and cumul.iloc[-1] > 0 else "négatif",
        "divergence": divergence,
        "gros_volumes_recents": gros_volumes,
    }


# ---------------------------------------------------------------- calendrier


def telecharger_calendrier():
    requete = urllib.request.Request("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                                     headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(requete, timeout=10) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def calendrier(maintenant=None, config=None, source=telecharger_calendrier):
    """Annonces économiques USD de la semaine (flux public de Forex Factory), classées par mgc/annonces.py.

    Jour de réunion du FOMC = journée bloquée (règle personnelle de Jabran) ; un discours du président de la Fed
    n'est PAS un jour de FOMC : il bloque 30 min avant et après. Annonce forte : 90 min avant, 30 min après.
    """
    from mgc import annonces
    from mgc import config as cfg

    config = config or cfg.charger()
    maintenant = maintenant or datetime.now(timezone.utc)
    try:
        evenements = source()
    except Exception as erreur:
        return {"disponible": False, "raison": f"Calendrier indisponible ({type(erreur).__name__})."}
    aujourd_hui = maintenant.astimezone(ZoneInfo(PARIS)).date()
    liste, a_venir, fomc_aujourdhui = [], [], False
    for e in evenements:
        titre = e.get("title", "")
        if e.get("country") != "USD":
            continue
        genre = annonces.classer(titre, e.get("impact"))
        if genre == "autre" and e.get("impact") != "Medium":
            continue
        try:
            quand = pd.Timestamp(e["date"]).to_pydatetime()
        except (KeyError, ValueError):
            continue
        liste.append({"quand": quand.isoformat(), "titre": titre, "impact": e.get("impact", "")})
        if genre == "reunion_fomc" and quand.astimezone(ZoneInfo(PARIS)).date() == aujourd_hui:
            fomc_aujourdhui = True
        if maintenant - timedelta(hours=2) <= quand <= maintenant + timedelta(hours=48):
            a_venir.append({"quand": heure(quand), "titre": titre, "impact": "fort" if e.get("impact") == "High" else "moyen",
                            "genre": genre})
    blocages = annonces.blocages(maintenant, liste, config)
    return {"disponible": True, "fomc_aujourdhui": fomc_aujourdhui,
            "annonce_forte_dans_90_min": [b for b in blocages if not b.startswith("Jour de réunion")],
            "blocages": blocages, "annonces_48h": a_venir[:10], "liste": liste,
            "regle_prop_firm": f"{config['prop_firm']} n'interdit pas de trader les annonces. Règle personnelle de Jabran : "
                               "pas de trade un jour de réunion du FOMC ; discours du président de la Fed : 30 min avant et après."}


# ---------------------------------------------------------------- macro (dollar et taux)


def macro(ticker):
    """Dollar (DXY) et taux 10 ans US : les deux moteurs classiques de l'or. Seulement pour les métaux."""
    if ticker not in ("GC=F", "MGC=F", "SI=F") and "XAU" not in ticker:
        return {"disponible": False, "raison": "Données macro réservées aux métaux."}
    import yfinance as yf

    res = {"disponible": True, "lecture": "en général, dollar et taux qui montent pèsent sur l'or ; l'inverse le soutient"}
    for nom, symbole in (("dollar_DXY", "DX-Y.NYB"), ("taux_10_ans_US", "^TNX")):
        try:
            c = yf.Ticker(symbole).history(period="3mo", interval="1d", auto_adjust=False)["Close"].dropna()
            res[nom] = {
                "dernier": round(float(c.iloc[-1]), 3),
                "variation_5_jours_pct": round(float((c.iloc[-1] / c.iloc[-6] - 1) * 100), 2),
                "au_dessus_moyenne_20_jours": bool(c.iloc[-1] > c.tail(20).mean()),
            }
        except Exception:
            res[nom] = None
    return res


# ---------------------------------------------------------------- tout préparer


def preparer(ticker, donnees=None):
    """Toutes les données calculées, rangées par spécialiste."""
    donnees = donnees or charger(ticker)
    h1 = donnees["H1"]
    a_h1 = float(atr(h1).iloc[-1])
    prix = float(donnees["M5"]["c"].iloc[-1]) if len(donnees["M5"]) else float(h1["c"].iloc[-1])
    maintenant = pd.Timestamp.now(tz=PARIS)
    cal = calendrier()
    annonces_brutes = cal.pop("liste", [])  # pour les vetos du programme, pas pour les prompts des IA
    return {
        "annonces_brutes": annonces_brutes,
        "marche": {
            "ticker": ticker,
            "prix": arrondi(prix),
            "derniere_bougie": heure(h1.index[-1]),
            "heure_paris": maintenant.strftime("%d/%m %Hh%M"),
            "atr_H1": round(a_h1, 2),
            "atr_D1": round(float(atr(donnees["D1"]).iloc[-1]), 2),
            "note": "Prix du contrat future (COMEX), un peu différent du XAU/USD spot." if ticker.endswith("=F") else "",
        },
        "smc": {
            "structure": [resume_smc(donnees[n], n, float(atr(donnees[n]).iloc[-1]))
                          for n in ("D1", "H4", "H1", "M15") if len(donnees[n]) > 30],
            "liquidite": liquidite(donnees, a_h1),
        },
        "fibo": {
            **fibo(donnees, a_h1),
            "biais_regle_jabran": {
                "structure_H12": structure(donnees["H12"])["tendance"] if len(donnees["H12"]) > 30 else "indéfinie",
                "structure_H1": structure(h1)["tendance"],
                "ema200_H1": "montante" if len(h1) > 220 and ema(h1["c"], 200).iloc[-1] > ema(h1["c"], 200).iloc[-21] else "descendante",
            },
        },
        "ichimoku": [ichimoku(donnees[n], n) for n in ("D1", "H4", "H1")],
        "tendance": tendance(donnees, ticker),
        "orderflow": order_flow(donnees, ticker),
        "calendrier": cal,
        "macro": macro(ticker),
    }
